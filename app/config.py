"""Central configuration. Every value can be overridden with an environment variable
(prefix-free, case-insensitive) or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- runtime ----
    app_name: str = "Kural"
    environment: str = "dev"  # dev | staging | prod
    log_level: str = "INFO"
    # mock = no network calls to Gnani (tests / offline demo); live = real APIs
    provider_mode: str = "live"

    # ---- Gnani speech APIs (Prisma STT + Timbre TTS) ----
    gnani_api_key: str = ""
    gnani_base_url: str = "https://api.vachana.ai"
    stt_default_language: str = "ta-IN"
    stt_format: str = "transcribe"  # ITN on: numbers, ₹, dates come back as digits
    stt_bias_score: float = 1.0
    stt_segment_seconds: int = 28  # REST ideal is <=30s; longer audio is split
    tts_model: str = "timbre-v2.5"
    tts_voice_ta: str = "Trisha"
    tts_voice_en: str = "Kaveri"
    tts_voice_hi: str = "Nalini"
    tts_voice_hien: str = "Poorvi"
    tts_speed: float = 1.0
    http_timeout_s: float = 30.0
    http_max_retries: int = 3

    # ---- Gnani Evon v3.3 (OpenAI-compatible, self-hosted via vLLM or HF endpoint) ----
    evon_base_url: str = "http://localhost:8000/v1"
    evon_api_key: str = "EMPTY"
    evon_model: str = "gnani/gnani-evon-v3.3-30B-A3B"
    evon_max_tokens: int = 400
    evon_temperature: float = 0.2
    # Evon reasons in a <think> block by default; off = much lower latency for voice
    evon_enable_thinking: bool = False

    # ---- RAG ----
    kb_dir: Path = ROOT / "kb"
    rag_top_k: int = 4
    rag_min_score: float = 0.10
    # without Evon's NO_ANSWER judgement, only read out passages we're confident about
    rag_fallback_min_score: float = 0.15

    # ---- storage ----
    db_path: Path = ROOT / "data" / "kural.db"
    tts_cache_dir: Path = ROOT / "data" / "tts_cache"

    # ---- security / limits ----
    admin_api_key: str = "change-me"
    cors_origins: str = "*"
    rate_limit_per_minute: int = 30
    max_upload_mb: int = 10
    max_audio_seconds: int = 120
    redact_pii: bool = True

    # ---- credit guard (programme gives 5,000 credits) ----
    credit_budget: float = 5000.0
    # from app.gnani.ai/voice/pricing (Oct 2026): STT 27 credits/hour, TTS 27 credits per 10k chars
    credit_cost_stt_per_min: float = 0.45
    credit_cost_tts_per_1k_chars: float = 2.7
    credit_alert_ratio: float = 0.8

    # ---- telephony ----
    public_base_url: str = "http://localhost:8080"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""  # set to enable webhook signature validation + recording download


@lru_cache
def get_settings() -> Settings:
    return Settings()
