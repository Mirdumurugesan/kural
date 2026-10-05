"""Gnani Timbre v2.5 text-to-speech client (REST /api/v1/tts/inference).

Docs: https://docs.gnani.ai/api/TTS/tts-inference
Responses are cached on disk by content hash -> repeated answers cost zero credits.
Telephony callers get 8 kHz mu-law-friendly WAV; web callers get MP3.
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings
from app.core.http import CircuitBreaker, request_with_retry
from app.core.logging import log

logger = logging.getLogger("kural.tts")

# Preferred voice per language (docs.gnani.ai/api/TTS/available-voices)
VOICE_MAP_DEFAULTS = {
    "ta-IN": "Trisha", "en-IN": "Kaveri", "hi-IN": "Nalini", "hi-en": "Poorvi",
    "te-IN": "Lavanya", "kn-IN": "Saanvi", "ml-IN": "Reshma", "mr-IN": "Ishaan",
    "bn-IN": "Kirra", "gu-IN": "Falak", "pa-IN": "Mehuli",
}

PROFILES = {
    # web playback: 16 kHz wav. (Timbre's mp3 container returned HTTP 500 on most requests in live testing,
    # Oct 2026, while wav succeeded 9/9 — see docs/BENCHMARKS.md. Switch back to mp3 once that's fixed.)
    "web": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
    # lossless 16 kHz wav (benchmarks; decodes without ffmpeg)
    "wav16": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
    # phone line: 8 kHz 16-bit wav (Twilio <Play> friendly)
    "phone": {"sample_rate": 8000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
}


@dataclass
class TTSResult:
    audio: bytes
    content_type: str
    voice: str
    cached: bool
    latency_ms: int
    chars: int


class TimbreTTS:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.s = settings
        self.client = client
        self.breaker = CircuitBreaker("gnani-timbre")
        self.cache_dir: Path = settings.tts_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.voices = dict(VOICE_MAP_DEFAULTS)
        self.voices.update({"ta-IN": settings.tts_voice_ta, "en-IN": settings.tts_voice_en,
                            "hi-IN": settings.tts_voice_hi, "hi-en": settings.tts_voice_hien})

    def voice_for(self, language: str) -> str:
        return self.voices.get(language, self.voices["en-IN"])

    async def synthesize(self, text: str, language: str, profile: str = "web") -> TTSResult:
        t0 = time.perf_counter()
        cfg = PROFILES[profile]
        voice = self.voice_for(language)
        ctype = "audio/mpeg" if cfg["container"] == "mp3" else "audio/wav"
        key = hashlib.sha256(f"{self.s.tts_model}|{voice}|{language}|{self.s.tts_speed}|{profile}|{text}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.{cfg['container']}"
        if path.exists():
            return TTSResult(path.read_bytes(), ctype, voice, True, int((time.perf_counter() - t0) * 1000), len(text))

        if self.s.provider_mode == "mock":
            audio, ctype = _mock_wav(text, cfg["sample_rate"]), "audio/wav"
        else:
            resp = await request_with_retry(
                self.client, "POST", f"{self.s.gnani_base_url}/api/v1/tts/inference",
                breaker=self.breaker, max_retries=self.s.http_max_retries,
                headers={"X-API-Key-ID": self.s.gnani_api_key, "Content-Type": "application/json"},
                json={"text": text, "voice": voice, "model": self.s.tts_model, "language": language,
                      "speed": self.s.tts_speed, "audio_config": cfg},
            )
            audio = resp.content
        path.write_bytes(audio)
        latency = int((time.perf_counter() - t0) * 1000)
        log(logger, logging.INFO, "tts_done", voice=voice, language=language, chars=len(text), latency_ms=latency)
        return TTSResult(audio, ctype, voice, False, latency, len(text))


def _mock_wav(text: str, sr: int) -> bytes:
    """Short soft tone so the offline demo still 'speaks'."""
    dur = min(2.0, 0.3 + len(text) / 200)
    n = int(sr * dur)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / sr))) for i in range(n)))
    return buf.getvalue()
