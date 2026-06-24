import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.environment import Environment
from app.models.project import Project
from app.models.test_case import TestCase
from app.models.test_plan import PlanCase, PlanRun, TestPlan
from app.models.user import User


def _create_project(session) -> Project:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hash")
    session.add(user)
    session.flush()
    project = Project(name="Demo Project", created_by=user.id)
    session.add(project)
    session.flush()
    return project


def _create_environment(session) -> Environment:
    environment = Environment(name=f"env_{uuid.uuid4().hex[:8]}", is_default=False)
    session.add(environment)
    session.flush()
    return environment


def test_test_plan_tables_created_by_migration(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())
    assert {"test_plans", "plan_cases", "plan_runs"}.issubset(table_names)

    plan_columns = {column["name"] for column in inspector.get_columns("test_plans")}
    assert plan_columns == {
        "id",
        "project_id",
        "name",
        "cron_expression",
        "environment_id",
        "is_enabled",
        "created_at",
    }

    plan_case_columns = {column["name"] for column in inspector.get_columns("plan_cases")}
    assert plan_case_columns == {"id", "plan_id", "case_id", "sort_order"}

    plan_run_columns = {column["name"] for column in inspector.get_columns("plan_runs")}
    assert plan_run_columns == {
        "id",
        "plan_id",
        "status",
        "total_count",
        "pass_count",
        "fail_count",
        "allure_report_url",
        "started_at",
        "finished_at",
        "created_at",
    }

    engine.dispose()


def test_test_plan_create_with_defaults(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        environment = _create_environment(session)
        plan = TestPlan(
            project_id=project.id,
            name="Smoke Plan",
            environment_id=environment.id,
        )
        session.add(plan)
        session.commit()

        saved = session.get(TestPlan, plan.id)
        assert saved is not None
        assert saved.name == "Smoke Plan"
        assert saved.cron_expression is None
        assert saved.is_enabled is False
        assert saved.created_at is not None

    engine.dispose()


def test_plan_case_relationship_and_sort_order(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        environment = _create_environment(session)
        plan = TestPlan(
            project_id=project.id,
            name="Regression",
            environment_id=environment.id,
        )
        case_a = TestCase(project_id=project.id, name="Case A")
        case_b = TestCase(project_id=project.id, name="Case B")
        session.add_all([plan, case_a, case_b])
        session.flush()

        session.add_all(
            [
                PlanCase(plan_id=plan.id, case_id=case_a.id, sort_order=1),
                PlanCase(plan_id=plan.id, case_id=case_b.id, sort_order=0),
            ]
        )
        session.commit()

        saved_plan = session.get(TestPlan, plan.id)
        assert saved_plan is not None
        assert [item.test_case.name for item in saved_plan.plan_cases] == ["Case B", "Case A"]

    engine.dispose()


def test_plan_run_create(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        environment = _create_environment(session)
        plan = TestPlan(
            project_id=project.id,
            name="Nightly",
            environment_id=environment.id,
        )
        session.add(plan)
        session.flush()

        plan_run = PlanRun(
            plan_id=plan.id,
            status="completed",
            total_count=10,
            pass_count=8,
            fail_count=2,
            allure_report_url="/reports/plan-run-1",
        )
        session.add(plan_run)
        session.commit()

        saved_run = session.get(PlanRun, plan_run.id)
        assert saved_run is not None
        assert saved_run.plan_id == plan.id
        assert saved_run.status == "completed"
        assert saved_run.pass_count == 8
        assert saved_run.fail_count == 2

    engine.dispose()


def test_plan_case_unique_constraint(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        environment = _create_environment(session)
        plan = TestPlan(
            project_id=project.id,
            name="Unique Plan",
            environment_id=environment.id,
        )
        test_case = TestCase(project_id=project.id, name="Single Case")
        session.add_all([plan, test_case])
        session.flush()

        session.add(PlanCase(plan_id=plan.id, case_id=test_case.id, sort_order=0))
        session.commit()

        session.add(PlanCase(plan_id=plan.id, case_id=test_case.id, sort_order=1))
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_test_plan_cascade_on_project_delete(migrated_db: str) -> None:
    engine = create_engine(migrated_db, connect_args={"check_same_thread": False})
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as session:
        project = _create_project(session)
        environment = _create_environment(session)
        plan = TestPlan(
            project_id=project.id,
            name="Cascade Plan",
            environment_id=environment.id,
        )
        test_case = TestCase(project_id=project.id, name="Linked Case")
        session.add_all([plan, test_case])
        session.flush()

        session.add(PlanCase(plan_id=plan.id, case_id=test_case.id, sort_order=0))
        session.add(PlanRun(plan_id=plan.id, status="pending"))
        session.commit()

        plan_id = plan.id
        plan_run_id = session.query(PlanRun).filter(PlanRun.plan_id == plan_id).one().id

        session.delete(project)
        session.commit()

        assert session.get(TestPlan, plan_id) is None
        assert session.get(PlanRun, plan_run_id) is None
        assert session.query(PlanCase).filter(PlanCase.plan_id == plan_id).count() == 0

    engine.dispose()
