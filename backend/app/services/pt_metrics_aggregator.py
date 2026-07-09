"""In-memory load test metrics aggregation — RT percentiles and QPS."""

from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.services.pt_load_engine import LoadSampleResult

AGGREGATE_SAMPLER_KEY = "__aggregate__"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile; ``p`` is 0–100 (e.g. 95 for P95)."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank_index = math.ceil(len(sorted_values) * p / 100) - 1
    rank_index = max(0, min(rank_index, len(sorted_values) - 1))
    return sorted_values[rank_index]


@dataclass
class SamplerStats:
    response_times_ms: list[float] = field(default_factory=list)
    total_requests: int = 0
    failed_requests: int = 0
    window_requests: int = 0


@dataclass(frozen=True)
class MetricSnapshot:
    sampler_key: str
    recorded_at: datetime
    qps: float
    avg_rt_ms: float
    rt_p95_ms: float | None
    rt_p99_ms: float | None
    error_rate_percent: float


@dataclass(frozen=True)
class InterfaceSummary:
    sampler_key: str
    name: str
    rt_p99_ms: float
    rt_p95_ms: float
    qps: float
    error_rate_percent: float
    total_requests: int
    failed_requests: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "sampler_key": self.sampler_key,
            "name": self.name,
            "rt_p99_ms": round(self.rt_p99_ms, 2),
            "rt_p95_ms": round(self.rt_p95_ms, 2),
            "qps": round(self.qps, 2),
            "error_rate_percent": round(self.error_rate_percent, 2),
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
        }


class PtMetricsAggregator:
    def __init__(
        self,
        *,
        flush_interval_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._flush_interval_seconds = (
            flush_interval_seconds
            if flush_interval_seconds is not None
            else settings.pt_metrics_flush_interval_seconds
        )
        self._lock = threading.Lock()
        self._sampler_stats: dict[str, SamplerStats] = {}
        self._sampler_names: dict[str, str] = {}
        self._aggregate_stats = SamplerStats()

    def record(self, sample: LoadSampleResult) -> None:
        with self._lock:
            sampler_stats = self._sampler_stats.setdefault(sample.sampler_key, SamplerStats())
            self._sampler_names[sample.sampler_key] = sample.sampler_name
            self._apply_sample(sampler_stats, sample)
            self._apply_sample(self._aggregate_stats, sample)

    def build_flush_snapshots(self, recorded_at: datetime) -> list[MetricSnapshot]:
        with self._lock:
            snapshots: list[MetricSnapshot] = []
            for sampler_key, stats in self._sampler_stats.items():
                snapshots.append(
                    self._build_snapshot(
                        sampler_key=sampler_key,
                        stats=stats,
                        recorded_at=recorded_at,
                    )
                )
            snapshots.append(
                self._build_snapshot(
                    sampler_key=AGGREGATE_SAMPLER_KEY,
                    stats=self._aggregate_stats,
                    recorded_at=recorded_at,
                )
            )
            return snapshots

    def reset_window(self) -> None:
        with self._lock:
            for stats in self._sampler_stats.values():
                stats.window_requests = 0
            self._aggregate_stats.window_requests = 0

    def build_summary_json(
        self,
        *,
        run_id: uuid.UUID,
        status: str,
        started_at: datetime,
        ended_at: datetime,
        stop_reason: str | None,
    ) -> dict[str, object]:
        duration_seconds = max(
            (_ensure_utc(ended_at) - _ensure_utc(started_at)).total_seconds(),
            0.001,
        )
        with self._lock:
            interfaces = [
                self._build_interface_summary(
                    sampler_key=sampler_key,
                    stats=stats,
                    duration_seconds=duration_seconds,
                )
                for sampler_key, stats in sorted(self._sampler_stats.items())
            ]

        return {
            "run_id": str(run_id),
            "status": status,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "stop_reason": stop_reason,
            "interfaces": [item.to_dict() for item in interfaces],
        }

    def build_interim_summary_json(
        self,
        *,
        run_id: uuid.UUID,
        status: str,
        started_at: datetime,
        stop_reason: str | None,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        return self.build_summary_json(
            run_id=run_id,
            status=status,
            started_at=started_at,
            ended_at=now,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _apply_sample(stats: SamplerStats, sample: LoadSampleResult) -> None:
        stats.response_times_ms.append(sample.response_time_ms)
        stats.total_requests += 1
        stats.window_requests += 1
        if not sample.success:
            stats.failed_requests += 1

    def _build_snapshot(
        self,
        *,
        sampler_key: str,
        stats: SamplerStats,
        recorded_at: datetime,
    ) -> MetricSnapshot:
        interval = max(float(self._flush_interval_seconds), 0.001)
        qps = stats.window_requests / interval
        avg_rt_ms = self._average(stats.response_times_ms)
        return MetricSnapshot(
            sampler_key=sampler_key,
            recorded_at=recorded_at,
            qps=qps,
            avg_rt_ms=avg_rt_ms,
            rt_p95_ms=self._percentile_or_none(stats.response_times_ms, 95),
            rt_p99_ms=self._percentile_or_none(stats.response_times_ms, 99),
            error_rate_percent=self._error_rate_percent(stats),
        )

    def _build_interface_summary(
        self,
        *,
        sampler_key: str,
        stats: SamplerStats,
        duration_seconds: float,
    ) -> InterfaceSummary:
        qps = stats.total_requests / duration_seconds
        return InterfaceSummary(
            sampler_key=sampler_key,
            name=self._sampler_names.get(sampler_key, sampler_key),
            rt_p99_ms=percentile(stats.response_times_ms, 99),
            rt_p95_ms=percentile(stats.response_times_ms, 95),
            qps=qps,
            error_rate_percent=self._error_rate_percent(stats),
            total_requests=stats.total_requests,
            failed_requests=stats.failed_requests,
        )

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _percentile_or_none(values: list[float], p: float) -> float | None:
        if not values:
            return None
        return percentile(values, p)

    @staticmethod
    def _error_rate_percent(stats: SamplerStats) -> float:
        if stats.total_requests == 0:
            return 0.0
        return stats.failed_requests / stats.total_requests * 100
