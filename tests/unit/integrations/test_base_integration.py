"""Unit tests for BaseIntegration: retry, circuit breaker, rate limiter."""
import time
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from integrations.base import (
    BaseIntegration,
    CircuitOpenError,
    IntegrationError,
    RateLimitError,
    _CircuitBreaker,
    _TokenBucket,
)


# ── Concrete stub ─────────────────────────────────────────────────────────────

class _StubIntegration(BaseIntegration):
    name = "stub"
    base_url = "https://api.stub.test"
    max_requests_per_minute = 600  # high limit so rate-limiter doesn't interfere

    async def health_check(self) -> bool:
        try:
            await self.request("GET", "/health")
            return True
        except Exception:
            return False

    async def get_credentials(self, org_id: str, db: Any) -> dict:
        return {}


@pytest.fixture
def stub() -> _StubIntegration:
    return _StubIntegration()


# ── Retry tests ───────────────────────────────────────────────────────────────

@respx.mock
async def test_retry_fires_on_500(stub: _StubIntegration) -> None:
    """Three consecutive 500s should exhaust retries and raise IntegrationError."""
    respx.get("https://api.stub.test/health").mock(
        return_value=httpx.Response(500, json={"error": "server error"})
    )

    with pytest.raises(IntegrationError) as exc_info:
        await stub.request("GET", "/health")

    assert exc_info.value.integration_name == "stub"
    # All 3 attempts fired
    assert respx.calls.call_count == 3


@respx.mock
async def test_retry_succeeds_on_second_attempt(stub: _StubIntegration) -> None:
    """First attempt 500, second attempt 200 — should return data."""
    route = respx.get("https://api.stub.test/data")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"ok": True}),
    ]

    result = await stub.request("GET", "/data")

    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_retry_on_502_and_503(stub: _StubIntegration) -> None:
    """502 and 503 are both retry-eligible."""
    route = respx.get("https://api.stub.test/data")
    route.side_effect = [
        httpx.Response(502),
        httpx.Response(503),
        httpx.Response(200, json={"result": "ok"}),
    ]

    result = await stub.request("GET", "/data")
    assert result == {"result": "ok"}
    assert route.call_count == 3


@respx.mock
async def test_no_retry_on_404(stub: _StubIntegration) -> None:
    """404 is not a retry-eligible status."""
    respx.get("https://api.stub.test/missing").mock(return_value=httpx.Response(404))

    with pytest.raises(Exception):
        await stub.request("GET", "/missing")

    assert respx.calls.call_count == 1


# ── Circuit breaker tests ─────────────────────────────────────────────────────

@respx.mock
async def test_circuit_opens_after_5_failures(stub: _StubIntegration) -> None:
    """After 5 total exhausted retries the circuit must open."""
    respx.get("https://api.stub.test/health").mock(return_value=httpx.Response(500))

    # Each call exhausts 3 retries → 5 such calls trip the breaker
    for _ in range(5):
        with pytest.raises(IntegrationError):
            await stub.request("GET", "/health")

    assert stub._circuit.is_open()


@respx.mock
async def test_circuit_open_rejects_without_attempting_request(
    stub: _StubIntegration,
) -> None:
    """Once open, the circuit should raise CircuitOpenError immediately."""
    # Force the circuit open
    stub._circuit._failures = 5
    stub._circuit._opened_at = time.monotonic()

    with pytest.raises(CircuitOpenError) as exc_info:
        await stub.request("GET", "/health")

    assert exc_info.value.integration_name == "stub"
    assert exc_info.value.retry_after_seconds > 0
    # httpx was never called
    assert respx.calls.call_count == 0


@respx.mock
async def test_circuit_closes_after_open_duration(stub: _StubIntegration) -> None:
    """After the open window expires the circuit should self-heal."""
    stub._circuit._failures = 5
    stub._circuit._opened_at = time.monotonic() - 61  # expired

    respx.get("https://api.stub.test/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    result = await stub.request("GET", "/health")
    assert result == {"status": "ok"}


# ── Rate limiter tests ────────────────────────────────────────────────────────

@respx.mock
async def test_rate_limit_raises_when_bucket_empty() -> None:
    """An empty token bucket should raise RateLimitError without touching httpx."""
    integration = _StubIntegration()
    integration.max_requests_per_minute = 1
    integration._bucket = _TokenBucket(max_tokens=1, refill_rate=1 / 60.0)
    integration._bucket._tokens = 0.0  # drain the bucket

    with pytest.raises(RateLimitError) as exc_info:
        await integration.request("GET", "/anything")

    assert exc_info.value.integration_name == "stub"
    assert respx.calls.call_count == 0


# ── Token bucket unit tests ───────────────────────────────────────────────────

def test_token_bucket_consume_succeeds_when_full() -> None:
    bucket = _TokenBucket(max_tokens=10, refill_rate=1.0)
    assert bucket.consume() is True


def test_token_bucket_consume_fails_when_empty() -> None:
    bucket = _TokenBucket(max_tokens=1, refill_rate=1 / 60.0)
    bucket._tokens = 0.0
    assert bucket.consume() is False


def test_token_bucket_seconds_until_token() -> None:
    bucket = _TokenBucket(max_tokens=10, refill_rate=2.0)
    bucket._tokens = 0.0
    assert bucket.seconds_until_token == pytest.approx(0.5, abs=0.01)


# ── Circuit breaker unit tests ────────────────────────────────────────────────

def test_circuit_breaker_starts_closed() -> None:
    cb = _CircuitBreaker()
    assert cb.is_open() is False


def test_circuit_breaker_opens_at_threshold() -> None:
    cb = _CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False
    cb.record_failure()
    assert cb.is_open() is True


def test_circuit_breaker_resets_on_success() -> None:
    cb = _CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is True
    cb.record_success()
    assert cb.is_open() is False


def test_circuit_breaker_retry_after_decreases_over_time() -> None:
    cb = _CircuitBreaker(open_duration_seconds=60)
    cb._failures = 5
    cb._opened_at = time.monotonic() - 30  # opened 30s ago
    assert 28 < cb.retry_after() < 32
