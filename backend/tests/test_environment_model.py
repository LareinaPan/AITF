import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.environment import Environment, EnvironmentVariable


def test_environment_tables_created_by_migration(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)

    assert "environments" in inspector.get_table_names()
    assert "environment_variables" in inspector.get_table_names()

    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    assert env_columns == {"id", "name", "is_default"}

    variable_columns = {
        column["name"] for column in inspector.get_columns("environment_variables")
    }
    assert variable_columns == {"id", "environment_id", "key", "value", "is_secret"}

    engine.dispose()


def test_environment_and_variable_relationship(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        environment = Environment(name="dev", is_default=True)
        session.add(environment)
        session.flush()

        variable = EnvironmentVariable(
            environment_id=environment.id,
            key="base_url",
            value="http://localhost:8080",
            is_secret=False,
        )
        session.add(variable)
        session.commit()

        saved_env = session.get(Environment, environment.id)
        assert saved_env is not None
        assert len(saved_env.variables) == 1
        assert saved_env.variables[0].key == "base_url"

        session.add(Environment(name="dev", is_default=False))
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_environment_variable_unique_key_per_environment(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        environment = Environment(name="test", is_default=False)
        session.add(environment)
        session.flush()

        session.add(
            EnvironmentVariable(
                environment_id=environment.id,
                key="token",
                value="secret-1",
                is_secret=True,
            )
        )
        session.commit()

        session.add(
            EnvironmentVariable(
                environment_id=environment.id,
                key="token",
                value="secret-2",
                is_secret=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
