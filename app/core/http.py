"""Resilient HTTP: exponential backoff with jitter on 429/5xx/network errors,
plus a simple circuit breaker so a dead upstream fails fast instead of piling up."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

import httpx

from app.core.errors import UpstreamError
from app.core.logging import log

logger = logging.getLogger("kural.http")
RETRYABLE = {429, 500, 502, 503, 504}


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, cooldown_s: float = 30.0):
        self.name, self.threshold, self.cooldown_s = name, threshold, cooldown_s
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at > self.cooldown_s:
            self.opened_at = None  # half-open: allow a trial request
            self.failures = self.threshold - 1
            return False
        return True

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()
            log(logger, logging.ERROR, "circuit_open", upstream=self.name)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    breaker: CircuitBreaker,
    max_retries: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    if breaker.is_open:
        raise UpstreamError(f"{breaker.name} temporarily unavailable (circuit open)")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in RETRYABLE and attempt < max_retries:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else _backoff(attempt)
                log(logger, logging.WARNING, "upstream_retry", upstream=breaker.name,
                    status=resp.status_code, attempt=attempt + 1, delay=round(delay, 2))
                await asyncio.sleep(delay)
                continue
            if resp.status_code >= 400:
                breaker.failure() if resp.status_code >= 500 else None
                raise UpstreamError(
                    f"{breaker.name} returned {resp.status_code}",
                    details={"status": resp.status_code, "body": _safe_body(resp)},
                )
            breaker.success()
            return resp
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(_backoff(attempt))
                continue
    breaker.failure()
    raise UpstreamError(f"{breaker.name} unreachable: {last_exc!r}")


def _backoff(attempt: int) -> float:
    return min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.25)


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]
