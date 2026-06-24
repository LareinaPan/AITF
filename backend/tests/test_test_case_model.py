import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.project import Project
from app.models.test_case import DEFAULT_ASSERTIONS_JSON, DEFAULT_REQUEST_JSON, TestCase
from app.models.user import User


def _create_project(session) -> Project:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()
    project = Project(name="Demo Project", created_by=user.id)
    session.add(project)
    session.flush()
    return project


def test_test_cases_table_created_by_migration(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)

    assert "test_cases" in inspector.get_table_names()
    column_names = {column["name"] for column in inspector.get_columns("test_cases")}
    assert column_names == {
        "id",
        "project_id",
        "name",
        "description",
        "request_json",
        "assertions_json",
        "priority",
        "status",
        "api_endpoint_id",
        "created_at",
    }

    indexes = {index["name"] for index in inspector.get_indexes("test_cases")}
    assert "ix_test_cases_project_id" in indexes

    engine.dispose()


def test_test_case_create_with_defaults(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        test_case = TestCase(
            project_id=project.id,
            name="Login success",
            description="Verify login API",
        )
        session.add(test_case)
        session.commit()

        saved = session.get(TestCase, test_case.id)
        assert saved is not None
        assert saved.name == "Login success"
        assert saved.description == "Verify login API"
        assert saved.priority == "P2"
        assert saved.status == "active"
        assert saved.api_endpoint_id is None
        assert saved.request_json == DEFAULT_REQUEST_JSON
        assert saved.assertions_json == DEFAULT_ASSERTIONS_JSON
        assert isinstance(saved.id, uuid.UUID)
        assert saved.created_at is not None

    engine.dispose()


def test_test_case_project_relationship_and_cascade(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        test_case = TestCase(
            project_id=project.id,
            name="Get users",
            priority="P0",
            status="draft",
            request_json={
                "method": "GET",
                "url": "{{base_url}}/api/users",
                "headers": [],
                "query": [],
                "body": {"type": "none", "content": ""},
            },
            assertions_json={
                "status_code": 200,
                "max_response_time_ms": 2000,
                "body_rules": [{"type": "contains", "value": "success"}],
            },
        )
        session.add(test_case)
        session.commit()

        saved_project = session.get(Project, project.id)
        assert saved_project is not None
        assert len(saved_project.test_cases) == 1
        assert saved_project.test_cases[0].name == "Get users"
        assert saved_project.test_cases[0].priority == "P0"
        assert saved_project.test_cases[0].status == "draft"

        session.delete(saved_project)
        session.commit()

        assert session.get(TestCase, test_case.id) is None

    engine.dispose()


def test_test_case_requires_valid_project(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()

    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        test_case = TestCase(
            project_id=uuid.uuid4(),
            name="Orphan case",
        )
        session.add(test_case)
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
