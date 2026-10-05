import io
import shutil
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app


def make_settings(tmp_path, **kw) -> Settings:
    kb = tmp_path / "kb"
    if not kb.exists():  # tests never write into the real knowledge base
        shutil.copytree(ROOT / "kb", kb)
    base = dict(provider_mode="mock", db_path=tmp_path / "t.db", tts_cache_dir=tmp_path / "tts",
                kb_dir=kb, admin_api_key="test-admin", rate_limit_per_minute=1000,
                gnani_api_key="test-key", log_level="WARNING")
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def tone_wav(seconds=2.0, sr=16000, freq=220.0, amp=8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(amp * math.sin(2 * math.pi * freq * i / sr) * (0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / sr))))
            for i in range(int(sr * seconds)))
        w.writeframes(frames)
    return buf.getvalue()
