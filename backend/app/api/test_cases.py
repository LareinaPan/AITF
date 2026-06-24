import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.api_endpoints import get_api_endpoint_or_404
from app.api.projects import get_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.test_case import DEFAULT_ASSERTIONS_JSON, DEFAULT_REQUEST_JSON, TestCase
from app.models.user import User
from app.schemas.test_case import (
    AssertionCheckResponse,
    AssertionsEvaluationResponse,
    HttpResponseResponse,
    PreparedRequestResponse,
    TestCaseCreateRequest,
    TestCaseResponse,
    TestCaseRunRequest,
    TestCaseRunResponse,
    TestCaseUpdateRequest,
)
from app.services.test_runner import (
    EnvironmentNotFoundError,
    SingleRunResult,
    TestCaseNotFoundError,
    TestRunner,
)
from app.services.variable_resolver import MissingVariableError

router = APIRouter()


def _to_run_response(result: SingleRunResult) -> TestCaseRunResponse:
    response = None
    if result.response is not None:
        response = HttpResponseResponse(
            status_code=result.response.status_code,
            body=result.response.body,
            elapsed_ms=result.response.elapsed_ms,
        )

    assertions = None
    if result.assertions is not None:
        assertions = AssertionsEvaluationResponse(
            passed=result.assertions.passed,
            checks=[
                AssertionCheckResponse(
                    name=check.name,
                    passed=check.passed,
                    message=check.message,
                    rule_type=check.rule_type,
                )
                for check in result.assertions.checks
            ],
        )

    prepared = result.prepared_request
    return TestCaseRunResponse(
        case_id=result.case_id,
        case_name=result.case_name,
        environment_id=result.environment_id,
        environment_name=result.environment_name,
        passed=result.passed,
        error=result.error,
        prepared_request=PreparedRequestResponse(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            body_type=prepared.body_type,
            body_content=prepared.body_content,
        ),
        response=response,
        assertions=assertions,
    )


def get_test_case_or_404(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session,
) -> TestCase:
    test_case = db.get(TestCase, case_id)
    if test_case is None or test_case.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found",
        )
    return test_case


@router.get("", response_model=list[TestCaseResponse])
def list_test_cases(
    project_id: uuid.UUID,
    api_endpoint_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TestCase]:
    get_project_or_404(project_id, db)
    if api_endpoint_id is not None:
        get_api_endpoint_or_404(project_id, api_endpoint_id, db)

    query = select(TestCase).where(TestCase.project_id == project_id)
    if api_endpoint_id is not None:
        query = query.where(TestCase.api_endpoint_id == api_endpoint_id)

    return list(db.scalars(query.order_by(TestCase.created_at.desc())).all())


@router.post("", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_test_case(
    project_id: uuid.UUID,
    payload: TestCaseCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestCase:
    get_project_or_404(project_id, db)
    if payload.api_endpoint_id is not None:
        get_api_endpoint_or_404(project_id, payload.api_endpoint_id, db)

    request_json = (
        payload.request_json.model_dump()
        if payload.request_json is not None
        else DEFAULT_REQUEST_JSON.copy()
    )
    assertions_json = (
        payload.assertions_json.model_dump()
        if payload.assertions_json is not None
        else DEFAULT_ASSERTIONS_JSON.copy()
    )

    test_case = TestCase(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        request_json=request_json,
        assertions_json=assertions_json,
        api_endpoint_id=payload.api_endpoint_id,
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    return test_case


@router.get("/{case_id}", response_model=TestCaseResponse)
def get_test_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestCase:
    get_project_or_404(project_id, db)
    return get_test_case_or_404(project_id, case_id, db)


@router.put("/{case_id}", response_model=TestCaseResponse)
def update_test_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: TestCaseUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestCase:
    get_project_or_404(project_id, db)
    test_case = get_test_case_or_404(project_id, case_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    if "api_endpoint_id" in update_data and update_data["api_endpoint_id"] is not None:
        get_api_endpoint_or_404(project_id, update_data["api_endpoint_id"], db)

    for field, value in update_data.items():
        setattr(test_case, field, value)

    db.commit()
    db.refresh(test_case)
    return test_case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_project_or_404(project_id, db)
    test_case = get_test_case_or_404(project_id, case_id, db)
    db.delete(test_case)
    db.commit()


@router.post("/{case_id}/confirm", response_model=TestCaseResponse)
def confirm_test_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestCase:
    get_project_or_404(project_id, db)
    test_case = get_test_case_or_404(project_id, case_id, db)

    if test_case.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft test cases can be confirmed",
        )

    test_case.status = "active"
    db.commit()
    db.refresh(test_case)
    return test_case


@router.post("/{case_id}/run", response_model=TestCaseRunResponse)
def run_test_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: TestCaseRunRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TestCaseRunResponse:
    get_project_or_404(project_id, db)
    get_test_case_or_404(project_id, case_id, db)

    runner = TestRunner(db)
    try:
        result = runner.run_single(case_id, payload.environment_id)
    except TestCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except EnvironmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MissingVariableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _to_run_response(result)
