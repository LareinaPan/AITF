import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_endpoint import ApiEndpoint
from app.services.openapi_parser import ParsedApiEndpoint


@dataclass(frozen=True)
class EndpointUpsertResult:
    created: int
    updated: int


def upsert_parsed_endpoints(
    session: Session,
    project_id: uuid.UUID,
    endpoints: list[ParsedApiEndpoint],
) -> EndpointUpsertResult:
    """Insert or update api_endpoints by unique key (project_id, method, path)."""
    if not endpoints:
        return EndpointUpsertResult(created=0, updated=0)

    existing_rows = session.scalars(
        select(ApiEndpoint).where(ApiEndpoint.project_id == project_id)
    ).all()
    existing_by_key = {(row.method, row.path): row for row in existing_rows}

    created = 0
    updated = 0

    for parsed in endpoints:
        key = (parsed.method, parsed.path)
        existing = existing_by_key.get(key)
        if existing is not None:
            existing.summary = parsed.summary
            existing.description = parsed.description
            existing.parameters_json = parsed.parameters_json
            existing.request_body_json = parsed.request_body_json
            existing.responses_json = parsed.responses_json
            updated += 1
            continue

        new_row = ApiEndpoint(
            project_id=project_id,
            method=parsed.method,
            path=parsed.path,
            summary=parsed.summary,
            description=parsed.description,
            parameters_json=parsed.parameters_json,
            request_body_json=parsed.request_body_json,
            responses_json=parsed.responses_json,
        )
        session.add(new_row)
        existing_by_key[key] = new_row
        created += 1

    session.flush()
    return EndpointUpsertResult(created=created, updated=updated)
