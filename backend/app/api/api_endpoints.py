import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.projects import get_project_or_404
from app.core.deps import get_current_user
from app.database import get_db
from app.models.api_endpoint import ApiEndpoint
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.ai_generation import AIGenerateRequest, AIGenerateResponse
from app.schemas.api_endpoint import (
    ApiEndpointListItemResponse,
    ApiEndpointListResponse,
    ApiEndpointResponse,
)
from app.services.ai_generator import (
    AIGenerationError,
    GenerationCounts,
    LLMCallError,
    LLMConfigurationError,
    LLMOutputValidationError,
    LLMResponseParseError,
    generate_test_case_candidates,
    save_draft_test_cases,
)

router = APIRouter()


def get_api_endpoint_or_404(
    project_id: uuid.UUID,
    api_id: uuid.UUID,
    db: Session,
) -> ApiEndpoint:
    endpoint = db.get(ApiEndpoint, api_id)
    if endpoint is None or endpoint.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API endpoint not found",
        )
    return endpoint


def _count_test_cases_by_endpoint(
    db: Session,
    endpoint_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not endpoint_ids:
        return {}

    rows = db.execute(
        select(TestCase.api_endpoint_id, func.count())
        .where(TestCase.api_endpoint_id.in_(endpoint_ids))
        .group_by(TestCase.api_endpoint_id)
    ).all()

    return {endpoint_id: count for endpoint_id, count in rows if endpoint_id is not None}


@router.get("", response_model=ApiEndpointListResponse)
def list_api_endpoints(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ApiEndpointListResponse:
    get_project_or_404(project_id, db)

    total = db.scalar(
        select(func.count())
        .select_from(ApiEndpoint)
        .where(ApiEndpoint.project_id == project_id)
    )
    assert total is not None

    offset = (page - 1) * page_size
    items = list(
        db.scalars(
            select(ApiEndpoint)
            .where(ApiEndpoint.project_id == project_id)
            .order_by(ApiEndpoint.method.asc(), ApiEndpoint.path.asc())
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    case_counts = _count_test_cases_by_endpoint(db, [item.id for item in items])
    list_items = [
        ApiEndpointListItemResponse(
            **ApiEndpointResponse.model_validate(item).model_dump(),
            test_case_count=case_counts.get(item.id, 0),
        )
        for item in items
    ]

    return ApiEndpointListResponse(
        items=list_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{api_id}", response_model=ApiEndpointResponse)
def get_api_endpoint(
    project_id: uuid.UUID,
    api_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ApiEndpoint:
    get_project_or_404(project_id, db)
    return get_api_endpoint_or_404(project_id, api_id, db)


@router.delete("/{api_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_endpoint(
    project_id: uuid.UUID,
    api_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    get_project_or_404(project_id, db)
    endpoint = get_api_endpoint_or_404(project_id, api_id, db)
    db.delete(endpoint)
    db.commit()


@router.post("/{api_id}/ai-generate", response_model=AIGenerateResponse)
def ai_generate_test_cases(
    project_id: uuid.UUID,
    api_id: uuid.UUID,
    payload: AIGenerateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AIGenerateResponse:
    get_project_or_404(project_id, db)
    endpoint = get_api_endpoint_or_404(project_id, api_id, db)

    counts = GenerationCounts(
        positive_count=payload.positive_count,
        boundary_count=payload.boundary_count,
        exception_count=payload.exception_count,
        auth_count=payload.auth_count,
    )

    try:
        generated = generate_test_case_candidates(endpoint, counts)
        saved_cases = save_draft_test_cases(
            db,
            project_id,
            api_id,
            generated.cases,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (LLMOutputValidationError, LLMResponseParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (LLMCallError, AIGenerationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return AIGenerateResponse(
        cases=saved_cases,
        requested_count=generated.requested_count,
        rejected_count=generated.rejected_count,
        raw_count=generated.raw_count,
    )
