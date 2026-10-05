"""Gnani Evon v3.3 (30B MoE, ~3.5B active, 128K ctx, 11 Indian languages).

Open weights: https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B
Served through any OpenAI-compatible server, e.g.:
    vllm serve gnani/gnani-evon-v3.3-30B-A3B --trust-remote-code --max-model-len 32768
If Evon is unreachable, the pipeline degrades to an extractive answer from the
top retrieved passage, so the helpline never goes silent.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.core.errors import UpstreamError
from app.core.http import CircuitBreaker, request_with_retry
from app.core.logging import log

logger = logging.getLogger("kural.evon")
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


class EvonLLM:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.s = settings
        self.client = client
        self.breaker = CircuitBreaker("gnani-evon", threshold=3, cooldown_s=60)
        self._down_until = 0.0  # unreachable Evon -> fail fast for a minute instead of waiting on every call

    async def chat(self, messages: list[dict], max_tokens: int | None = None) -> LLMResult:
        t0 = time.perf_counter()
        if self.s.provider_mode == "mock":
            return LLMResult(_mock_answer(messages), "mock-evon", 1)
        if time.monotonic() < self._down_until:
            raise UpstreamError("gnani-evon marked unreachable (retrying in <60s)")
        try:
            resp = await self._post(messages, max_tokens)
        except UpstreamError as exc:
            if "unreachable" in exc.message or "circuit open" in exc.message:
                self._down_until = time.monotonic() + 60
            raise
        body = resp.json()
        return self._parse(body, t0)

    async def _post(self, messages: list[dict], max_tokens: int | None):
        return await request_with_retry(
            self.client, "POST", f"{self.s.evon_base_url.rstrip('/')}/chat/completions",
            breaker=self.breaker, max_retries=0,
            headers={"Authorization": f"Bearer {self.s.evon_api_key}"},
            json={"model": self.s.evon_model, "messages": messages,
                  "max_tokens": max_tokens or self.s.evon_max_tokens,
                  "temperature": self.s.evon_temperature,
                  "chat_template_kwargs": {"enable_thinking": self.s.evon_enable_thinking}},
            timeout=httpx.Timeout(60.0, connect=2.0),
        )

    def _parse(self, body: dict, t0: float) -> LLMResult:
        text = body["choices"][0]["message"]["content"] or ""
        text = THINK_RE.sub("", text).strip()  # drop reasoning trace if the model emits one
        usage = body.get("usage") or {}
        latency = int((time.perf_counter() - t0) * 1000)
        log(logger, logging.INFO, "evon_done", latency_ms=latency, **{k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")})
        return LLMResult(text, body.get("model", self.s.evon_model), latency,
                         usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    async def health(self) -> bool:
        if self.s.provider_mode == "mock":
            return True
        try:
            r = await self.client.get(f"{self.s.evon_base_url.rstrip('/')}/models",
                                      headers={"Authorization": f"Bearer {self.s.evon_api_key}"}, timeout=2)
            return r.status_code == 200
        except Exception:
            return False


def _mock_answer(messages: list[dict]) -> str:
    """Offline stand-in for Evon: answer from passage [1] in the requested language."""
    from app.pipeline import extractive_answer  # local import avoids a cycle
    ctx = messages[-1]["content"]
    lang = "ta-IN" if "Reply in Tamil" in messages[0]["content"] else "en-IN"
    m = re.search(r"\[1\][^\n]*\n(.+?)(?:\n\[2\] |\n\nCONVERSATION SO FAR|$)", ctx, re.S)
    if not m:
        return "NO_ANSWER"
    return extractive_answer(m.group(1), lang, 300) + " [1]"
