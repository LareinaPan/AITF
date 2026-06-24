import uuid

from pydantic import BaseModel


class ProjectStatsItem(BaseModel):
    project_id: uuid.UUID
    name: str
    apis: int
    cases: int


class DashboardStatsResponse(BaseModel):
    total_apis: int
    total_cases: int
    by_project: list[ProjectStatsItem]
