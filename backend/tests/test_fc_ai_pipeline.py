import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.database as database_module
from app.models.fc_generation_batch import FcGenerationBatch, FcGenerationBatchStatus
from app.models.fc_project import FcProject
from app.models.fc_requirement_doc import FcRequirementDoc, FcRequirementParseStatus
from app.models.fc_test_case import FcTestCase, FcTestCaseStatus
from app.models.user import User
from app.schemas.fc_generation import FcAIReviewReport
from app.services.fc_ai_generator import GeneratedFcTestCases
from app.services.fc_ai_pipeline import run_generation_batch
from app.services.fc_ai_reviewer import (
    FcReviewInput,
    apply_coverage_gate,
    compute_coverage_score,
    review_functional_test_cases,
    validate_fc_review_report,
)

SAMPLE_CASES = [
    {
        "case_no": "FC-001",
        "module": "用户登录",
        "title": "正确密码登录",
        "preconditions": "用户已注册",
        "steps": "1. 打开登录页\n2. 输入账号密码",
        "expected_result": "登录成功",
        "priority": "P0",
        "case_type": "positive",
    }
]

PASSING_DIMENSION_SCORES = {
    "positive": 90.0,
    "negative": 85.0,
    "boundary": 80.0,
    "permission": 88.0,
    "security": 82.0,
    "compatibility": 78.0,
}

FAILING_DIMENSION_SCORES = {
    "positive": 60.0,
    "negative": 60.0,
    "boundary": 60.0,
    "permission": 60.0,
    "security": 60.0,
    "compatibility": 60.0,
}


def _build_review_report(
    *,
    dimension_scores: dict[str, float],
    passed: bool | None = None,
) -> dict[str, object]:
    coverage_score = compute_coverage_score(dimension_scores)
    return {
        "coverage_score": coverage_score,
        "dimension_scores": dimension_scores,
        "feature_checklist": [{"feature": "用户登录", "covered": True, "case_count": 1}],
        "gaps": [] if coverage_score >= 80 else ["缺少忘记密码场景"],
        "suggestions": [] if coverage_score >= 80 else ["补充异常登录用例"],
        "passed": passed if passed is not None else coverage_score >= 80,
    }


def test_compute_coverage_score_uses_dimension_weights() -> None:
    score = compute_coverage_score(PASSING_DIMENSION_SCORES)
    expected = round(
        90 * 0.25 + 85 * 0.2 + 80 * 0.15 + 88 * 0.15 + 82 * 0.15 + 78 * 0.1,
        1,
    )
    assert score == expected


def test_apply_coverage_gate_passes_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FC_COVERAGE_THRESHOLD", "80")
    from app.config import get_settings

    get_settings.cache_clear()

    report = FcAIReviewReport.model_validate(_build_review_report(dimension_scores=PASSING_DIMENSION_SCORES))
    gated = apply_coverage_gate(report)

    assert gated.coverage_score >= 80.0
    assert gated.passed is True


def test_apply_coverage_gate_fails_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FC_COVERAGE_THRESHOLD", "80")
    from app.config import get_settings

    get_settings.cache_clear()

    report = FcAIReviewReport.model_validate(
        _build_review_report(dimension_scores=FAILING_DIMENSION_SCORES, passed=True)
    )
    gated = apply_coverage_gate(report)

    assert gated.coverage_score < 80.0
    assert gated.passed is False


def test_validate_fc_review_report_overrides_ai_passed_flag() -> None:
    raw_report = _build_review_report(dimension_scores=FAILING_DIMENSION_SCORES, passed=True)
    report = validate_fc_review_report(raw_report)

    assert report.passed is False
    assert report.coverage_score == compute_coverage_score(FAILING_DIMENSION_SCORES)


def test_review_functional_test_cases_with_mock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        _build_review_report(dimension_scores=PASSING_DIMENSION_SCORES),
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )

    report = review_functional_test_cases(
        FcReviewInput(parsed_text="登录需求", generated_cases=SAMPLE_CASES),
        client=mock_client,
    )

    assert report["passed"] is True
    assert report["coverage_score"] >= 80.0


def _seed_batch(db: Session) -> FcGenerationBatch:
    user = User(username=f"user_{uuid.uuid4().hex[:8]}", password_hash="hashed")
    db.add(user)
    db.flush()

    project = FcProject(name="Pipeline Project", description="test", created_by=user.id)
    db.add(project)
    db.flush()

    doc = FcRequirementDoc(
        fc_project_id=project.id,
        filename="req.txt",
        file_path=f"storage/fc-uploads/{uuid.uuid4()}.txt",
        file_type="txt",
        file_size=128,
        parse_status=FcRequirementParseStatus.SUCCESS.value,
        parsed_text="用户登录与忘记密码需求",
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()

    batch = FcGenerationBatch(
        fc_project_id=project.id,
        requirement_doc_id=doc.id,
        experience_case_ids=[],
        status=FcGenerationBatchStatus.PENDING.value,
        triggered_by=user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def test_run_generation_batch_completes_with_draft_cases(migrated_db: str) -> None:
    engine = database_module.engine
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    batch = _seed_batch(db)

    passing_report = validate_fc_review_report(
        _build_review_report(dimension_scores=PASSING_DIMENSION_SCORES)
    ).to_storage_dict()

    with (
        patch(
            "app.services.fc_ai_pipeline.generate_functional_test_cases",
            return_value=GeneratedFcTestCases(cases=SAMPLE_CASES, rejected_count=0, raw_count=1),
        ) as mock_generate,
        patch(
            "app.services.fc_ai_pipeline.review_functional_test_cases",
            return_value=passing_report,
        ) as mock_review,
    ):
        run_generation_batch(batch.id, db=db)

    db.refresh(batch)
    assert batch.status == FcGenerationBatchStatus.AWAITING_REVIEW.value
    assert batch.coverage_score is not None
    assert batch.coverage_score >= 80.0
    assert batch.completed_at is not None
    assert batch.review_report_json is not None
    assert mock_generate.call_count == 1
    assert mock_review.call_count == 1

    cases = list(
        db.scalars(select(FcTestCase).where(FcTestCase.generation_batch_id == batch.id)).all()
    )
    assert len(cases) == 1
    assert cases[0].status == FcTestCaseStatus.DRAFT.value
    assert cases[0].title == "正确密码登录"
    db.close()


def test_run_generation_batch_retries_until_internal_limit(migrated_db: str) -> None:
    engine = database_module.engine
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    batch = _seed_batch(db)

    failing_report = validate_fc_review_report(
        _build_review_report(dimension_scores=FAILING_DIMENSION_SCORES)
    ).to_storage_dict()

    with (
        patch(
            "app.services.fc_ai_pipeline.generate_functional_test_cases",
            return_value=GeneratedFcTestCases(cases=SAMPLE_CASES, rejected_count=0, raw_count=1),
        ) as mock_generate,
        patch(
            "app.services.fc_ai_pipeline.review_functional_test_cases",
            return_value=failing_report,
        ) as mock_review,
    ):
        run_generation_batch(batch.id, db=db)

    db.refresh(batch)
    assert batch.status == FcGenerationBatchStatus.AWAITING_REVIEW.value
    assert batch.internal_retry_count == 3
    assert batch.coverage_score is not None
    assert batch.coverage_score < 80.0
    assert mock_generate.call_count == 4
    assert mock_review.call_count == 4
    db.close()


def test_run_generation_batch_marks_failed_on_generation_error(migrated_db: str) -> None:
    engine = database_module.engine
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    batch = _seed_batch(db)

    with patch(
        "app.services.fc_ai_pipeline.generate_functional_test_cases",
        side_effect=RuntimeError("LLM unavailable"),
    ):
        run_generation_batch(batch.id, db=db)

    db.refresh(batch)
    assert batch.status == FcGenerationBatchStatus.FAILED.value
    assert batch.error_message == "LLM unavailable"
    assert batch.completed_at is not None
    db.close()
