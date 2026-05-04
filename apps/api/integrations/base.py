import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class IntegrationError(Exception):
    def __init__(self, message: str, status_code: int | None, integration_name: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.integration_name = integration_name


class CircuitOpenError(IntegrationError):
    def __init__(self, integration_name: str, retry_after_seconds: float) -> None:
        super().__init__(
            f"Circuit open for {integration_name!r}, retry in {retry_after_seconds:.0f}s",
            status_code=None,
            integration_name=integration_name,
        )
        self.retry_after_seconds = retry_after_seconds


class RateLimitError(IntegrationError):
    def __init__(self, integration_name: str, retry_after_seconds: float) -> None:
        super().__init__(
            f"Rate limit hit for {integration_name!r}, retry in {retry_after_seconds:.1f}s",
            status_code=429,
            integration_name=integration_name,
        )
        self.retry_after_seconds = retry_after_seconds


# ── Token bucket (per-integration rate limiter) ───────────────────────────────

@dataclass
class _TokenBucket:
    max_tokens: float
    refill_rate: float          # tokens per second
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.max_tokens)
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        """Return True if a token was consumed; False if empty."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.max_tokens, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    @property
    def seconds_until_token(self) -> float:
        return max(0.0, (1 - self._tokens) / self.refill_rate)


# ── Circuit breaker ───────────────────────────────────────────────────────────

@dataclass
class _CircuitBreaker:
    failure_threshold: int = 5
    open_duration_seconds: float = 60.0
    _failures: int = 0
    _opened_at: float | None = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.open_duration_seconds:
            self._failures = 0
            self._opened_at = None
            return False
        return True

    def retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.open_duration_seconds - (time.monotonic() - self._opened_at))

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()


# ── BaseIntegration ───────────────────────────────────────────────────────────

_RETRY_STATUSES = {429, 500, 502, 503}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds — doubles each retry
_DEFAULT_TIMEOUT = 30.0  # seconds — generous for async event-loop environments


class BaseIntegration(ABC):
    name: str
    base_url: str
    max_requests_per_minute: int = 60

    def __init__(self) -> None:
        rpm = self.max_requests_per_minute
        self._bucket = _TokenBucket(max_tokens=rpm, refill_rate=rpm / 60.0)
        self._circuit = _CircuitBreaker()

    # ── Public interface ──────────────────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict:
        if self._circuit.is_open():
            raise CircuitOpenError(self.name, self._circuit.retry_after())

        if not self._bucket.consume():
            raise RateLimitError(self.name, self._bucket.seconds_until_token)

        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                    response = await client.request(method, url, **kwargs)
                response_ms = int((time.monotonic() - t0) * 1000)

                logger.info(
                    "integration_request",
                    extra={
                        "integration": self.name,
                        "method": method,
                        "url": url,
                        "status_code": response.status_code,
                        "response_time_ms": response_ms,
                        "attempt": attempt + 1,
                    },
                )

                if response.status_code in _RETRY_STATUSES:
                    last_error = IntegrationError(
                        f"HTTP {response.status_code}",
                        response.status_code,
                        self.name,
                    )
                    if attempt < _MAX_RETRIES - 1:
                        await _async_sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue

                response.raise_for_status()
                self._circuit.record_success()
                return response.json()

            except (IntegrationError, CircuitOpenError, RateLimitError):
                raise
            except httpx.HTTPStatusError as exc:
                # 4xx (excluding retriable ones already handled above) — don't retry
                self._circuit.record_failure()
                raise IntegrationError(
                    f"HTTP {exc.response.status_code}: {exc}",
                    status_code=exc.response.status_code,
                    integration_name=self.name,
                ) from exc
            except Exception as exc:
                response_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(
                    "integration_request_error",
                    extra={
                        "integration": self.name,
                        "method": method,
                        "url": url,
                        "error": str(exc),
                        "response_time_ms": response_ms,
                        "attempt": attempt + 1,
                    },
                )
                last_error = exc
                if attempt < _MAX_RETRIES - 1:
                    await _async_sleep(_BACKOFF_BASE * (2 ** attempt))

        self._circuit.record_failure()
        raise IntegrationError(
            f"All {_MAX_RETRIES} attempts failed: {last_error}",
            status_code=None,
            integration_name=self.name,
        ) from last_error

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict: ...

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_org_settings(self, org_id: str, db: AsyncSession) -> dict:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT settings FROM organizations WHERE id = :org_id"),
            {"org_id": org_id},
        )
        row = result.fetchone()
        return row[0] if row else {}


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
