import pytest
from pydantic import ValidationError

from app.schemas.ai_generation import AIGeneratedTestCaseCandidate
from app.services.ai_generator import (
    LLMOutputValidationError,
    normalize_llm_candidate,
    validate_test_case_candidate,
    validate_test_case_candidates,
)
from app.services.ai_generator import EndpointContext

VALID_CASE = {
    "name": "Create user success",
    "description": "Valid payload",
    "priority": "P1",
    "request_json": {
        "method": "post",
        "url": "{{base_url}}/api/users",
        "headers": [{"key": "Content-Type", "value": "application/json"}],
        "query": [],
        "body": {"type": "json", "content": '{"name":"demo"}'},
    },
    "assertions_json": {
        "status_code": 201,
        "max_response_time_ms": 3000,
        "body_rules": [{"type": "contains", "value": "id"}],
    },
}


def test_validate_test_case_candidate_accepts_valid_payload() -> None:
    validated = validate_test_case_candidate(VALID_CASE)
    assert validated["name"] == "Create user success"
    assert validated["request_json"]["method"] == "POST"
    assert validated["assertions_json"]["status_code"] == 201


def test_validate_test_case_candidate_rejects_invalid_priority() -> None:
    payload = {**VALID_CASE, "priority": "P9"}
    with pytest.raises(ValidationError):
        validate_test_case_candidate(payload)


def test_validate_test_case_candidate_rejects_empty_name() -> None:
    payload = {**VALID_CASE, "name": "   "}
    with pytest.raises(ValidationError):
        validate_test_case_candidate(payload)


def test_validate_test_case_candidate_rejects_invalid_method() -> None:
    payload = {
        **VALID_CASE,
        "request_json": {**VALID_CASE["request_json"], "method": "TRACE"},
    }
    with pytest.raises(ValidationError):
        validate_test_case_candidate(payload)


def test_validate_test_case_candidate_rejects_invalid_body_rule() -> None:
    payload = {
        **VALID_CASE,
        "assertions_json": {
            **VALID_CASE["assertions_json"],
            "body_rules": [{"type": "json_path", "path": "$.code"}],
        },
    }
    with pytest.raises(ValidationError):
        validate_test_case_candidate(payload)


def test_normalize_llm_candidate_fixes_json_path_body_rule() -> None:
    endpoint = EndpointContext(
        method="POST",
        path="/api/users",
        summary=None,
        description=None,
        parameters_json=[],
        request_body_json=None,
        responses_json={},
    )
    payload = {
        **VALID_CASE,
        "assertions_json": {
            **VALID_CASE["assertions_json"],
            "body_rules": [{"type": "json_path", "path": "$.code", "expected": "0"}],
        },
    }
    normalized = normalize_llm_candidate(payload, endpoint)
    validated = validate_test_case_candidate(normalized, endpoint)
    assert validated["assertions_json"]["body_rules"][0]["operator"] == "eq"


def test_normalize_llm_candidate_fixes_relative_url() -> None:
    endpoint = EndpointContext(
        method="GET",
        path="/api/users",
        summary=None,
        description=None,
        parameters_json=[],
        request_body_json=None,
        responses_json={},
    )
    payload = {
        **VALID_CASE,
        "request_json": {**VALID_CASE["request_json"], "url": "/api/users", "method": "get"},
    }
    normalized = normalize_llm_candidate(payload, endpoint)
    assert normalized["request_json"]["url"] == "{{base_url}}/api/users"
    assert normalized["request_json"]["method"] == "GET"


def test_normalize_llm_candidate_strips_absolute_url_host() -> None:
    endpoint = EndpointContext(
        method="GET",
        path="/api/users",
        summary=None,
        description=None,
        parameters_json=[],
        request_body_json=None,
        responses_json={},
    )
    payload = {
        **VALID_CASE,
        "request_json": {
            **VALID_CASE["request_json"],
            "url": "http://host.docker.internal:8001/api/users",
            "method": "get",
        },
    }
    normalized = normalize_llm_candidate(payload, endpoint)
    assert normalized["request_json"]["url"] == "{{base_url}}/api/users"


def test_validate_test_case_candidates_skips_invalid_items() -> None:
    invalid = {**VALID_CASE, "priority": "P9"}
    result = validate_test_case_candidates(
        [VALID_CASE, invalid, VALID_CASE],
        require_at_least_one=False,
    )

    assert len(result.valid_cases) == 2
    assert result.rejected_count == 1
    assert len(result.errors) == 1


def test_validate_test_case_candidates_raises_when_all_invalid() -> None:
    invalid = {**VALID_CASE, "name": ""}
    with pytest.raises(LLMOutputValidationError) as exc_info:
        validate_test_case_candidates([invalid])

    assert "No valid test cases" in str(exc_info.value)


def test_ai_generated_test_case_candidate_json_path_rule() -> None:
    payload = {
        **VALID_CASE,
        "assertions_json": {
            **VALID_CASE["assertions_json"],
            "body_rules": [
                {
                    "type": "json_path",
                    "path": "$.code",
                    "operator": "eq",
                    "expected": "0",
                }
            ],
        },
    }
    candidate = AIGeneratedTestCaseCandidate.model_validate(payload)
    assert candidate.assertions_json.body_rules[0].path == "$.code"
