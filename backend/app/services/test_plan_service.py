import uuid

from app.models.test_case import TestCase

PLAN_CASE_MAX_COUNT = 500


class PlanCaseBindingError(ValueError):
    """Raised when plan case binding violates business rules."""


def resolve_new_case_ids(
    payload_case_ids: list[uuid.UUID],
    existing_case_ids: set[uuid.UUID],
) -> list[uuid.UUID]:
    seen_in_request: set[uuid.UUID] = set()
    new_case_ids: list[uuid.UUID] = []
    for case_id in payload_case_ids:
        if case_id in seen_in_request:
            continue
        seen_in_request.add(case_id)
        if case_id in existing_case_ids:
            continue
        new_case_ids.append(case_id)
    return new_case_ids


def validate_plan_case_capacity(existing_count: int, new_count: int) -> None:
    if existing_count + new_count > PLAN_CASE_MAX_COUNT:
        raise PlanCaseBindingError(
            f"A test plan can contain at most {PLAN_CASE_MAX_COUNT} cases",
        )


def validate_cases_are_active(test_cases: list[TestCase]) -> None:
    inactive = [case for case in test_cases if case.status != "active"]
    if not inactive:
        return

    if len(inactive) == 1:
        case = inactive[0]
        raise PlanCaseBindingError(
            f"Only active test cases can be bound (case '{case.name}' is {case.status})",
        )

    names = ", ".join(f"'{case.name}'" for case in inactive[:3])
    suffix = "" if len(inactive) <= 3 else f" and {len(inactive) - 3} more"
    raise PlanCaseBindingError(
        f"Only active test cases can be bound ({len(inactive)} inactive: {names}{suffix})",
    )
