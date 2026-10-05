"""Auth, rate limiting, PII redaction, credit budget guard."""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from base64 import b64encode

from app.core.errors import BudgetExceeded, RateLimited, Unauthorized

# ---------------- PII redaction ----------------
# Contest rule + DPDP hygiene: never persist Aadhaar / PAN / phone / account numbers.
PII_PATTERNS = [
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I)),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("ACCOUNT", re.compile(r"(?<!\d)\d{11,18}(?!\d)")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
]


def redact(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    for label, pat in PII_PATTERNS:
        if pat.search(text):
            found.append(label)
            text = pat.sub(f"[{label}]", text)
    return text, found


def hash_caller(number: str, salt: str) -> str:
    return hashlib.sha256((salt + number).encode()).hexdigest()[:16] if number else ""


# ---------------- admin auth ----------------
def check_admin(provided: str | None, expected: str) -> None:
    if not provided or not hmac.compare_digest(provided, expected):
        raise Unauthorized("Valid X-Admin-Key header required")


# ---------------- rate limiting (token bucket per client) ----------------
class RateLimiter:
    def __init__(self, per_minute: int):
        self.rate = per_minute / 60.0
        self.capacity = float(per_minute)
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                self.buckets[key] = (tokens, now)
                raise RateLimited("Too many requests, slow down", details={"retry_after_s": round((1 - tokens) / self.rate, 1)})
            self.buckets[key] = (tokens - 1, now)
            if len(self.buckets) > 50_000:  # bound memory
                self.buckets.clear()


# ---------------- credit guard ----------------
class CreditGuard:
    """Tracks estimated programme-credit burn and refuses new paid calls past the budget.
    Rates are configurable because pricing is shown on the Gnani dashboard."""

    def __init__(self, db, budget: float, stt_per_min: float, tts_per_1k: float, alert_ratio: float):
        self.db, self.budget, self.stt_per_min, self.tts_per_1k, self.alert = db, budget, stt_per_min, tts_per_1k, alert_ratio

    def ensure_available(self) -> None:
        if self.db.credits_used() >= self.budget:
            raise BudgetExceeded("Programme credit budget exhausted; raise CREDIT_BUDGET or top up")

    def record_stt(self, seconds: float) -> None:
        self.db.add_usage("stt_seconds", seconds, seconds / 60 * self.stt_per_min)

    def record_tts(self, chars: int) -> None:
        self.db.add_usage("tts_chars", chars, chars / 1000 * self.tts_per_1k)

    def status(self) -> dict:
        used = self.db.credits_used()
        return {"budget": self.budget, "used": round(used, 2), "remaining": round(self.budget - used, 2),
                "alert": used >= self.alert * self.budget}


# ---------------- Twilio webhook signature ----------------
def twilio_signature_valid(auth_token: str, url: str, params: dict, signature: str) -> bool:
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(digest, signature or "")
