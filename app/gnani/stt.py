"""Gnani Prisma v2.5 speech-to-text client (REST /stt/v3).

Docs: https://docs.gnani.ai/api/STT/speech-to-text
- multipart: audio_file, language_code, format, bias_list, bias_score
- auth header: X-API-Key-ID
- clips should be <= 30s (hard max 60s) -> longer audio is segmented upstream
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.core.http import CircuitBreaker, request_with_retry
from app.core.logging import log
from app.rag.store import BIAS_WORD_RE

logger = logging.getLogger("kural.stt")

SUPPORTED_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}


@dataclass
class STTResult:
    transcript: str
    language: str
    request_ids: list[str]
    latency_ms: int
    segments: int


class PrismaSTT:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.s = settings
        self.client = client
        self.breaker = CircuitBreaker("gnani-prisma")

    async def transcribe_segments(
        self, segments: list[bytes], language: str, bias_words: list[str] | None = None
    ) -> STTResult:
        if language not in SUPPORTED_LANGS:
            language = self.s.stt_default_language
        t0 = time.perf_counter()
        # segments are independent -> transcribe concurrently, keep order
        results = await asyncio.gather(
            *(self._one(seg, language, bias_words, i) for i, seg in enumerate(segments))
        )
        text = " ".join(r[0] for r in results if r[0]).strip()
        latency = int((time.perf_counter() - t0) * 1000)
        log(logger, logging.INFO, "stt_done", language=language, segments=len(segments), latency_ms=latency)
        return STTResult(text, language, [r[1] for r in results], latency, len(segments))

    async def _one(self, wav: bytes, language: str, bias_words: list[str] | None, idx: int) -> tuple[str, str]:
        if self.s.provider_mode == "mock":
            return (_mock_transcript(language), f"mock-{idx}")
        data = {"language_code": language, "format": self.s.stt_format}
        clean_bias = [w for w in (bias_words or []) if BIAS_WORD_RE.fullmatch(w)][:100]
        if clean_bias and self.s.stt_bias_score > 0:
            # boost scheme names (docs recommend verbatim for best boosting; we keep ITN
            # by default because spoken ₹ amounts matter more for this use case)
            data.update(bias_list=json.dumps(clean_bias, ensure_ascii=False),
                        bias_score=str(self.s.stt_bias_score))
        resp = await request_with_retry(
            self.client, "POST", f"{self.s.gnani_base_url}/stt/v3",
            breaker=self.breaker, max_retries=self.s.http_max_retries,
            headers={"X-API-Key-ID": self.s.gnani_api_key},
            data=data,
            files={"audio_file": (f"seg{idx}.wav", wav, "audio/wav")},
        )
        body = resp.json()
        return (body.get("transcript", "") or "", body.get("request_id", ""))


def _mock_transcript(language: str) -> str:
    return {
        "ta-IN": "பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்",
        "en-IN": "how much money do I get under PM Kisan scheme",
        "hi-IN": "पीएम किसान योजना में कितना पैसा मिलता है",
    }.get(language, "PM Kisan scheme details")
