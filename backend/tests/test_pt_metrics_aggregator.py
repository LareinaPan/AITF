import uuid
from datetime import datetime, timezone

from app.services.pt_load_engine import LoadSampleResult
from app.services.pt_metrics_aggregator import (
    AGGREGATE_SAMPLER_KEY,
    PtMetricsAggregator,
    percentile,
)


def _sample(
    *,
    sampler_key: str,
    sampler_name: str,
    response_time_ms: float,
    success: bool,
) -> LoadSampleResult:
    return LoadSampleResult(
        sampler_key=sampler_key,
        sampler_name=sampler_name,
        status_code=200 if success else 500,
        response_time_ms=response_time_ms,
        success=success,
        error_type=None if success else "http_error",
        message=None,
        occurred_at=datetime.now(timezone.utc),
    )


def test_percentile_empty_returns_zero() -> None:
    assert percentile([], 95) == 0.0


def test_percentile_single_value() -> None:
    assert percentile([42.0], 95) == 42.0
    assert percentile([42.0], 99) == 42.0


def test_percentile_nearest_rank() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(values, 95) == 100.0
    assert percentile(values, 50) == 50.0


def test_record_builds_cumulative_percentiles() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)
    for latency in [100.0, 200.0, 300.0, 400.0, 500.0]:
        aggregator.record(
            _sample(
                sampler_key="sampler-001",
                sampler_name="Login API",
                response_time_ms=latency,
                success=True,
            )
        )

    snapshots = aggregator.build_flush_snapshots(datetime.now(timezone.utc))
    sampler_snapshot = next(item for item in snapshots if item.sampler_key == "sampler-001")
    assert sampler_snapshot.rt_p95_ms == 500.0
    assert sampler_snapshot.rt_p99_ms == 500.0
    assert sampler_snapshot.avg_rt_ms == 300.0
    assert sampler_snapshot.error_rate_percent == 0.0


def test_window_qps_resets_after_flush() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=2)
    aggregator.record(
        _sample(
            sampler_key="sampler-001",
            sampler_name="Login API",
            response_time_ms=100.0,
            success=True,
        )
    )
    aggregator.record(
        _sample(
            sampler_key="sampler-001",
            sampler_name="Login API",
            response_time_ms=120.0,
            success=True,
        )
    )

    first_flush = aggregator.build_flush_snapshots(datetime.now(timezone.utc))
    sampler_snapshot = next(item for item in first_flush if item.sampler_key == "sampler-001")
    assert sampler_snapshot.qps == 1.0

    aggregator.reset_window()
    second_flush = aggregator.build_flush_snapshots(datetime.now(timezone.utc))
    sampler_snapshot = next(item for item in second_flush if item.sampler_key == "sampler-001")
    assert sampler_snapshot.qps == 0.0
    assert sampler_snapshot.rt_p95_ms == 120.0


def test_aggregate_snapshot_included() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)
    aggregator.record(
        _sample(
            sampler_key="sampler-001",
            sampler_name="A",
            response_time_ms=100.0,
            success=True,
        )
    )
    aggregator.record(
        _sample(
            sampler_key="sampler-002",
            sampler_name="B",
            response_time_ms=300.0,
            success=False,
        )
    )

    snapshots = aggregator.build_flush_snapshots(datetime.now(timezone.utc))
    aggregate = next(item for item in snapshots if item.sampler_key == AGGREGATE_SAMPLER_KEY)
    assert aggregate.avg_rt_ms == 200.0
    assert aggregate.error_rate_percent == 50.0


def test_build_summary_json_structure() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)
    aggregator.record(
        _sample(
            sampler_key="sampler-001",
            sampler_name="Login API",
            response_time_ms=100.0,
            success=True,
        )
    )
    aggregator.record(
        _sample(
            sampler_key="sampler-001",
            sampler_name="Login API",
            response_time_ms=200.0,
            success=False,
        )
    )

    run_id = uuid.uuid4()
    started_at = datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 7, 3, 10, 0, 10, tzinfo=timezone.utc)
    summary = aggregator.build_summary_json(
        run_id=run_id,
        status="completed",
        started_at=started_at,
        ended_at=ended_at,
        stop_reason="duration_reached",
    )

    assert summary["run_id"] == str(run_id)
    assert summary["status"] == "completed"
    assert summary["stop_reason"] == "duration_reached"
    assert len(summary["interfaces"]) == 1
    interface = summary["interfaces"][0]
    assert interface["sampler_key"] == "sampler-001"
    assert interface["name"] == "Login API"
    assert interface["total_requests"] == 2
    assert interface["failed_requests"] == 1
    assert interface["error_rate_percent"] == 50.0
    assert interface["qps"] == 0.2
