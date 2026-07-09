import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.fc_projects import get_fc_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.fc_generation_batch import FcGenerationBatch
from app.models.fc_requirement_doc import FcRequirementDoc
from app.models.fc_test_case import FcTestCase
from app.models.user import User
from app.schemas.fc_experience_case import FC_CASE_TYPES, FC_PRIORITIES
from app.schemas.fc_test_case import (
    FcTestCaseBatchDeleteRequest,
    FcTestCaseBatchDeleteResponse,
    FcTestCaseCreateRequest,
    FcTestCaseFilterOptionsResponse,
    FcTestCaseListResponse,
    FcTestCaseResponse,
    FcTestCaseUpdateRequest,
)

router = APIRouter()


def _to_response(case: FcTestCase) -> FcTestCaseResponse:
    return FcTestCaseResponse.model_validate(case)


def _get_case_or_404(case_id: uuid.UUID, db: Session) -> FcTestCase:
    case = db.get(FcTestCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Functional test case not found",
        )
    return case


def _ensure_case_belongs_to_project(case: FcTestCase, fc_project_id: uuid.UUID) -> None:
    if case.fc_project_id != fc_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Functional test case not found",
        )


def _validate_enums(priority: str, case_type: str) -> None:
    if priority not in FC_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid priority: {priority}",
        )
    if case_type not in FC_CASE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case_type: {case_type}",
        )


def _validate_related_ids(
    fc_project_id: uuid.UUID,
    db: Session,
    requirement_doc_id: uuid.UUID | None,
    generation_batch_id: uuid.UUID | None,
) -> None:
    if requirement_doc_id is not None:
        doc = db.get(FcRequirementDoc, requirement_doc_id)
        if doc is None or doc.fc_project_id != fc_project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid requirement_doc_id for this project",
            )

    if generation_batch_id is not None:
        batch = db.get(FcGenerationBatch, generation_batch_id)
        if batch is None or batch.fc_project_id != fc_project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid generation_batch_id for this project",
            )


def _resolve_case_no(payload: FcTestCaseCreateRequest, fc_project_id: uuid.UUID, db: Session) -> str:
    if payload.case_no:
        return payload.case_no

    count = db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(FcTestCase.fc_project_id == fc_project_id)
    ) or 0
    return f"FC-{count + 1:03d}"


def _validate_list_filters(
    status_filter: str | None,
    case_type: str | None,
) -> None:
    if status_filter is not None and status_filter not in {"draft", "active"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter",
        )
    if case_type is not None and case_type not in FC_CASE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid case_type filter: {case_type}",
        )


def _apply_test_case_list_filters(
    query,
    *,
    status_filter: str | None,
    module: str | None,
    case_type: str | None,
    generation_batch_id: uuid.UUID | None,
    no_batch: bool,
):
    if status_filter is not None:
        query = query.where(FcTestCase.status == status_filter)
    if module is not None:
        query = query.where(FcTestCase.module == module.strip())
    if case_type is not None:
        query = query.where(FcTestCase.case_type == case_type)
    if no_batch:
        query = query.where(FcTestCase.generation_batch_id.is_(None))
    elif generation_batch_id is not None:
        query = query.where(FcTestCase.generation_batch_id == generation_batch_id)
    return query


@router.get("", response_model=FcTestCaseListResponse)
def list_fc_test_cases(
    fc_project_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    module: str | None = Query(default=None),
    case_type: str | None = Query(default=None),
    generation_batch_id: uuid.UUID | None = Query(default=None),
    no_batch: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseListResponse:
    get_fc_project_or_404(fc_project_id, db)
    _validate_list_filters(status_filter, case_type)

    base_query = select(FcTestCase).where(FcTestCase.fc_project_id == fc_project_id)
    filtered_query = _apply_test_case_list_filters(
        base_query,
        status_filter=status_filter,
        module=module,
        case_type=case_type,
        generation_batch_id=generation_batch_id,
        no_batch=no_batch,
    )

    count_query = select(func.count()).select_from(FcTestCase).where(
        FcTestCase.fc_project_id == fc_project_id
    )
    count_query = _apply_test_case_list_filters(
        count_query,
        status_filter=status_filter,
        module=module,
        case_type=case_type,
        generation_batch_id=generation_batch_id,
        no_batch=no_batch,
    )
    total = db.scalar(count_query)
    assert total is not None

    offset = (page - 1) * page_size
    cases = list(
        db.scalars(
            filtered_query.order_by(FcTestCase.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    return FcTestCaseListResponse(
        items=[_to_response(case) for case in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/filter-options", response_model=FcTestCaseFilterOptionsResponse)
def get_fc_test_case_filter_options(
    fc_project_id: uuid.UUID,
    status_filter: str = Query(default="active", alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseFilterOptionsResponse:
    get_fc_project_or_404(fc_project_id, db)
    _validate_list_filters(status_filter, None)

    modules = list(
        db.scalars(
            select(FcTestCase.module)
            .where(FcTestCase.fc_project_id == fc_project_id, FcTestCase.status == status_filter)
            .distinct()
            .order_by(FcTestCase.module.asc())
        ).all()
    )
    batch_ids = list(
        db.scalars(
            select(FcTestCase.generation_batch_id)
            .where(
                FcTestCase.fc_project_id == fc_project_id,
                FcTestCase.status == status_filter,
                FcTestCase.generation_batch_id.is_not(None),
            )
            .distinct()
            .order_by(FcTestCase.generation_batch_id.desc())
        ).all()
    )
    has_no_batch = db.scalar(
        select(func.count())
        .select_from(FcTestCase)
        .where(
            FcTestCase.fc_project_id == fc_project_id,
            FcTestCase.status == status_filter,
            FcTestCase.generation_batch_id.is_(None),
        )
    ) > 0

    return FcTestCaseFilterOptionsResponse(
        modules=modules,
        generation_batch_ids=batch_ids,
        has_no_batch=has_no_batch,
    )


@router.post("/batch-delete", response_model=FcTestCaseBatchDeleteResponse)
def batch_delete_fc_test_cases(
    fc_project_id: uuid.UUID,
    payload: FcTestCaseBatchDeleteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseBatchDeleteResponse:
    get_fc_project_or_404(fc_project_id, db)

    case_ids = list(dict.fromkeys(payload.case_ids))
    existing_ids = set(
        db.scalars(
            select(FcTestCase.id).where(
                FcTestCase.fc_project_id == fc_project_id,
                FcTestCase.id.in_(case_ids),
            )
        ).all()
    )
    if not existing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching functional test cases found",
        )

    result = db.execute(
        delete(FcTestCase).where(
            FcTestCase.fc_project_id == fc_project_id,
            FcTestCase.id.in_(existing_ids),
        )
    )
    db.commit()
    return FcTestCaseBatchDeleteResponse(deleted_count=result.rowcount or 0)


@router.post("", response_model=FcTestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_fc_test_case(
    fc_project_id: uuid.UUID,
    payload: FcTestCaseCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseResponse:
    get_fc_project_or_404(fc_project_id, db)
    _validate_enums(payload.priority, payload.case_type)
    _validate_related_ids(
        fc_project_id,
        db,
        payload.requirement_doc_id,
        payload.generation_batch_id,
    )

    case = FcTestCase(
        fc_project_id=fc_project_id,
        requirement_doc_id=payload.requirement_doc_id,
        generation_batch_id=payload.generation_batch_id,
        case_no=_resolve_case_no(payload, fc_project_id, db),
        module=payload.module.strip(),
        title=payload.title.strip(),
        preconditions=payload.preconditions,
        steps=payload.steps.strip(),
        expected_result=payload.expected_result.strip(),
        priority=payload.priority,
        case_type=payload.case_type,
        status=payload.status,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return _to_response(case)


@router.get("/{case_id}", response_model=FcTestCaseResponse)
def get_fc_test_case(
    fc_project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseResponse:
    get_fc_project_or_404(fc_project_id, db)
    case = _get_case_or_404(case_id, db)
    _ensure_case_belongs_to_project(case, fc_project_id)
    return _to_response(case)


@router.put("/{case_id}", response_model=FcTestCaseResponse)
def update_fc_test_case(
    fc_project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: FcTestCaseUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FcTestCaseResponse:
    get_fc_project_or_404(fc_project_id, db)
    case = _get_case_or_404(case_id, db)
    _ensure_case_belongs_to_project(case, fc_project_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field in ("case_no", "module", "title", "steps", "expected_result"):
        if field in update_data and update_data[field] is not None:
            update_data[field] = update_data[field].strip()

    priority = update_data.get("priority", case.priority)
    case_type = update_data.get("case_type", case.case_type)
    _validate_enums(priority, case_type)

    for field, value in update_data.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    return _to_response(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fc_test_case(
    fc_project_id: uuid.UUID,
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_fc_project_or_404(fc_project_id, db)
    case = _get_case_or_404(case_id, db)
    _ensure_case_belongs_to_project(case, fc_project_id)
    db.delete(case)
    db.commit()
