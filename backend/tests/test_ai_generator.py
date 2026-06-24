import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ai_generator import (
    AIGenerationError,
    EndpointContext,
    GenerationCounts,
    LLMCallError,
    LLMConfigurationError,
    LLMOutputValidationError,
    LLMResponseParseError,
    GeneratedTestCases,
    attach_api_endpoint_id,
    build_generation_prompt,
    call_llm,
    extract_json_array,
    generate_test_case_candidates,
    validate_test_case_candidates,
)


SAMPLE_ENDPOINT = EndpointContext(
    method="POST",
    path="/api/users",
    summary="Create user",
    description="Create a new user account",
    parameters_json=[{"name": "page", "in": "query"}],
    request_body_json={
        "content": {"application/json": {"schema": {"type": "object"}}},
    },
    responses_json={"201": {"description": "Created"}},
)

SAMPLE_LLM_CASES = [
    {
        "name": "Create user success",
        "description": "Valid payload",
        "priority": "P1",
        "request_json": {
            "method": "POST",
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
]


def test_build_generation_prompt_includes_endpoint_and_counts() -> None:
    counts = GenerationCounts(
        positive_count=2,
        boundary_count=1,
        exception_count=1,
        auth_count=0,
    )

    system_prompt, user_prompt = build_generation_prompt(SAMPLE_ENDPOINT, counts)

    assert "JSON array" in system_prompt
    assert "POST" in user_prompt
    assert "/api/users" in user_prompt
    assert '"positive": 2' in user_prompt
    assert '"boundary": 1' in user_prompt
    assert '"exception": 1' in user_prompt
    assert '"total": 4' in user_prompt
    assert "Create user" in user_prompt


def test_extract_json_array_from_plain_json() -> None:
    content = json.dumps(SAMPLE_LLM_CASES)
    parsed = extract_json_array(content)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Create user success"


def test_extract_json_array_from_markdown_fence() -> None:
    content = f"Here are cases:\n```json\n{json.dumps(SAMPLE_LLM_CASES)}\n```"
    parsed = extract_json_array(content)
    assert parsed[0]["priority"] == "P1"


def test_extract_json_array_from_wrapped_object() -> None:
    content = json.dumps({"cases": SAMPLE_LLM_CASES})
    parsed = extract_json_array(content)
    assert len(parsed) == 1


def test_extract_json_array_raises_on_invalid_content() -> None:
    with pytest.raises(LLMResponseParseError):
        extract_json_array("not-json")


def test_call_llm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='[{"name":"case"}]'))]
    )

    content = call_llm(
        [{"role": "user", "content": "generate"}],
        client=mock_client,
        primary_model="primary-model",
        fallback_model="fallback-model",
    )

    assert content == '[{"name":"case"}]'
    mock_client.chat.completions.create.assert_called_once()
    get_settings.cache_clear()


def test_call_llm_uses_fallback_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        LLMCallError("primary failed"),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='[{"name":"fallback"}]'))]
        ),
    ]

    content = call_llm(
        [{"role": "user", "content": "generate"}],
        client=mock_client,
        primary_model="primary-model",
        fallback_model="fallback-model",
    )

    assert content == '[{"name":"fallback"}]'
    assert mock_client.chat.completions.create.call_count == 2
    get_settings.cache_clear()


def test_call_llm_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.ai_generator.get_settings",
        lambda: Settings(openai_api_key=""),
    )

    with pytest.raises(LLMConfigurationError):
        call_llm([{"role": "user", "content": "generate"}])

    get_settings.cache_clear()


def test_generate_test_case_candidates_with_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(SAMPLE_LLM_CASES)))
        ]
    )

    counts = GenerationCounts(
        positive_count=1,
        boundary_count=0,
        exception_count=0,
        auth_count=0,
    )
    result = generate_test_case_candidates(
        SAMPLE_ENDPOINT,
        counts,
        client=mock_client,
    )

    assert len(result.cases) == 1
    assert result.cases[0]["request_json"]["url"] == "{{base_url}}/api/users"
    assert result.rejected_count == 0
    assert result.requested_count == 1
    get_settings.cache_clear()


def test_generate_test_case_candidates_retries_until_enough_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    case_two = {
        **SAMPLE_LLM_CASES[0],
        "name": "Create user boundary",
        "priority": "P2",
    }
    case_three = {
        **SAMPLE_LLM_CASES[0],
        "name": "Create user invalid",
        "priority": "P1",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(SAMPLE_LLM_CASES)))]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps([case_two, case_three])))
            ]
        ),
    ]

    counts = GenerationCounts(
        positive_count=2,
        boundary_count=1,
        exception_count=0,
        auth_count=0,
    )
    result = generate_test_case_candidates(SAMPLE_ENDPOINT, counts, client=mock_client)

    assert len(result.cases) == 3
    assert result.requested_count == 3
    assert mock_client.chat.completions.create.call_count == 2
    get_settings.cache_clear()


def test_generate_test_case_candidates_requires_positive_total() -> None:
    counts = GenerationCounts(
        positive_count=0,
        boundary_count=0,
        exception_count=0,
        auth_count=0,
    )
    with pytest.raises(AIGenerationError):
        generate_test_case_candidates(SAMPLE_ENDPOINT, counts, client=MagicMock())


def test_attach_api_endpoint_id() -> None:
    import uuid

    endpoint_id = uuid.uuid4()
    enriched = attach_api_endpoint_id(SAMPLE_LLM_CASES, endpoint_id)
    assert enriched[0]["api_endpoint_id"] == str(endpoint_id)


def test_generate_test_case_candidates_rejects_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    invalid_cases = [
        {
            **SAMPLE_LLM_CASES[0],
            "name": "   ",
            "request_json": {**SAMPLE_LLM_CASES[0]["request_json"], "method": "TRACE"},
        }
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(invalid_cases)))
        ]
    )

    counts = GenerationCounts(
        positive_count=1,
        boundary_count=0,
        exception_count=0,
        auth_count=0,
    )
    with pytest.raises(LLMOutputValidationError):
        generate_test_case_candidates(SAMPLE_ENDPOINT, counts, client=mock_client)

    get_settings.cache_clear()
