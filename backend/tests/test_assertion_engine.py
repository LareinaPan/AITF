import pytest

from app.services.assertion_engine import (
    AssertionsEvaluationResult,
    evaluate_assertions,
    evaluate_body_rule,
    evaluate_response_time,
    evaluate_status_code,
    extract_json_path,
)


def test_extract_json_path_nested_value() -> None:
    data = {"code": "0", "data": {"id": 42}, "total": 2}

    assert extract_json_path(data, "$.code") == "0"
    assert extract_json_path(data, "$.data.id") == 42
    assert extract_json_path(data, "$.missing") is None
    assert extract_json_path(data, "$. total") == 2


def test_extract_json_path_invalid_format() -> None:
    with pytest.raises(ValueError, match="Unsupported JSONPath"):
        extract_json_path({"code": 0}, "code")


def test_evaluate_status_code() -> None:
    passed = evaluate_status_code(200, 200)
    failed = evaluate_status_code(200, 404)

    assert passed.passed is True
    assert failed.passed is False
    assert "404" in failed.message


def test_evaluate_response_time() -> None:
    passed = evaluate_response_time(3000, 1200.5)
    failed = evaluate_response_time(1000, 1500.0)

    assert passed.passed is True
    assert failed.passed is False


def test_evaluate_body_rule_contains() -> None:
    passed = evaluate_body_rule({"type": "contains", "value": "success"}, '{"msg":"success"}')
    failed = evaluate_body_rule({"type": "contains", "value": "error"}, '{"msg":"success"}')

    assert passed.passed is True
    assert failed.passed is False


def test_evaluate_body_rule_json_path_eq() -> None:
    body = '{"code":"0","message":"ok"}'

    passed = evaluate_body_rule(
        {
            "type": "json_path",
            "path": "$.code",
            "operator": "eq",
            "expected": "0",
        },
        body,
    )
    failed = evaluate_body_rule(
        {
            "type": "json_path",
            "path": "$.code",
            "operator": "eq",
            "expected": "1",
        },
        body,
    )

    assert passed.passed is True
    assert failed.passed is False
    assert "expected" in failed.message.lower() or "0" in failed.message


def test_evaluate_body_rule_json_path_invalid_body() -> None:
    result = evaluate_body_rule(
        {
            "type": "json_path",
            "path": "$.code",
            "operator": "eq",
            "expected": "0",
        },
        "not-json",
    )

    assert result.passed is False
    assert "JSON" in result.message


def test_evaluate_body_rule_unsupported_operator() -> None:
    result = evaluate_body_rule(
        {
            "type": "json_path",
            "path": "$.code",
            "operator": "gt",
            "expected": "0",
        },
        '{"code": 1}',
    )

    assert result.passed is False
    assert "operator" in result.message.lower()


def test_evaluate_assertions_all_pass() -> None:
    assertions_json = {
        "status_code": 200,
        "max_response_time_ms": 3000,
        "body_rules": [
            {"type": "contains", "value": "success"},
            {
                "type": "json_path",
                "path": "$.code",
                "operator": "eq",
                "expected": "0",
            },
        ],
    }

    result = evaluate_assertions(
        assertions_json,
        response_status_code=200,
        response_body='{"code":"0","message":"success"}',
        elapsed_ms=850.2,
    )

    assert isinstance(result, AssertionsEvaluationResult)
    assert result.passed is True
    assert len(result.checks) == 4
    assert all(check.passed for check in result.checks)


def test_evaluate_assertions_partial_failure() -> None:
    assertions_json = {
        "status_code": 200,
        "max_response_time_ms": 500,
        "body_rules": [{"type": "contains", "value": "missing"}],
    }

    result = evaluate_assertions(
        assertions_json,
        response_status_code=500,
        response_body='{"code":"0"}',
        elapsed_ms=1200.0,
    )

    assert result.passed is False
    failed_checks = [check for check in result.checks if not check.passed]
    assert len(failed_checks) == 3
