from collections.abc import Generator
from pathlib import Path
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.database as database_module
from app.config import get_settings
from app.database import get_db
from app.main import app

ALEMBIC_CFG = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@pytest.fixture
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "test.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    command.upgrade(ALEMBIC_CFG, "head")

    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(database_module, "engine", test_engine)
    monkeypatch.setattr(
        database_module,
        "SessionLocal",
        sessionmaker(bind=test_engine, autocommit=False, autoflush=False),
    )

    yield database_url
    get_settings.cache_clear()


@pytest.fixture
def client(migrated_db: str) -> Generator[TestClient, None, None]:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    username = f"user_{uuid.uuid4().hex[:8]}"
    password = "secret12"
    client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
