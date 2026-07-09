import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.config import get_settings
from app.schemas.fc_generation import FcAIGeneratedCaseCandidate
from app.services.ai_generator import (
    AIGenerationError,
    LLMCallError,
    LLMConfigurationError,
    LLMOutputValidationError,
    LLMResponseParseError,
    call_llm,
    extract_json_array,
)

SYSTEM_PROMPT = """You are a senior software test engineer with 12 years of experience.
Generate high-quality functional test cases from product requirement documents.
Return ONLY a JSON array. Do not include markdown or explanations.
Each item must match this shape:
{
  "case_no": "FC-001",
  "module": "功能模块名",
  "title": "用例标题",
  "preconditions": "前置条件或 null",
  "steps": "1. 步骤一\\n2. 步骤二",
  "expected_result": "预期结果",
  "priority": "P0|P1|P2|P3",
  "case_type": "positive|negative|boundary|permission|security|compatibility"
}
Cover positive, negative, boundary, permission, security, and compatibility scenarios.
Use concise Chinese unless the requirement document is in English."""


class FcAIGenerationError(AIGenerationError):
    """Base error for functional test case AI generation."""


@dataclass(frozen=True)
class ExperienceCaseContext:
    id: uuid.UUID
    module: str
    title: str
    preconditions: str | None
    steps: str
    expected_result: str
    priority: str
    case_type: str


@dataclass(frozen=True)
class FcGenerationInput:
    parsed_text: str
    experience_cases: list[ExperienceCaseContext]
    user_feedback: str | None = None
    review_suggestions: str | None = None


@dataclass(frozen=True)
class FcCandidateValidationResult:
    valid_cases: list[dict[str, Any]]
    rejected_count: int
    errors: list[str]


@dataclass(frozen=True)
class GeneratedFcTestCases:
    cases: list[dict[str, Any]]
    rejected_count: int
    raw_count: int


class ChatCompletionClient(Protocol):
    class Chat:
        class Completions:
            def create(self, **kwargs: Any) -> Any: ...

        completions: Completions

    chat: Chat


MAX_GENERATION_ATTEMPTS = 3


def _serialize_experience_cases(cases: list[ExperienceCaseContext]) -> list[dict[str, Any]]:
    return [
        {
            "module": case.module,
            "title": case.title,
            "preconditions": case.preconditions,
            "steps": case.steps,
            "expected_result": case.expected_result,
            "priority": case.priority,
            "case_type": case.case_type,
        }
        for case in cases
    ]


def build_fc_generation_prompt(generation_input: FcGenerationInput) -> tuple[str, str]:
    """Build system and user prompts for functional test case generation."""
    sections = [
        "Generate comprehensive functional test cases from the requirement document below.",
        "Requirement document:",
        generation_input.parsed_text,
        "Rules:",
        "- Return a JSON array only.",
        "- Cover positive, negative, boundary, permission, security, and compatibility scenarios.",
        "- Each case must include module, title, steps, expected_result, priority, and case_type.",
        "- Use unique case_no values when provided; otherwise use FC-001, FC-002, ...",
        "- Steps may use numbered lines separated by \\n.",
    ]

    if generation_input.experience_cases:
        sections.extend(
            [
                "Reference experience cases (learn style and coverage depth, do not copy verbatim):",
                json.dumps(
                    _serialize_experience_cases(generation_input.experience_cases),
                    ensure_ascii=False,
                ),
            ]
        )

    if generation_input.user_feedback:
        sections.extend(
            [
                "User review feedback from the previous round (must address):",
                generation_input.user_feedback,
            ]
        )

    if generation_input.review_suggestions:
        sections.extend(
            [
                "Reviewer suggestions for improvement (must address):",
                generation_input.review_suggestions,
            ]
        )

    return SYSTEM_PROMPT, "\n".join(sections)


def build_fc_retry_prompt(
    generation_input: FcGenerationInput,
    existing_case_nos: list[str],
) -> str:
    return (
        "Previous generation did not produce enough valid functional test cases.\n"
        f"Do not reuse these case_no values: {json.dumps(existing_case_nos, ensure_ascii=False)}\n"
        "Generate additional unique functional test cases.\n"
        f"Requirement document:\n{generation_input.parsed_text}\n"
        "Return a JSON array only."
    )


def validate_fc_case_candidate(
    item: dict[str, Any],
    *,
    default_case_no: str | None = None,
) -> dict[str, Any]:
    candidate = FcAIGeneratedCaseCandidate.model_validate(item)
    return candidate.to_storage_dict(default_case_no=default_case_no)


def validate_fc_case_candidates(
    items: list[dict[str, Any]],
    *,
    require_at_least_one: bool = True,
) -> FcCandidateValidationResult:
    valid_cases: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, item in enumerate(items):
        try:
            if not isinstance(item, dict):
                raise ValueError("case must be a JSON object")
            default_case_no = f"FC-{index + 1:03d}"
            valid_cases.append(
                validate_fc_case_candidate(item, default_case_no=default_case_no)
            )
        except (ValidationError, ValueError) as exc:
            label = item.get("title") if isinstance(item, dict) else None
            prefix = f"case[{index}]"
            if label:
                prefix = f'{prefix} "{label}"'
            errors.append(f"{prefix}: {exc}")

    if require_at_least_one and items and not valid_cases:
        detail = "; ".join(errors[:5])
        if len(errors) > 5:
            detail = f"{detail}; ...and {len(errors) - 5} more"
        raise LLMOutputValidationError(
            f"No valid functional test cases in LLM output ({len(items)} rejected): {detail}"
        )

    return FcCandidateValidationResult(
        valid_cases=valid_cases,
        rejected_count=len(errors),
        errors=errors,
    )


def _resolve_fc_models() -> tuple[str, str]:
    settings = get_settings()
    primary = settings.ai_fc_model or settings.ai_model
    fallback = settings.ai_fc_fallback_model or settings.ai_fallback_model
    return primary, fallback


def generate_functional_test_cases(
    generation_input: FcGenerationInput,
    *,
    client: ChatCompletionClient | None = None,
) -> GeneratedFcTestCases:
    """Generate validated functional test case candidates from requirement text via LLM."""
    if not generation_input.parsed_text.strip():
        raise FcAIGenerationError("Requirement document text is empty")

    system_prompt, user_prompt = build_fc_generation_prompt(generation_input)
    collected: dict[str, dict[str, Any]] = {}
    total_rejected = 0
    total_raw = 0
    all_errors: list[str] = []

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        if attempt == 0:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": build_fc_retry_prompt(
                        generation_input,
                        list(collected.keys()),
                    ),
                },
            ]

        primary_model, fallback_model = _resolve_fc_models()
        raw_content = call_llm(
            messages,
            client=client,
            primary_model=primary_model,
            fallback_model=fallback_model,
        )
        raw_items = extract_json_array(raw_content)
        total_raw += len(raw_items)
        validation = validate_fc_case_candidates(raw_items, require_at_least_one=False)
        total_rejected += validation.rejected_count
        all_errors.extend(validation.errors)

        for case in validation.valid_cases:
            collected.setdefault(case["case_no"], case)

        if collected:
            break

    valid_cases = list(collected.values())
    if not valid_cases:
        detail = "; ".join(all_errors[:5])
        if len(all_errors) > 5:
            detail = f"{detail}; ...and {len(all_errors) - 5} more"
        raise LLMOutputValidationError(
            f"No valid functional test cases in LLM output ({total_rejected} rejected): {detail}"
        )

    return GeneratedFcTestCases(
        cases=valid_cases,
        rejected_count=total_rejected,
        raw_count=total_raw,
    )


__all__ = [
    "ExperienceCaseContext",
    "FcAIGenerationError",
    "FcGenerationInput",
    "GeneratedFcTestCases",
    "build_fc_generation_prompt",
    "generate_functional_test_cases",
    "validate_fc_case_candidates",
]
