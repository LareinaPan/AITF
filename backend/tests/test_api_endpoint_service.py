import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import ApiEndpoint
from app.models.project import Project
from app.models.user import User
from app.services.api_endpoint_service import upsert_parsed_endpoints
from app.services.openapi_parser import ParsedApiEndpoint


def _create_project(session) -> Project:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()
    project = Project(name="API Project", created_by=user.id)
    session.add(project)
    session.flush()
    return project


def _parsed(
    method: str,
    path: str,
    *,
    summary: str | None = None,
) -> ParsedApiEndpoint:
    return ParsedApiEndpoint(
        method=method,
        path=path,
        summary=summary,
        description=None,
        parameters_json=[],
        request_body_json=None,
        responses_json={"200": {"description": "OK"}},
    )


def test_upsert_parsed_endpoints_creates_rows(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        result = upsert_parsed_endpoints(
            session,
            project.id,
            [
                _parsed("GET", "/api/users", summary="List users"),
                _parsed("POST", "/api/users", summary="Create user"),
            ],
        )
        session.commit()

        assert result.created == 2
        assert result.updated == 0

        rows = session.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)
        ).all()
        assert len(rows) == 2
        assert {(row.method, row.path) for row in rows} == {
            ("GET", "/api/users"),
            ("POST", "/api/users"),
        }

    engine.dispose()


def test_upsert_parsed_endpoints_updates_existing_rows(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        session.add(
            ApiEndpoint(
                project_id=project.id,
                method="GET",
                path="/api/users",
                summary="Old summary",
                responses_json={"201": {"description": "Created"}},
            )
        )
        session.commit()

        result = upsert_parsed_endpoints(
            session,
            project.id,
            [
                ParsedApiEndpoint(
                    method="GET",
                    path="/api/users",
                    summary="New summary",
                    description="Updated description",
                    parameters_json=[{"name": "page", "in": "query"}],
                    request_body_json=None,
                    responses_json={"200": {"description": "OK"}},
                )
            ],
        )
        session.commit()

        assert result.created == 0
        assert result.updated == 1

        saved = session.scalars(
            select(ApiEndpoint).where(
                ApiEndpoint.project_id == project.id,
                ApiEndpoint.method == "GET",
                ApiEndpoint.path == "/api/users",
            )
        ).one()
        assert saved.summary == "New summary"
        assert saved.description == "Updated description"
        assert saved.parameters_json == [{"name": "page", "in": "query"}]
        assert saved.responses_json == {"200": {"description": "OK"}}

    engine.dispose()


def test_upsert_parsed_endpoints_mixed_create_and_update(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        session.add(
            ApiEndpoint(
                project_id=project.id,
                method="GET",
                path="/api/users",
                summary="Existing",
            )
        )
        session.commit()

        result = upsert_parsed_endpoints(
            session,
            project.id,
            [
                _parsed("GET", "/api/users", summary="Updated"),
                _parsed("DELETE", "/api/users/{id}", summary="Delete user"),
            ],
        )
        session.commit()

        assert result.created == 1
        assert result.updated == 1
        assert session.scalar(
            select(func.count()).select_from(ApiEndpoint).where(
                ApiEndpoint.project_id == project.id
            )
        ) == 2

    engine.dispose()


def test_upsert_parsed_endpoints_preserves_created_at_on_update(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        session.add(
            ApiEndpoint(
                project_id=project.id,
                method="GET",
                path="/api/users",
                summary="Before",
            )
        )
        session.commit()

        before = session.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)
        ).one()
        created_at = before.created_at

        upsert_parsed_endpoints(
            session,
            project.id,
            [_parsed("GET", "/api/users", summary="After")],
        )
        session.commit()

        after = session.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)
        ).one()
        assert after.summary == "After"
        assert after.created_at == created_at

    engine.dispose()


def test_upsert_parsed_endpoints_does_not_delete_missing_rows(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        session.add_all(
            [
                ApiEndpoint(
                    project_id=project.id,
                    method="GET",
                    path="/api/users",
                    summary="Keep",
                ),
                ApiEndpoint(
                    project_id=project.id,
                    method="GET",
                    path="/api/orders",
                    summary="Also keep",
                ),
            ]
        )
        session.commit()

        upsert_parsed_endpoints(
            session,
            project.id,
            [_parsed("POST", "/api/users", summary="New only")],
        )
        session.commit()

        rows = session.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)
        ).all()
        assert len(rows) == 3
        assert {(row.method, row.path) for row in rows} == {
            ("GET", "/api/users"),
            ("GET", "/api/orders"),
            ("POST", "/api/users"),
        }

    engine.dispose()


def test_upsert_parsed_endpoints_empty_list(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        result = upsert_parsed_endpoints(session, project.id, [])
        session.commit()

        assert result.created == 0
        assert result.updated == 0
        assert (
            session.scalar(
                select(func.count()).select_from(ApiEndpoint).where(
                    ApiEndpoint.project_id == project.id
                )
            )
            == 0
        )

    engine.dispose()
