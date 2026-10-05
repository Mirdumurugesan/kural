"""Typed errors mapped to consistent JSON API responses."""
from __future__ import annotations


class KuralError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequest(KuralError):
    status_code = 400
    code = "BAD_REQUEST"


class Unauthorized(KuralError):
    status_code = 401
    code = "UNAUTHORIZED"


class RateLimited(KuralError):
    status_code = 429
    code = "RATE_LIMITED"


class UpstreamError(KuralError):
    """A Gnani / Evon call failed after retries."""

    status_code = 502
    code = "UPSTREAM_ERROR"


class BudgetExceeded(KuralError):
    status_code = 402
    code = "CREDIT_BUDGET_EXCEEDED"
