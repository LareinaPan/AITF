import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models.api_endpoint import ApiEndpoint
from app.models.test_case import TestCase
from app.schemas.ai_generation import AIGeneratedTestCaseCandidate

JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

SYSTEM_PROMPT = """You are an API test case generator for an automated testing platform.
Return ONLY a JSON array. Do not include markdown or explanations.
The array length MUST exactly match the requested total count.
Each item must match this shape:
{
  "name": "string",
  "description": "string or null",
  "priority": "P0|P1|P2|P3",
  "request_json": {
    "method": "GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS",
    "url": "string using {{base_url}} prefix when calling the API path",
    "headers": [{"key": "Header-Name", "value": "value"}],
    "query": [{"key": "param", "value": "value"}],
    "body": {"type": "none|json|raw|form", "content": "string"}
  },
  "assertions_json": {
    "status_code": 200,
    "max_response_time_ms": 3000,
    "body_rules": [
      {"type": "contains", "value": "success"},
      {"type": "json_path", "path": "$.code", "operator": "eq", "expected": "0"}
    ]
  }
}
Use realistic values derived from the OpenAPI context. Prefer {{base_url}} in request URLs.
Every json_path body rule MUST include operator=eq and expected fields."""


class AIGenerationError(Exception):
    """Base error for AI test case generation."""


class LLMConfigurationError(AIGenerationError):
    """Raised when AI provider settings are missing or invalid."""


class LLMCallError(AIGenerationError):
    """Raised when the LLM provider call fails."""


class LLMResponseParseError(AIGenerationError):
    """Raised when LLM output cannot be parsed as JSON array."""


class LLMOutputValidationError(AIGenerationError):
    """Raised when no LLM-generated test case passes schema validation."""


@dataclass(frozen=True)
class CandidateValidationResult:
    valid_cases: list[dict[str, Any]]
    rejected_count: int
    errors: list[str]


@dataclass(frozen=True)
class GeneratedTestCases:
    cases: list[dict[str, Any]]
    rejected_count: int
    requested_count: int
    raw_count: int = 0


class ChatCompletionClient(Protocol):
    class Chat:
        class Completions:
            def create(self, **kwargs: Any) -> Any: ...

        completions: Completions

    chat: Chat


@dataclass(frozen=True)
class GenerationCounts:
    positive_count: int
    boundary_count: int
    exception_count: int
    auth_count: int

    @property
    def total(self) -> int:
        return (
            self.positive_count
            + self.boundary_count
            + self.exception_count
            + self.auth_count
        )


@dataclass(frozen=True)
class EndpointContext:
    method: str
    path: str
    summary: str | None
    description: str | None
    parameters_json: list[Any]
    request_body_json: dict[str, Any] | None
    responses_json: dict[str, Any]


def endpoint_context_from_model(endpoint: ApiEndpoint) -> EndpointContext:
    return EndpointContext(
        method=endpoint.method,
        path=endpoint.path,
        summary=endpoint.summary,
        description=endpoint.description,
        parameters_json=endpoint.parameters_json,
        request_body_json=endpoint.request_body_json,
        responses_json=endpoint.responses_json,
    )


def build_generation_prompt(
    endpoint: EndpointContext,
    counts: GenerationCounts,
) -> tuple[str, str]:
    """Build system and user prompts for LLM test case generation."""
    openapi_context = {
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
        "description": endpoint.description,
        "parameters": endpoint.parameters_json,
        "requestBody": endpoint.request_body_json,
        "responses": endpoint.responses_json,
    }
    generation_plan = {
        "positive": counts.positive_count,
        "boundary": counts.boundary_count,
        "exception": counts.exception_count,
        "auth": counts.auth_count,
        "total": counts.total,
    }
    user_prompt = (
        "Generate API test cases for the following OpenAPI operation.\n"
        f"Generation counts: {json.dumps(generation_plan, ensure_ascii=False)}\n"
        f"OpenAPI operation context: {json.dumps(openapi_context, ensure_ascii=False)}\n"
        "Rules:\n"
        f"- Return a JSON array with EXACTLY {counts.total} objects.\n"
        f"- Include exactly {counts.positive_count} positive, "
        f"{counts.boundary_count} boundary, "
        f"{counts.exception_count} exception, and "
        f"{counts.auth_count} auth cases.\n"
        "- Positive cases should use valid inputs and expect success responses.\n"
        "- Boundary cases should test edge values from schemas.\n"
        "- Exception cases should use invalid inputs and expect error responses.\n"
        "- Auth cases should cover missing or invalid credentials when relevant.\n"
        "- request_json.method should match the OpenAPI operation method when possible.\n"
        "- request_json.url must start with {{base_url}} followed by the API path.\n"
        "- Each case name must be unique.\n"
        "- Return a JSON array only."
    )
    return SYSTEM_PROMPT, user_prompt


def build_retry_prompt(
    endpoint: EndpointContext,
    counts: GenerationCounts,
    existing_names: list[str],
    remaining: int,
) -> str:
    openapi_context = {
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
    }
    return (
        "Previous generation did not produce enough valid test cases.\n"
        f"Generate EXACTLY {remaining} additional unique API test cases.\n"
        f"Do not reuse these names: {json.dumps(existing_names, ensure_ascii=False)}\n"
        f"OpenAPI operation context: {json.dumps(openapi_context, ensure_ascii=False)}\n"
        "Return a JSON array only. Each object must follow the required schema."
    )


VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
VALID_BODY_TYPES = frozenset({"none", "json", "raw", "form"})
MAX_GENERATION_ATTEMPTS = 3


def _normalize_key_value_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        normalized.append({"key": key, "value": str(item.get("value", ""))})
    return normalized


def _normalize_body_rules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for rule in value:
        if not isinstance(rule, dict):
            continue
        rule_type = str(rule.get("type", "")).strip()
        if rule_type == "contains":
            text = str(rule.get("value", "")).strip()
            if text:
                normalized.append({"type": "contains", "value": text})
            continue
        if rule_type == "json_path":
            path = str(rule.get("path", "")).strip()
            if not path:
                continue
            expected = rule.get("expected", rule.get("value", "0"))
            normalized.append(
                {
                    "type": "json_path",
                    "path": path,
                    "operator": "eq",
                    "expected": str(expected),
                }
            )
    return normalized


def _normalize_priority(value: Any) -> str:
    if not isinstance(value, str):
        return "P2"
    normalized = value.strip().upper()
    if normalized in VALID_PRIORITIES:
        return normalized
    return "P2"


def normalize_llm_candidate(item: dict[str, Any], endpoint: EndpointContext) -> dict[str, Any]:
    """Best-effort cleanup for common LLM formatting mistakes before schema validation."""
    normalized = dict(item)
    normalized["name"] = str(normalized.get("name", "")).strip()
    normalized["priority"] = _normalize_priority(normalized.get("priority"))

    description = normalized.get("description")
    if description is not None:
        normalized["description"] = str(description).strip() or None

    request_json = normalized.get("request_json")
    request = dict(request_json) if isinstance(request_json, dict) else {}

    method = str(request.get("method", endpoint.method)).strip().upper() or endpoint.method
    request["method"] = method

    url = str(request.get("url", "")).strip()
    if not url:
        request["url"] = f"{{{{base_url}}}}{endpoint.path}"
    elif not url.startswith("{{base_url}}"):
        if url.startswith(("http://", "https://")):
            parsed = urlparse(url)
            path = parsed.path or endpoint.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            request["url"] = f"{{{{base_url}}}}{path}"
        elif url.startswith(endpoint.path):
            request["url"] = f"{{{{base_url}}}}{url}"
        elif url.startswith("/"):
            request["url"] = f"{{{{base_url}}}}{url}"
        else:
            request["url"] = f"{{{{base_url}}}}{endpoint.path}"

    request["headers"] = _normalize_key_value_items(request.get("headers"))
    request["query"] = _normalize_key_value_items(request.get("query"))

    body = request.get("body")
    body_dict = dict(body) if isinstance(body, dict) else {}
    body_type = str(body_dict.get("type", "none")).strip().lower()
    if body_type not in VALID_BODY_TYPES:
        body_type = "json" if body_dict.get("content") else "none"
    request["body"] = {
        "type": body_type,
        "content": str(body_dict.get("content", "")),
    }
    normalized["request_json"] = request

    assertions_json = normalized.get("assertions_json")
    assertions = dict(assertions_json) if isinstance(assertions_json, dict) else {}
    status_code = assertions.get("status_code", 200)
    try:
        assertions["status_code"] = int(status_code)
    except (TypeError, ValueError):
        assertions["status_code"] = 200

    max_ms = assertions.get("max_response_time_ms", 3000)
    try:
        assertions["max_response_time_ms"] = int(max_ms)
    except (TypeError, ValueError):
        assertions["max_response_time_ms"] = 3000

    assertions["body_rules"] = _normalize_body_rules(assertions.get("body_rules"))
    normalized["assertions_json"] = assertions
    return normalized


def extract_json_array(content: str) -> list[dict[str, Any]]:
    """Extract a JSON array from raw LLM output."""
    text = content.strip()
    if not text:
        raise LLMResponseParseError("LLM response is empty")

    candidates = [text]
    fenced_blocks = JSON_FENCE_PATTERN.findall(text)
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

        if isinstance(parsed, list):
            items = [item for item in parsed if isinstance(item, dict)]
            if not items:
                raise LLMResponseParseError("LLM response JSON array is empty")
            return items

        if isinstance(parsed, dict):
            for key in ("cases", "test_cases", "items"):
                nested = parsed.get(key)
                if isinstance(nested, list):
                    items = [item for item in nested if isinstance(item, dict)]
                    if items:
                        return items

    detail = str(last_error) if last_error else "no JSON array found"
    raise LLMResponseParseError(f"Unable to parse LLM response as JSON array: {detail}")


def validate_test_case_candidate(
    item: dict[str, Any],
    endpoint: EndpointContext | None = None,
) -> dict[str, Any]:
    """Validate and normalize a single LLM-generated test case candidate."""
    payload = normalize_llm_candidate(item, endpoint) if endpoint is not None else item
    candidate = AIGeneratedTestCaseCandidate.model_validate(payload)
    return candidate.to_storage_dict()


def validate_test_case_candidates(
    items: list[dict[str, Any]],
    *,
    endpoint: EndpointContext | None = None,
    require_at_least_one: bool = True,
) -> CandidateValidationResult:
    """Validate LLM candidates; skip invalid items and collect error messages."""
    valid_cases: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, item in enumerate(items):
        try:
            if not isinstance(item, dict):
                raise ValueError("case must be a JSON object")
            valid_cases.append(validate_test_case_candidate(item, endpoint))
        except Exception as exc:
            label = item.get("name") if isinstance(item, dict) else None
            prefix = f"case[{index}]"
            if label:
                prefix = f'{prefix} "{label}"'
            errors.append(f"{prefix}: {exc}")

    if require_at_least_one and items and not valid_cases:
        detail = "; ".join(errors[:5])
        if len(errors) > 5:
            detail = f"{detail}; ...and {len(errors) - 5} more"
        raise LLMOutputValidationError(
            f"No valid test cases in LLM output ({len(items)} rejected): {detail}"
        )

    return CandidateValidationResult(
        valid_cases=valid_cases,
        rejected_count=len(errors),
        errors=errors,
    )


def create_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is not configured")
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.ai_request_timeout_seconds,
    )


@retry(
    retry=retry_if_exception_type(
        (APITimeoutError, APIConnectionError, RateLimitError),
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _create_chat_completion(
    client: ChatCompletionClient,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
    except Exception as exc:
        raise LLMCallError(f"LLM request failed for model {model}: {exc}") from exc

    message = response.choices[0].message
    content = message.content if message is not None else None
    if not content:
        raise LLMCallError(f"LLM returned empty content for model {model}")
    return content


def call_llm(
    messages: list[dict[str, str]],
    *,
    client: ChatCompletionClient | None = None,
    primary_model: str | None = None,
    fallback_model: str | None = None,
) -> str:
    """Call LLM with retry and fallback model support."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is not configured")

    llm_client = client or create_openai_client()
    primary = primary_model or settings.ai_model
    fallback = fallback_model or settings.ai_fallback_model

    try:
        return _create_chat_completion(llm_client, model=primary, messages=messages)
    except (LLMCallError, APITimeoutError, APIConnectionError, RateLimitError) as primary_error:
        if fallback == primary:
            raise LLMCallError(str(primary_error)) from primary_error
        try:
            return _create_chat_completion(llm_client, model=fallback, messages=messages)
        except Exception as fallback_error:
            raise LLMCallError(
                f"Primary model failed ({primary_error}); "
                f"fallback model failed ({fallback_error})"
            ) from fallback_error


def generate_test_case_candidates(
    endpoint: ApiEndpoint | EndpointContext,
    counts: GenerationCounts,
    *,
    client: ChatCompletionClient | None = None,
) -> GeneratedTestCases:
    """Generate validated test case candidates from an API endpoint via LLM."""
    if counts.total <= 0:
        raise AIGenerationError("At least one test case must be requested")

    context = (
        endpoint
        if isinstance(endpoint, EndpointContext)
        else endpoint_context_from_model(endpoint)
    )
    system_prompt, user_prompt = build_generation_prompt(context, counts)
    collected: dict[str, dict[str, Any]] = {}
    total_rejected = 0
    total_raw = 0
    all_errors: list[str] = []

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        if len(collected) >= counts.total:
            break

        if attempt == 0:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        else:
            remaining = counts.total - len(collected)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_retry_prompt(
                    context,
                    counts,
                    list(collected.keys()),
                    remaining,
                )},
            ]

        raw_content = call_llm(messages, client=client)
        raw_items = extract_json_array(raw_content)
        total_raw += len(raw_items)
        validation = validate_test_case_candidates(
            raw_items,
            endpoint=context,
            require_at_least_one=False,
        )
        total_rejected += validation.rejected_count
        all_errors.extend(validation.errors)

        for case in validation.valid_cases:
            collected.setdefault(case["name"], case)

    valid_cases = list(collected.values())[: counts.total]
    if not valid_cases:
        detail = "; ".join(all_errors[:5])
        if len(all_errors) > 5:
            detail = f"{detail}; ...and {len(all_errors) - 5} more"
        raise LLMOutputValidationError(
            f"No valid test cases in LLM output ({total_rejected} rejected): {detail}"
        )

    return GeneratedTestCases(
        cases=valid_cases,
        rejected_count=total_rejected,
        requested_count=counts.total,
        raw_count=total_raw,
    )


def save_draft_test_cases(
    session: Session,
    project_id: uuid.UUID,
    api_endpoint_id: uuid.UUID,
    candidates: list[dict[str, Any]],
) -> list[TestCase]:
    """Persist validated AI candidates as draft test cases."""
    if not candidates:
        return []

    saved_cases: list[TestCase] = []
    for item in candidates:
        test_case = TestCase(
            project_id=project_id,
            name=item["name"],
            description=item.get("description"),
            priority=item["priority"],
            status="draft",
            request_json=item["request_json"],
            assertions_json=item["assertions_json"],
            api_endpoint_id=api_endpoint_id,
        )
        session.add(test_case)
        saved_cases.append(test_case)

    session.commit()
    for test_case in saved_cases:
        session.refresh(test_case)
    return saved_cases


def generation_counts_from_dict(payload: dict[str, Any]) -> GenerationCounts:
    return GenerationCounts(
        positive_count=int(payload.get("positive_count", 0)),
        boundary_count=int(payload.get("boundary_count", 0)),
        exception_count=int(payload.get("exception_count", 0)),
        auth_count=int(payload.get("auth_count", 0)),
    )


def attach_api_endpoint_id(
    candidates: list[dict[str, Any]],
    api_endpoint_id: uuid.UUID,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in candidates:
        merged = dict(item)
        merged["api_endpoint_id"] = str(api_endpoint_id)
        enriched.append(merged)
    return enriched
