from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.security import verify_password
from app.models.api_endpoint import ApiEndpoint
from app.models.environment import Environment, EnvironmentVariable
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.test_plan import TestPlan
from app.models.user import User
from app.services.demo_seed_service import (
    DEMO_ENV_NAME,
    DEMO_OPENAPI_PATH,
    DEMO_PASSWORD,
    DEMO_PROJECT_NAME,
    DEMO_USERNAME,
    seed_demo_data,
)

ALEMBIC_CFG = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@pytest.fixture
def seed_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    db_path = tmp_path / "seed.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import get_settings

    get_settings.cache_clear()
    command.upgrade(ALEMBIC_CFG, "head")

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    import app.database as database_module

    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(database_module, "SessionLocal", session_factory)

    yield session_factory
    get_settings.cache_clear()
    engine.dispose()


def test_demo_openapi_file_exists() -> None:
    assert DEMO_OPENAPI_PATH.is_file()


def test_seed_demo_data_is_idempotent(seed_db: sessionmaker) -> None:
    with seed_db() as session:
        first = seed_demo_data(session)
        assert first.endpoints_created == 4
        assert first.test_cases_created == 2
        assert first.test_plans_created == 1

    with seed_db() as session:
        second = seed_demo_data(session)
        assert second.endpoints_created == 0
        assert second.endpoints_updated == 4
        assert second.test_cases_created == 0
        assert second.test_plans_created == 0

        user = session.scalar(select(User).where(User.username == DEMO_USERNAME))
        assert user is not None

        project = session.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
        assert project is not None

        endpoint_count = session.scalar(
            select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.project_id == project.id),
        )
        assert endpoint_count == 4

        case_count = session.scalar(
            select(func.count()).select_from(TestCase).where(TestCase.project_id == project.id),
        )
        assert case_count == 2

        plan_count = session.scalar(
            select(func.count()).select_from(TestPlan).where(TestPlan.project_id == project.id),
        )
        assert plan_count == 1

        environment = session.scalar(select(Environment).where(Environment.name == DEMO_ENV_NAME))
        assert environment is not None
        variables = session.scalars(
            select(EnvironmentVariable).where(EnvironmentVariable.environment_id == environment.id),
        ).all()
        assert {item.key for item in variables} == {"base_url", "token"}


def test_seed_demo_user_password(seed_db: sessionmaker) -> None:
    with seed_db() as session:
        seed_demo_data(session)

    with seed_db() as session:
        user = session.scalar(select(User).where(User.username == DEMO_USERNAME))
        assert user is not None
        assert verify_password(DEMO_PASSWORD, user.password_hash)
