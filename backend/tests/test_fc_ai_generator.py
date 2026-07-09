import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.fc_ai_generator import (
    ExperienceCaseContext,
    FcGenerationInput,
    build_fc_generation_prompt,
    generate_functional_test_cases,
    validate_fc_case_candidates,
)
from app.services.ai_generator import LLMOutputValidationError, LLMResponseParseError

SAMPLE_FC_CASES = [
    {
        "case_no": "FC-001",
        "module": "用户登录",
        "title": "正确密码登录",
        "preconditions": "用户已注册",
        "steps": "1. 打开登录页\n2. 输入账号密码",
        "expected_result": "登录成功",
        "priority": "P0",
        "case_type": "positive",
    },
    {
        "module": "用户登录",
        "title": "错误密码登录",
        "steps": "1. 输入错误密码",
        "expected_result": "提示密码错误",
        "priority": "P1",
        "case_type": "negative",
    },
]

SAMPLE_EXPERIENCE_CASE = ExperienceCaseContext(
    id=uuid.uuid4(),
    module="用户登录",
    title="历史登录用例",
    preconditions="已注册",
    steps="1. 登录",
    expected_result="成功",
    priority="P1",
    case_type="positive",
)


def test_build_fc_generation_prompt_includes_requirement_and_experience() -> None:
    generation_input = FcGenerationInput(
        parsed_text="用户登录模块需求说明",
        experience_cases=[SAMPLE_EXPERIENCE_CASE],
        user_feedback="请补充边界场景",
    )

    system_prompt, user_prompt = build_fc_generation_prompt(generation_input)

    assert "senior software test engineer" in system_prompt
    assert "用户登录模块需求说明" in user_prompt
    assert "历史登录用例" in user_prompt
    assert "请补充边界场景" in user_prompt


def test_validate_fc_case_candidates_accepts_valid_items() -> None:
    result = validate_fc_case_candidates(SAMPLE_FC_CASES)

    assert len(result.valid_cases) == 2
    assert result.rejected_count == 0
    assert result.valid_cases[0]["case_no"] == "FC-001"
    assert result.valid_cases[1]["case_no"] == "FC-002"


def test_validate_fc_case_candidates_raises_when_all_invalid() -> None:
    with pytest.raises(LLMOutputValidationError):
        validate_fc_case_candidates([{"title": "missing fields"}])


def test_generate_functional_test_cases_with_mock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(SAMPLE_FC_CASES, ensure_ascii=False))
            )
        ]
    )

    result = generate_functional_test_cases(
        FcGenerationInput(
            parsed_text="登录模块需求",
            experience_cases=[SAMPLE_EXPERIENCE_CASE],
        ),
        client=mock_client,
    )

    assert len(result.cases) == 2
    assert result.cases[0]["module"] == "用户登录"
    assert result.raw_count == 2


def test_generate_functional_test_cases_retries_on_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='[{"title":"bad"}]'))]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(SAMPLE_FC_CASES, ensure_ascii=False))
                )
            ]
        ),
    ]

    result = generate_functional_test_cases(
        FcGenerationInput(parsed_text="登录模块需求", experience_cases=[]),
        client=mock_client,
    )

    assert len(result.cases) == 2
    assert mock_client.chat.completions.create.call_count == 2


def test_generate_functional_test_cases_raises_on_empty_requirement() -> None:
    with pytest.raises(Exception, match="empty"):
        generate_functional_test_cases(
            FcGenerationInput(parsed_text="   ", experience_cases=[]),
            client=MagicMock(),
        )
