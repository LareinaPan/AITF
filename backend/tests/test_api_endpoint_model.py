import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.api_endpoint import (
    DEFAULT_PARAMETERS_JSON,
    DEFAULT_RESPONSES_JSON,
    ApiEndpoint,
)
from app.models.project import Project
from app.models.user import User


def _create_project(session) -> Project:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()
    project = Project(name="API Project", created_by=user.id)
    session.add(project)
    session.flush()
    return project


def test_api_endpoints_table_created_by_migration(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)

    assert "api_endpoints" in inspector.get_table_names()
    column_names = {column["name"] for column in inspector.get_columns("api_endpoints")}
    assert column_names == {
        "id",
        "project_id",
        "method",
        "path",
        "summary",
        "description",
        "parameters_json",
        "request_body_json",
        "responses_json",
        "created_at",
    }

    indexes = {index["name"] for index in inspector.get_indexes("api_endpoints")}
    assert "ix_api_endpoints_project_id" in indexes

    unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("api_endpoints")
    }
    assert "uq_api_endpoints_project_method_path" in unique_constraints

    engine.dispose()


def test_api_endpoint_create_with_defaults(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        endpoint = ApiEndpoint(
            project_id=project.id,
            method="GET",
            path="/api/users",
            summary="List users",
        )
        session.add(endpoint)
        session.commit()

        saved = session.get(ApiEndpoint, endpoint.id)
        assert saved is not None
        assert saved.method == "GET"
        assert saved.path == "/api/users"
        assert saved.summary == "List users"
        assert saved.parameters_json == DEFAULT_PARAMETERS_JSON
        assert saved.request_body_json is None
        assert saved.responses_json == DEFAULT_RESPONSES_JSON
        assert isinstance(saved.id, uuid.UUID)

    engine.dispose()


def test_api_endpoint_project_relationship_and_unique_key(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        endpoint = ApiEndpoint(
            project_id=project.id,
            method="POST",
            path="/api/users",
            summary="Create user",
            parameters_json=[{"name": "body", "in": "body"}],
            request_body_json={"content": {"application/json": {"schema": {"type": "object"}}}},
            responses_json={"200": {"description": "OK"}},
        )
        session.add(endpoint)
        session.commit()

        saved_project = session.get(Project, project.id)
        assert saved_project is not None
        assert len(saved_project.api_endpoints) == 1
        assert saved_project.api_endpoints[0].path == "/api/users"

        session.add(
            ApiEndpoint(
                project_id=project.id,
                method="POST",
                path="/api/users",
                summary="Duplicate",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_api_endpoint_requires_valid_project(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()

    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        endpoint = ApiEndpoint(
            project_id=uuid.uuid4(),
            method="GET",
            path="/api/orphan",
        )
        session.add(endpoint)
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
