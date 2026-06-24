import uuid

import pytest

from app.models.test_case import TestCase
from app.services.test_plan_service import (
    PlanCaseBindingError,
    PLAN_CASE_MAX_COUNT,
    resolve_new_case_ids,
    validate_cases_are_active,
    validate_plan_case_capacity,
)


def test_resolve_new_case_ids_deduplicates_and_skips_existing() -> None:
    existing = {uuid.uuid4(), uuid.uuid4()}
    new_id = uuid.uuid4()
    duplicate_in_payload = uuid.uuid4()

    result = resolve_new_case_ids(
        [new_id, duplicate_in_payload, duplicate_in_payload, next(iter(existing))],
        existing,
    )

    assert result == [new_id, duplicate_in_payload]


def test_validate_plan_case_capacity_allows_up_to_limit() -> None:
    validate_plan_case_capacity(499, 1)
    validate_plan_case_capacity(500, 0)


def test_validate_plan_case_capacity_rejects_overflow() -> None:
    with pytest.raises(PlanCaseBindingError, match="500"):
        validate_plan_case_capacity(500, 1)

    with pytest.raises(PlanCaseBindingError, match="500"):
        validate_plan_case_capacity(499, 2)


def test_validate_cases_are_active_accepts_active_cases() -> None:
    case = TestCase(
        project_id=uuid.uuid4(),
        name="Active",
        status="active",
    )
    validate_cases_are_active([case])


def test_validate_cases_are_active_rejects_single_draft() -> None:
    case = TestCase(
        project_id=uuid.uuid4(),
        name="Draft Case",
        status="draft",
    )
    with pytest.raises(PlanCaseBindingError, match="Draft Case"):
        validate_cases_are_active([case])


def test_validate_cases_are_active_rejects_multiple_inactive() -> None:
    cases = [
        TestCase(project_id=uuid.uuid4(), name="A", status="draft"),
        TestCase(project_id=uuid.uuid4(), name="B", status="draft"),
    ]
    with pytest.raises(PlanCaseBindingError, match="2 inactive"):
        validate_cases_are_active(cases)


def test_plan_case_max_count_constant() -> None:
    assert PLAN_CASE_MAX_COUNT == 500
