"""HTTP load testing engine — asyncio workers with httpx."""

from __future__ import annotations

import asyncio
import logging
import time
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, TypedDict

import httpx

from app.config import get_settings
from app.models.pt_run import PtRunStopReason
from app.services.variable_resolver import rewrite_loopback_host

logger = logging.getLogger(__name__)

STOP_GRACE_SECONDS = 5.0


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class LoadErrorType(str, Enum):
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    OTHER = "other"


@dataclass(frozen=True)
class LoadEngineSampler:
    key: str
    name: str
    method: str
    url: str
    headers: dict[str, str]
    has_variables: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoadEngineSampler:
        headers = {
            str(item["name"]): str(item["value"])
            for item in data.get("headers", [])
            if isinstance(item, dict) and item.get("name")
        }
        return cls(
            key=str(data["key"]),
            name=str(data["name"]),
            method=str(data.get("method", "GET")).upper(),
            url=str(data["url"]),
            headers=headers,
            has_variables=bool(data.get("has_variables", False)),
        )


@dataclass(frozen=True)
class LoadEngineConfig:
    max_concurrency: int
    ramp_up_seconds: int
    stop_mode: str
    duration_seconds: int | None
    default_max_requests: int
    sampler_limits: dict[str, int]
    samplers: list[LoadEngineSampler]

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> LoadEngineConfig:
        samplers = [
            LoadEngineSampler.from_dict(item)
            for item in snapshot.get("samplers", [])
            if isinstance(item, dict) and item.get("key")
        ]
        return cls(
            max_concurrency=int(snapshot["max_concurrency"]),
            ramp_up_seconds=int(snapshot["ramp_up_seconds"]),
            stop_mode=str(snapshot["stop_mode"]),
            duration_seconds=(
                int(snapshot["duration_seconds"])
                if snapshot.get("duration_seconds") is not None
                else None
            ),
            default_max_requests=int(snapshot.get("default_max_requests", 1000)),
            sampler_limits={
                str(key): int(value)
                for key, value in (snapshot.get("sampler_limits") or {}).items()
            },
            samplers=samplers,
        )

    def sampler_request_limit(self, sampler_key: str) -> int:
        return self.sampler_limits.get(sampler_key, self.default_max_requests)


@dataclass(frozen=True)
class LoadSampleResult:
    sampler_key: str
    sampler_name: str
    status_code: int | None
    response_time_ms: float
    success: bool
    error_type: str | None
    message: str | None
    occurred_at: datetime


class SampleRecorder(Protocol):
    def __call__(self, sample: LoadSampleResult) -> None: ...


class LoadEngineState(TypedDict):
    run_id: uuid.UUID
    cancel_event: threading.Event
    active_workers: int
    sampler_request_counts: dict[str, int]
    started_at: datetime


_active_engines: dict[uuid.UUID, PtLoadEngine] = {}


def get_active_engine(run_id: uuid.UUID) -> PtLoadEngine | None:
    return _active_engines.get(run_id)


class PtLoadEngine:
    def __init__(
        self,
        run_id: uuid.UUID,
        config: LoadEngineConfig,
        *,
        on_sample: SampleRecorder | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self.run_id = run_id
        self.config = config
        self._on_sample = on_sample
        self.started_at = _ensure_utc(started_at or datetime.now(timezone.utc))
        self.cancel_event = threading.Event()
        self.stop_reason: str | None = None
        self._host_alias = get_settings().runner_host_alias
        self._stagger_delay = (
            config.ramp_up_seconds / config.max_concurrency
            if config.max_concurrency > 0
            else 0.0
        )
        self._executable_samplers = [
            sampler for sampler in config.samplers if not sampler.has_variables
        ]
        self._sampler_index = 0
        self._sampler_index_lock = asyncio.Lock()
        self._counts_lock = asyncio.Lock()
        self._workers_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._stopping = False
        self._active_workers = 0
        self._sampler_request_counts: dict[str, int] = {}
        self._in_flight = 0
        self._in_flight_lock = asyncio.Lock()

    @property
    def state(self) -> LoadEngineState:
        return LoadEngineState(
            run_id=self.run_id,
            cancel_event=self.cancel_event,
            active_workers=self._active_workers,
            sampler_request_counts=dict(self._sampler_request_counts),
            started_at=self.started_at,
        )

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.stop_reason is None:
            self.stop_reason = PtRunStopReason.MANUAL_CANCEL.value
        self._stopping = True

    async def run(self) -> None:
        if not self._executable_samplers:
            raise ValueError("No executable HTTP samplers available for load test")

        _active_engines[self.run_id] = self
        settings = get_settings()
        limits = httpx.Limits(
            max_connections=self.config.max_concurrency,
            max_keepalive_connections=self.config.max_concurrency,
        )

        try:
            async with httpx.AsyncClient(
                timeout=settings.pt_request_timeout_seconds,
                limits=limits,
                follow_redirects=False,
            ) as client:
                tasks = [
                    asyncio.create_task(self._worker(worker_id, client))
                    for worker_id in range(self.config.max_concurrency)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.exception("Load worker failed for run %s", self.run_id, exc_info=result)
                        await self._set_stop_reason(PtRunStopReason.ENGINE_ERROR.value)
                        raise result

                await self._wait_for_in_flight()
        finally:
            _active_engines.pop(self.run_id, None)

        if self.stop_reason is None:
            self.stop_reason = self._default_stop_reason()

    async def _worker(self, worker_id: int, client: httpx.AsyncClient) -> None:
        stagger_seconds = self._stagger_delay * worker_id
        if stagger_seconds > 0:
            await asyncio.sleep(stagger_seconds)

        async with self._workers_lock:
            self._active_workers += 1

        try:
            while not await self._should_stop():
                sampler = await self._next_sampler()
                if sampler is None:
                    break

                if await self._is_request_limit_reached(sampler.key):
                    await self._set_stop_reason(PtRunStopReason.REQUEST_LIMIT_REACHED.value)
                    break

                async with self._in_flight_lock:
                    self._in_flight += 1
                try:
                    sample = await self._execute_request(client, sampler)
                finally:
                    async with self._in_flight_lock:
                        self._in_flight -= 1

                await self._record_sample(sample)

                if (
                    self.config.stop_mode == "request_limit"
                    and await self._is_request_limit_reached(sampler.key)
                ):
                    await self._set_stop_reason(PtRunStopReason.REQUEST_LIMIT_REACHED.value)
                    break
        finally:
            async with self._workers_lock:
                self._active_workers -= 1

    async def _next_sampler(self) -> LoadEngineSampler | None:
        if not self._executable_samplers:
            return None
        async with self._sampler_index_lock:
            sampler = self._executable_samplers[self._sampler_index % len(self._executable_samplers)]
            self._sampler_index += 1
            return sampler

    async def _should_stop(self) -> bool:
        if self.cancel_event.is_set():
            await self._set_stop_reason(PtRunStopReason.MANUAL_CANCEL.value)
            return True
        if self._stopping:
            return True
        if self.config.stop_mode == "duration" and self.config.duration_seconds is not None:
            elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
            if elapsed >= self.config.duration_seconds:
                await self._set_stop_reason(PtRunStopReason.DURATION_REACHED.value)
                return True
        return False

    async def _set_stop_reason(self, reason: str) -> None:
        async with self._stop_lock:
            if self.stop_reason is None:
                self.stop_reason = reason
            self._stopping = True
            self.cancel_event.set()

    async def _is_request_limit_reached(self, sampler_key: str) -> bool:
        if self.config.stop_mode != "request_limit":
            return False
        async with self._counts_lock:
            current_count = self._sampler_request_counts.get(sampler_key, 0)
        return current_count >= self.config.sampler_request_limit(sampler_key)

    async def _record_sample(self, sample: LoadSampleResult) -> None:
        async with self._counts_lock:
            self._sampler_request_counts[sample.sampler_key] = (
                self._sampler_request_counts.get(sample.sampler_key, 0) + 1
            )
        if self._on_sample is not None:
            self._on_sample(sample)

    async def _execute_request(
        self,
        client: httpx.AsyncClient,
        sampler: LoadEngineSampler,
    ) -> LoadSampleResult:
        url = rewrite_loopback_host(sampler.url, self._host_alias)
        started = time.perf_counter()
        occurred_at = datetime.now(timezone.utc)
        try:
            response = await client.request(
                sampler.method,
                url,
                headers=sampler.headers or None,
            )
            response_time_ms = (time.perf_counter() - started) * 1000
            success = response.status_code < 400
            return LoadSampleResult(
                sampler_key=sampler.key,
                sampler_name=sampler.name,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                success=success,
                error_type=None if success else LoadErrorType.HTTP_ERROR.value,
                message=None if success else f"HTTP {response.status_code}",
                occurred_at=occurred_at,
            )
        except httpx.TimeoutException as exc:
            response_time_ms = (time.perf_counter() - started) * 1000
            return LoadSampleResult(
                sampler_key=sampler.key,
                sampler_name=sampler.name,
                status_code=None,
                response_time_ms=response_time_ms,
                success=False,
                error_type=LoadErrorType.TIMEOUT.value,
                message=str(exc),
                occurred_at=occurred_at,
            )
        except httpx.ConnectError as exc:
            response_time_ms = (time.perf_counter() - started) * 1000
            return LoadSampleResult(
                sampler_key=sampler.key,
                sampler_name=sampler.name,
                status_code=None,
                response_time_ms=response_time_ms,
                success=False,
                error_type=LoadErrorType.CONNECTION_ERROR.value,
                message=str(exc),
                occurred_at=occurred_at,
            )
        except Exception as exc:
            response_time_ms = (time.perf_counter() - started) * 1000
            return LoadSampleResult(
                sampler_key=sampler.key,
                sampler_name=sampler.name,
                status_code=None,
                response_time_ms=response_time_ms,
                success=False,
                error_type=LoadErrorType.OTHER.value,
                message=str(exc),
                occurred_at=occurred_at,
            )

    async def _wait_for_in_flight(self) -> None:
        deadline = time.monotonic() + STOP_GRACE_SECONDS
        while time.monotonic() < deadline:
            async with self._in_flight_lock:
                if self._in_flight <= 0:
                    return
            await asyncio.sleep(0.05)

    def _default_stop_reason(self) -> str:
        if self.config.stop_mode == "duration":
            return PtRunStopReason.DURATION_REACHED.value
        return PtRunStopReason.REQUEST_LIMIT_REACHED.value
