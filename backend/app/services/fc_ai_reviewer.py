import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import get_settings
from app.schemas.fc_generation import FcAIReviewReport
from app.services.ai_generator import (
    LLMCallError,
    LLMConfigurationError,
    LLMOutputValidationError,
    LLMResponseParseError,
    call_llm,
)

SYSTEM_PROMPT = """You are a senior software test architect reviewing functional test case coverage.
Return ONLY one JSON object. Do not include markdown or explanations.
The object must match this shape:
{
  "coverage_score": 85.5,
  "dimension_scores": {
    "positive": 90,
    "negative": 85,
    "boundary": 80,
    "permission": 88,
    "security": 82,
    "compatibility": 78
  },
  "feature_checklist": [
    {"feature": "用户登录", "covered": true, "case_count": 5}
  ],
  "gaps": ["缺少支付超时异常场景"],
  "suggestions": ["建议补充并发下单边界用例"],
  "passed": true
}
Score each dimension from 0 to 100 based on requirement coverage by generated cases."""

DIMENSION_WEIGHTS: dict[str, float] = {
    "positive": 0.25,
    "negative": 0.20,
    "boundary": 0.15,
    "permission": 0.15,
    "security": 0.15,
    "compatibility": 0.10,
}

JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
MAX_REVIEW_ATTEMPTS = 3


class FcAIReviewError(Exception):
    """Base error for functional test case AI review."""


@dataclass(frozen=True)
class FcReviewInput:
    parsed_text: str
    generated_cases: list[dict[str, Any]]


class ChatCompletionClient(Protocol):
    class Chat:
        class Completions:
            def create(self, **kwargs: Any) -> Any: ...

        completions: Completions

    chat: Chat


def compute_coverage_score(dimension_scores: dict[str, float]) -> float:
    """Compute weighted coverage score from dimension scores."""
    total = 0.0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        total += float(dimension_scores.get(dimension, 0.0)) * weight
    return round(total, 1)


def apply_coverage_gate(report: FcAIReviewReport, *, threshold: float | None = None) -> FcAIReviewReport:
    """Recompute coverage score and passed flag using service-layer weighting."""
    settings = get_settings()
    gate = threshold if threshold is not None else settings.fc_coverage_threshold
    computed_score = compute_coverage_score(report.dimension_scores)
    return report.model_copy(
        update={
            "coverage_score": computed_score,
            "passed": computed_score >= gate,
        }
    )


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise LLMResponseParseError("LLM response is empty")

    candidates = [text]
    candidates.extend(block.strip() for block in JSON_FENCE_PATTERN.findall(text) if block.strip())

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    detail = str(last_error) if last_error else "no JSON object found"
    raise LLMResponseParseError(f"Unable to parse LLM response as JSON object: {detail}")


def build_fc_review_prompt(review_input: FcReviewInput) -> tuple[str, str]:
    sections = [
        "Review the generated functional test cases against the requirement document.",
        "Requirement document:",
        review_input.parsed_text,
        "Generated test cases:",
        json.dumps(review_input.generated_cases, ensure_ascii=False),
        "Rules:",
        "- Return one JSON object only.",
        "- dimension_scores must include positive, negative, boundary, permission, security, compatibility.",
        "- feature_checklist should list major features from the requirement and whether they are covered.",
        "- gaps and suggestions must be concise Chinese strings when the requirement is Chinese.",
    ]
    return SYSTEM_PROMPT, "\n".join(sections)


def validate_fc_review_report(raw_report: dict[str, Any]) -> FcAIReviewReport:
    try:
        report = FcAIReviewReport.model_validate(raw_report)
    except ValidationError as exc:
        raise LLMOutputValidationError(f"Invalid review report from LLM: {exc}") from exc
    return apply_coverage_gate(report)


def _resolve_fc_models() -> tuple[str, str]:
    settings = get_settings()
    primary = settings.ai_fc_model or settings.ai_model
    fallback = settings.ai_fc_fallback_model or settings.ai_fallback_model
    return primary, fallback


def review_functional_test_cases(
    review_input: FcReviewInput,
    *,
    client: ChatCompletionClient | None = None,
) -> dict[str, Any]:
    """Review generated cases and return a structured coverage report."""
    if not review_input.parsed_text.strip():
        raise FcAIReviewError("Requirement document text is empty")
    if not review_input.generated_cases:
        raise FcAIReviewError("Generated test cases are empty")

    system_prompt, user_prompt = build_fc_review_prompt(review_input)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    primary_model, fallback_model = _resolve_fc_models()

    last_error: Exception | None = None
    for _ in range(MAX_REVIEW_ATTEMPTS):
        try:
            raw_content = call_llm(
                messages,
                client=client,
                primary_model=primary_model,
                fallback_model=fallback_model,
            )
            raw_report = _extract_json_object(raw_content)
            report = validate_fc_review_report(raw_report)
            return report.to_storage_dict()
        except (LLMResponseParseError, LLMOutputValidationError) as exc:
            last_error = exc
            continue
        except (LLMCallError, LLMConfigurationError):
            raise

    detail = str(last_error) if last_error else "unknown review validation error"
    raise LLMOutputValidationError(f"Unable to produce valid review report: {detail}")


__all__ = [
    "DIMENSION_WEIGHTS",
    "FcAIReviewError",
    "FcReviewInput",
    "apply_coverage_gate",
    "build_fc_review_prompt",
    "compute_coverage_score",
    "review_functional_test_cases",
    "validate_fc_review_report",
]
