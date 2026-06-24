import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.user import User


def test_users_table_created_by_migration(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)

    assert "users" in inspector.get_table_names()
    column_names = {column["name"] for column in inspector.get_columns("users")}
    assert column_names == {"id", "username", "password_hash"}

    indexes = {index["name"] for index in inspector.get_indexes("users")}
    assert "ix_users_username" in indexes

    engine.dispose()


def test_user_model_create_and_unique_username(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        user = User(username="demo", password_hash="hashed-secret")
        session.add(user)
        session.commit()

        saved = session.get(User, user.id)
        assert saved is not None
        assert saved.username == "demo"
        assert saved.password_hash == "hashed-secret"
        assert isinstance(saved.id, uuid.UUID)

        session.add(User(username="demo", password_hash="another-hash"))
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
