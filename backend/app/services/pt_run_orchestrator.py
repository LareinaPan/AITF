"""Load test run orchestration — slot lock, engine lifecycle, finalize."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.config import get_settings
from app.models.pt_run import PtRun, PtRunStatus, PtRunStopReason
from app.models.pt_run_error_log import PtRunErrorLog
from app.models.pt_run_metric_point import PtRunMetricPoint
from app.models.pt_script import PtScript, PtScriptParseStatus, PtScriptStopMode
from app.services.pt_error_log_sanitizer import sanitize_error_message
from app.services.pt_load_engine import LoadEngineConfig, LoadSampleResult, PtLoadEngine, get_active_engine
from app.services.pt_metrics_aggregator import MetricSnapshot, PtMetricsAggregator

logger = logging.getLogger(__name__)

_running_run_id: uuid.UUID | None = None
_slot_lock = asyncio.Lock()
_active_aggregators: dict[uuid.UUID, PtMetricsAggregator] = {}


@dataclass
class _RunTelemetrySidecar:
    recent_errors: deque[LoadSampleResult] = field(
        default_factory=lambda: deque(maxlen=50)
    )
    persisted_error_count: int = 0


_run_sidecars: dict[uuid.UUID, _RunTelemetrySidecar] = {}


class PtRunConflictError(Exception):
    """Raised when another load test is already running."""


class PtRunNotRunningError(Exception):
    """Raised when cancel is requested for a run that is not active."""


class PtRunOrchestratorError(Exception):
    """Raised when orchestration preconditions fail."""


@dataclass(frozen=True)
class _RunFinalizeOutcome:
    status: str
    stop_reason: str | None
    error_message: str | None
    include_summary: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_config_snapshot_from_script(script: PtScript) -> dict[str, Any]:
    parsed_plan = script.parsed_plan_json or {}
    return {
        "max_concurrency": script.max_concurrency,
        "ramp_up_seconds": script.ramp_up_seconds,
        "stop_mode": script.stop_mode,
        "duration_seconds": script.duration_seconds,
        "default_max_requests": script.default_max_requests,
        "sampler_limits": script.sampler_limits_json or {},
        "samplers": parsed_plan.get("samplers", []),
    }


def validate_script_ready_for_run(script: PtScript) -> None:
    if script.parse_status != PtScriptParseStatus.SUCCESS.value:
        raise PtRunOrchestratorError("Script must be parsed successfully before running")
    snapshot = build_config_snapshot_from_script(script)
    if not snapshot.get("samplers"):
        raise PtRunOrchestratorError("Script has no parsed HTTP samplers")
    if snapshot["stop_mode"] == PtScriptStopMode.DURATION.value:
        if snapshot.get("duration_seconds") is None:
            raise PtRunOrchestratorError("duration_seconds is required for duration stop mode")
    elif snapshot["stop_mode"] == PtScriptStopMode.REQUEST_LIMIT.value:
        if snapshot.get("default_max_requests") is None:
            raise PtRunOrchestratorError(
                "default_max_requests is required for request_limit stop mode"
            )
    config = LoadEngineConfig.from_snapshot(snapshot)
    if not [sampler for sampler in config.samplers if not sampler.has_variables]:
        raise PtRunOrchestratorError("No executable HTTP samplers available")


def find_global_running_run(db: Session) -> PtRun | None:
    return db.scalar(select(PtRun).where(PtRun.status == PtRunStatus.RUNNING.value))


def is_run_slot_busy(db: Session) -> bool:
    if _running_run_id is not None:
        return True
    return find_global_running_run(db) is not None


async def acquire_run_slot(run_id: uuid.UUID, db: Session) -> None:
    global _running_run_id
    async with _slot_lock:
        if _running_run_id is not None and _running_run_id != run_id:
            raise PtRunConflictError("Another load test is already running")
        existing = find_global_running_run(db)
        if existing is not None and existing.id != run_id:
            raise PtRunConflictError("Another load test is already running")
        _running_run_id = run_id


async def release_run_slot(run_id: uuid.UUID) -> None:
    global _running_run_id
    async with _slot_lock:
        if _running_run_id == run_id:
            _running_run_id = None


def get_run_aggregator(run_id: uuid.UUID) -> PtMetricsAggregator | None:
    return _active_aggregators.get(run_id)


def persist_metric_snapshots(run_id: uuid.UUID, snapshots: list[MetricSnapshot]) -> None:
    """Persist flush-window metric snapshots using an independent DB session."""
    if not snapshots:
        return

    db = database.SessionLocal()
    try:
        for snapshot in snapshots:
            db.add(
                PtRunMetricPoint(
                    pt_run_id=run_id,
                    sampler_key=snapshot.sampler_key,
                    recorded_at=snapshot.recorded_at,
                    qps=snapshot.qps,
                    avg_rt_ms=snapshot.avg_rt_ms,
                    rt_p95_ms=snapshot.rt_p95_ms,
                    rt_p99_ms=snapshot.rt_p99_ms,
                    error_rate_percent=snapshot.error_rate_percent,
                )
            )
        db.commit()
    except Exception:
        logger.exception("Failed to persist metric points for run %s", run_id)
        db.rollback()
    finally:
        db.close()


def persist_error_log(run_id: uuid.UUID, sample: LoadSampleResult) -> None:
    """Persist a single failed request sample as an error log with sanitized message."""
    persist_error_logs_batch(run_id, [sample])


def persist_error_logs_batch(run_id: uuid.UUID, samples: list[LoadSampleResult]) -> None:
    """Persist a batch of failed samples in one DB transaction."""
    if not samples:
        return

    db = database.SessionLocal()
    try:
        for sample in samples:
            if sample.success or sample.error_type is None:
                continue
            db.add(
                PtRunErrorLog(
                    pt_run_id=run_id,
                    occurred_at=sample.occurred_at,
                    sampler_key=sample.sampler_key,
                    sampler_name=sample.sampler_name,
                    status_code=sample.status_code,
                    error_type=sample.error_type,
                    message=sanitize_error_message(sample.message),
                )
            )
        db.commit()
    except Exception:
        logger.exception("Failed to persist error logs for run %s", run_id)
        db.rollback()
    finally:
        db.close()


def flush_sampled_error_logs(run_id: uuid.UUID) -> None:
    """Persist a small sampled batch of recent errors without blocking metric writes."""
    sidecar = _run_sidecars.get(run_id)
    if sidecar is None or not sidecar.recent_errors:
        return

    settings = get_settings()
    remaining = max(settings.pt_error_log_max_per_run - sidecar.persisted_error_count, 0)
    if remaining <= 0:
        return

    batch_size = min(settings.pt_error_log_max_per_flush, remaining, len(sidecar.recent_errors))
    if batch_size <= 0:
        return

    samples = list(sidecar.recent_errors)[-batch_size:]
    persist_error_logs_batch(run_id, samples)
    sidecar.persisted_error_count += len(samples)


def _build_sample_recorder(
    run_id: uuid.UUID,
    aggregator: PtMetricsAggregator,
) -> Callable[[LoadSampleResult], None]:
    sidecar = _run_sidecars[run_id]

    def record_sample(sample: LoadSampleResult) -> None:
        aggregator.record(sample)
        if not sample.success:
            sidecar.recent_errors.append(sample)

    return record_sample


def _build_flush_handler(
    run_id: uuid.UUID,
    flush_handler: Callable[[list[MetricSnapshot]], None] | None,
) -> Callable[[list[MetricSnapshot]], None]:
    if flush_handler is not None:
        return flush_handler
    return lambda snapshots: persist_metric_snapshots(run_id, snapshots)


async def start_load_test(
    run_id: uuid.UUID,
    *,
    flush_handler: Callable[[list[MetricSnapshot]], None] | None = None,
) -> None:
    aggregator = PtMetricsAggregator()
    flush_stop = asyncio.Event()
    flush_task: asyncio.Task[None] | None = None
    outcome: _RunFinalizeOutcome | None = None
    effective_flush_handler = _build_flush_handler(run_id, flush_handler)
    run_started_at: datetime | None = None

    setup_db = database.SessionLocal()
    try:
        run = setup_db.get(PtRun, run_id)
        if run is None:
            logger.error("PtRun %s not found for orchestration", run_id)
            return

        await acquire_run_slot(run_id, setup_db)
        run_started_at = run.started_at
        config = LoadEngineConfig.from_snapshot(run.config_snapshot_json)
    finally:
        setup_db.close()

    _active_aggregators[run_id] = aggregator
    _run_sidecars[run_id] = _RunTelemetrySidecar()

    try:
        engine = PtLoadEngine(
            run_id,
            config,
            on_sample=_build_sample_recorder(run_id, aggregator),
            started_at=run_started_at,
        )
        flush_task = asyncio.create_task(
            _metrics_flush_loop(
                run_id,
                aggregator,
                flush_stop,
                flush_handler=effective_flush_handler,
            )
        )

        await engine.run()

        if engine.stop_reason == PtRunStopReason.MANUAL_CANCEL.value:
            final_status = PtRunStatus.CANCELLED.value
        else:
            final_status = PtRunStatus.COMPLETED.value

        outcome = _RunFinalizeOutcome(
            status=final_status,
            stop_reason=engine.stop_reason,
            error_message=None,
            include_summary=True,
        )
    except PtRunConflictError:
        outcome = _RunFinalizeOutcome(
            status=PtRunStatus.FAILED.value,
            stop_reason=PtRunStopReason.ENGINE_ERROR.value,
            error_message="Another load test is already running",
            include_summary=False,
        )
        raise
    except Exception as exc:
        logger.exception("Load test run %s failed", run_id)
        outcome = _RunFinalizeOutcome(
            status=PtRunStatus.FAILED.value,
            stop_reason=PtRunStopReason.ENGINE_ERROR.value,
            error_message=str(exc),
            include_summary=False,
        )
    finally:
        flush_stop.set()
        if flush_task is not None:
            flush_task.cancel()
            try:
                await flush_task
            except asyncio.CancelledError:
                pass

        final_snapshots = aggregator.build_flush_snapshots(_utcnow())
        active_final_snapshots = _active_metric_snapshots(final_snapshots)
        if active_final_snapshots:
            effective_flush_handler(active_final_snapshots)
        flush_sampled_error_logs(run_id)

        finalize_db = database.SessionLocal()
        try:
            if outcome is not None:
                ended_at = _utcnow()
                run = finalize_db.get(PtRun, run_id)
                summary_json = _build_final_summary_json(
                    aggregator=aggregator,
                    run_id=run_id,
                    run=run,
                    outcome=outcome,
                    ended_at=ended_at,
                )
                if run is not None:
                    _finalize_run(
                        finalize_db,
                        run,
                        status=outcome.status,
                        stop_reason=outcome.stop_reason,
                        summary_json=summary_json,
                        error_message=outcome.error_message,
                        ended_at=ended_at,
                    )
        finally:
            finalize_db.close()

        _active_aggregators.pop(run_id, None)
        _run_sidecars.pop(run_id, None)
        await release_run_slot(run_id)


async def cancel_load_test(run_id: uuid.UUID) -> None:
    engine = get_active_engine(run_id)
    if engine is None:
        raise PtRunNotRunningError(f"Load test run {run_id} is not active")
    engine.cancel()


def schedule_load_test(run_id: uuid.UUID) -> None:
    """Start a load test in a daemon thread so API handlers return immediately."""

    def _runner() -> None:
        try:
            asyncio.run(start_load_test(run_id))
        except Exception:
            logger.exception("Background load test failed for run %s", run_id)

    thread = threading.Thread(
        target=_runner,
        name=f"pt-load-{run_id}",
        daemon=True,
    )
    thread.start()


def enqueue_load_test(run_id: uuid.UUID) -> None:
    schedule_load_test(run_id)


def _active_metric_snapshots(snapshots: list[MetricSnapshot]) -> list[MetricSnapshot]:
    return [snapshot for snapshot in snapshots if snapshot.qps > 0]


async def _metrics_flush_loop(
    run_id: uuid.UUID,
    aggregator: PtMetricsAggregator,
    stop_event: asyncio.Event,
    *,
    flush_handler: Callable[[list[MetricSnapshot]], None] | None,
) -> None:
    settings = get_settings()
    interval = max(settings.pt_metrics_flush_interval_seconds, 1)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            snapshots = aggregator.build_flush_snapshots(_utcnow())
            active_snapshots = _active_metric_snapshots(snapshots)
            if flush_handler is not None and active_snapshots:
                flush_handler(active_snapshots)
            flush_sampled_error_logs(run_id)
            aggregator.reset_window()


def _build_final_summary_json(
    *,
    aggregator: PtMetricsAggregator,
    run_id: uuid.UUID,
    run: PtRun | None,
    outcome: _RunFinalizeOutcome,
    ended_at: datetime,
) -> dict[str, Any] | None:
    if not outcome.include_summary or run is None:
        return None
    return aggregator.build_summary_json(
        run_id=run_id,
        status=outcome.status,
        started_at=run.started_at,
        ended_at=ended_at,
        stop_reason=outcome.stop_reason,
    )


def _finalize_run(
    db: Session,
    run: PtRun,
    *,
    status: str,
    stop_reason: str | None,
    summary_json: dict[str, Any] | None,
    error_message: str | None,
    ended_at: datetime | None = None,
) -> None:
    run.status = status
    run.stop_reason = stop_reason
    run.summary_json = summary_json
    run.error_message = error_message
    run.ended_at = ended_at or _utcnow()
    db.commit()


__all__ = [
    "PtRunConflictError",
    "PtRunNotRunningError",
    "PtRunOrchestratorError",
    "acquire_run_slot",
    "build_config_snapshot_from_script",
    "cancel_load_test",
    "enqueue_load_test",
    "find_global_running_run",
    "flush_sampled_error_logs",
    "get_run_aggregator",
    "is_run_slot_busy",
    "persist_error_log",
    "persist_error_logs_batch",
    "persist_metric_snapshots",
    "release_run_slot",
    "schedule_load_test",
    "start_load_test",
    "validate_script_ready_for_run",
]
