from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.api_endpoint import ApiEndpoint
from app.models.project import Project
from app.models.test_case import TestCase
from app.schemas.dashboard import DashboardStatsResponse, ProjectStatsItem


def get_dashboard_stats(db: Session) -> DashboardStatsResponse:
    total_apis = db.scalar(select(func.count()).select_from(ApiEndpoint)) or 0
    total_cases = (
        db.scalar(
            select(func.count())
            .select_from(TestCase)
            .where(TestCase.status == "active"),
        )
        or 0
    )

    api_counts = (
        select(
            ApiEndpoint.project_id.label("project_id"),
            func.count().label("apis"),
        )
        .group_by(ApiEndpoint.project_id)
        .subquery()
    )
    case_counts = (
        select(
            TestCase.project_id.label("project_id"),
            func.count().label("cases"),
        )
        .where(TestCase.status == "active")
        .group_by(TestCase.project_id)
        .subquery()
    )

    rows = db.execute(
        select(
            Project.id,
            Project.name,
            func.coalesce(api_counts.c.apis, 0).label("apis"),
            func.coalesce(case_counts.c.cases, 0).label("cases"),
        )
        .outerjoin(api_counts, Project.id == api_counts.c.project_id)
        .outerjoin(case_counts, Project.id == case_counts.c.project_id)
        .order_by(Project.name),
    ).all()

    by_project = [
        ProjectStatsItem(
            project_id=row.id,
            name=row.name,
            apis=int(row.apis),
            cases=int(row.cases),
        )
        for row in rows
    ]

    return DashboardStatsResponse(
        total_apis=total_apis,
        total_cases=total_cases,
        by_project=by_project,
    )
