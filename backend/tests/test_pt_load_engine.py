import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from app.models.pt_run import PtRunStopReason
from app.services.pt_load_engine import (
    LoadEngineConfig,
    LoadEngineSampler,
    LoadSampleResult,
    PtLoadEngine,
    get_active_engine,
)
from app.services.pt_metrics_aggregator import PtMetricsAggregator


def _sampler(
    *,
    key: str = "sampler-001",
    name: str = "Test API",
    url: str = "https://mock.test/api",
    has_variables: bool = False,
) -> LoadEngineSampler:
    return LoadEngineSampler(
        key=key,
        name=name,
        method="GET",
        url=url,
        headers={},
        has_variables=has_variables,
    )


def _build_config(
    *,
    max_concurrency: int = 2,
    ramp_up_seconds: int = 0,
    stop_mode: str = "duration",
    duration_seconds: int | None = 1,
    default_max_requests: int = 1000,
    sampler_limits: dict[str, int] | None = None,
    samplers: list[LoadEngineSampler] | None = None,
) -> LoadEngineConfig:
    return LoadEngineConfig(
        max_concurrency=max_concurrency,
        ramp_up_seconds=ramp_up_seconds,
        stop_mode=stop_mode,
        duration_seconds=duration_seconds,
        default_max_requests=default_max_requests,
        sampler_limits=sampler_limits or {},
        samplers=samplers or [_sampler()],
    )


@contextmanager
def _mock_httpx_transport(handler):
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    with patch("app.services.pt_load_engine.httpx.AsyncClient", side_effect=client_factory):
        yield


class _GateAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self.release.wait()
        return httpx.Response(200, text="ok")


@contextmanager
def _mock_async_transport(transport: httpx.AsyncBaseTransport):
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    with patch("app.services.pt_load_engine.httpx.AsyncClient", side_effect=client_factory):
        yield


def _run_engine(config: LoadEngineConfig, samples: list[LoadSampleResult]) -> PtLoadEngine:
    async def _execute() -> PtLoadEngine:
        engine = PtLoadEngine(uuid.uuid4(), config, on_sample=samples.append)
        await engine.run()
        return engine

    return asyncio.run(_execute())


def test_duration_mode_completes_with_mock_server() -> None:
    samples: list[LoadSampleResult] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://mock.test/api"
        return httpx.Response(200, text="ok")

    config = _build_config(duration_seconds=1, max_concurrency=2)
    with _mock_httpx_transport(handler):
        engine = _run_engine(config, samples)

    assert engine.stop_reason == PtRunStopReason.DURATION_REACHED.value
    assert len(samples) >= 1
    assert all(sample.success for sample in samples)


def test_request_limit_mode_stops_at_limit() -> None:
    samples: list[LoadSampleResult] = []
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, text="ok")

    config = _build_config(
        stop_mode="request_limit",
        duration_seconds=None,
        default_max_requests=5,
        max_concurrency=2,
    )
    with _mock_httpx_transport(handler):
        engine = _run_engine(config, samples)

    assert engine.stop_reason == PtRunStopReason.REQUEST_LIMIT_REACHED.value
    assert request_count == 5
    assert len(samples) == 5


def test_manual_cancel_stops_engine() -> None:
    samples: list[LoadSampleResult] = []
    transport = _GateAsyncTransport()

    config = _build_config(
        stop_mode="duration",
        duration_seconds=3600,
        max_concurrency=1,
    )

    async def _execute() -> PtLoadEngine:
        engine = PtLoadEngine(uuid.uuid4(), config, on_sample=samples.append)
        with _mock_async_transport(transport):
            task = asyncio.create_task(engine.run())
            await asyncio.sleep(0.05)
            engine.cancel()
            transport.release.set()
            await asyncio.wait_for(task, timeout=5)
        return engine

    engine = asyncio.run(_execute())
    assert engine.stop_reason == PtRunStopReason.MANUAL_CANCEL.value
    assert len(samples) <= 2


def test_records_http_errors_from_mock_server() -> None:
    samples: list[LoadSampleResult] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    config = _build_config(
        stop_mode="request_limit",
        duration_seconds=None,
        default_max_requests=2,
        max_concurrency=1,
    )
    with _mock_httpx_transport(handler):
        engine = _run_engine(config, samples)

    assert len(samples) == 2
    assert all(not sample.success for sample in samples)
    assert all(sample.error_type == "http_error" for sample in samples)
    assert all(sample.status_code == 503 for sample in samples)
    assert engine.stop_reason == PtRunStopReason.REQUEST_LIMIT_REACHED.value


def test_records_connection_errors_from_mock_server() -> None:
    samples: list[LoadSampleResult] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    config = _build_config(
        stop_mode="request_limit",
        duration_seconds=None,
        default_max_requests=1,
        max_concurrency=1,
    )
    with _mock_httpx_transport(handler):
        engine = _run_engine(config, samples)

    assert len(samples) == 1
    assert samples[0].success is False
    assert samples[0].error_type == "connection_error"
    assert samples[0].status_code is None


def test_skips_samplers_with_variables() -> None:
    with pytest.raises(ValueError, match="No executable HTTP samplers"):
        config = _build_config(
            samplers=[_sampler(has_variables=True)],
        )
        _run_engine(config, [])


def test_engine_registers_active_instance_during_run() -> None:
    first_request_seen = asyncio.Event()

    def handler(_: httpx.Request) -> httpx.Response:
        first_request_seen.set()
        return httpx.Response(200, text="ok")

    config = _build_config(
        stop_mode="request_limit",
        duration_seconds=None,
        default_max_requests=100,
        max_concurrency=1,
    )

    async def _execute() -> bool:
        run_id = uuid.uuid4()
        engine = PtLoadEngine(run_id, config)

        with _mock_httpx_transport(handler):
            task = asyncio.create_task(engine.run())
            await first_request_seen.wait()
            seen_active = get_active_engine(run_id) is not None
            engine.cancel()
            await task
        return seen_active

    assert asyncio.run(_execute()) is True


def test_engine_samples_flow_into_metrics_aggregator() -> None:
    aggregator = PtMetricsAggregator(flush_interval_seconds=3)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    config = _build_config(
        stop_mode="request_limit",
        duration_seconds=None,
        default_max_requests=3,
        max_concurrency=1,
    )

    async def _execute() -> None:
        engine = PtLoadEngine(
            uuid.uuid4(),
            config,
            on_sample=aggregator.record,
        )
        with _mock_httpx_transport(handler):
            await engine.run()

    asyncio.run(_execute())
    now = datetime.now(timezone.utc)
    summary = aggregator.build_summary_json(
        run_id=uuid.uuid4(),
        status="completed",
        started_at=now,
        ended_at=now,
        stop_reason="request_limit_reached",
    )
    assert summary["interfaces"][0]["total_requests"] == 3


def test_engine_accepts_naive_started_at_for_duration_stop() -> None:
    naive_started_at = datetime(2026, 7, 3, 10, 0, 0)
    config = _build_config(
        stop_mode="duration",
        duration_seconds=1,
        max_concurrency=1,
    )

    async def _execute() -> str | None:
        engine = PtLoadEngine(
            uuid.uuid4(),
            config,
            started_at=naive_started_at,
        )
        with _mock_httpx_transport(lambda _: httpx.Response(200, text="ok")):
            await engine.run()
        return engine.stop_reason

    assert asyncio.run(_execute()) == PtRunStopReason.DURATION_REACHED.value
