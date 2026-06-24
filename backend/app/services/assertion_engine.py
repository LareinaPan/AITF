import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssertionCheckResult:
    name: str
    passed: bool
    message: str
    rule_type: str | None = None


@dataclass(frozen=True)
class AssertionsEvaluationResult:
    passed: bool
    checks: list[AssertionCheckResult]


def extract_json_path(data: Any, path: str) -> Any:
    """Extract a value using a simple `$.a.b` JSONPath subset."""
    normalized = path.strip()
    if not normalized.startswith("$."):
        raise ValueError(f"Unsupported JSONPath: {path}")

    current: Any = data
    for part in normalized[2:].split("."):
        key = part.strip()
        if key == "":
            raise ValueError(f"Unsupported JSONPath: {path}")
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _values_equal(actual: Any, expected: str) -> bool:
    if actual is None:
        return expected in {"", "null", "None"}
    return str(actual) == expected


def evaluate_status_code(expected: int, actual: int) -> AssertionCheckResult:
    passed = expected == actual
    return AssertionCheckResult(
        name="status_code",
        passed=passed,
        message=(
            f"Expected status code {expected}, got {actual}"
            if not passed
            else f"Status code is {actual}"
        ),
        rule_type="status_code",
    )


def evaluate_response_time(max_ms: int, elapsed_ms: float) -> AssertionCheckResult:
    passed = elapsed_ms <= max_ms
    return AssertionCheckResult(
        name="max_response_time_ms",
        passed=passed,
        message=(
            f"Response time {elapsed_ms:.2f}ms exceeds limit {max_ms}ms"
            if not passed
            else f"Response time {elapsed_ms:.2f}ms within limit {max_ms}ms"
        ),
        rule_type="response_time",
    )


def evaluate_body_rule(rule: dict[str, Any], response_body: str) -> AssertionCheckResult:
    rule_type = rule.get("type")

    if rule_type == "contains":
        expected = str(rule.get("value", ""))
        passed = expected in response_body
        return AssertionCheckResult(
            name="body_contains",
            passed=passed,
            message=(
                f'Response body does not contain "{expected}"'
                if not passed
                else f'Response body contains "{expected}"'
            ),
            rule_type="contains",
        )

    if rule_type == "json_path":
        path = str(rule.get("path", "")).strip()
        operator = str(rule.get("operator", "eq")).strip()
        expected = str(rule.get("expected", ""))

        if operator != "eq":
            return AssertionCheckResult(
                name="body_json_path",
                passed=False,
                message=f'Unsupported JSONPath operator: {operator}',
                rule_type="json_path",
            )

        try:
            parsed_body = json.loads(response_body) if response_body else None
        except json.JSONDecodeError:
            return AssertionCheckResult(
                name="body_json_path",
                passed=False,
                message="Response body is not valid JSON",
                rule_type="json_path",
            )

        try:
            actual = extract_json_path(parsed_body, path)
        except ValueError as exc:
            return AssertionCheckResult(
                name="body_json_path",
                passed=False,
                message=str(exc),
                rule_type="json_path",
            )

        passed = _values_equal(actual, expected)
        actual_display = "null" if actual is None else str(actual)
        return AssertionCheckResult(
            name="body_json_path",
            passed=passed,
            message=(
                f'JSONPath "{path}" expected "{expected}", got "{actual_display}"'
                if not passed
                else f'JSONPath "{path}" equals "{expected}"'
            ),
            rule_type="json_path",
        )

    return AssertionCheckResult(
        name="body_rule",
        passed=False,
        message=f"Unsupported body rule type: {rule_type}",
        rule_type=str(rule_type) if rule_type is not None else None,
    )


def evaluate_body_rules(
    rules: list[dict[str, Any]],
    response_body: str,
) -> list[AssertionCheckResult]:
    return [evaluate_body_rule(rule, response_body) for rule in rules]


def evaluate_assertions(
    assertions_json: dict[str, Any],
    *,
    response_status_code: int,
    response_body: str,
    elapsed_ms: float,
) -> AssertionsEvaluationResult:
    checks: list[AssertionCheckResult] = []

    status_code = int(assertions_json.get("status_code", 200))
    checks.append(evaluate_status_code(status_code, response_status_code))

    max_response_time_ms = int(assertions_json.get("max_response_time_ms", 3000))
    checks.append(evaluate_response_time(max_response_time_ms, elapsed_ms))

    body_rules = assertions_json.get("body_rules", [])
    if isinstance(body_rules, list):
        checks.extend(evaluate_body_rules(body_rules, response_body))

    passed = all(check.passed for check in checks)
    return AssertionsEvaluationResult(passed=passed, checks=checks)
