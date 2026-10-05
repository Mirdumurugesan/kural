"""Live-mode clients against mocked HTTP: checks we speak Gnani's documented wire format."""
import json

import httpx
import pytest
import respx

from app.core.errors import UpstreamError
from app.gnani.evon import EvonLLM
from app.gnani.stt import PrismaSTT
from app.gnani.tts import TimbreTTS
from tests.conftest import make_settings, tone_wav

BASE = "https://api.vachana.ai"


@pytest.fixture
def live(tmp_path):
    return make_settings(tmp_path, provider_mode="live", http_max_retries=2)


@respx.mock
async def test_prisma_request_format(live):
    route = respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(
        200, json={"success": True, "request_id": "req_1", "transcript": "வணக்கம்"}))
    async with httpx.AsyncClient() as c:
        r = await PrismaSTT(live, c).transcribe_segments([tone_wav(1)], "ta-IN", ["கிசான்", "PMKisan", "bad-word", "x1"])
    assert r.transcript == "வணக்கம்" and r.request_ids == ["req_1"]
    req = route.calls[0].request
    assert req.headers["X-API-Key-ID"] == "test-key"
    body = req.content.decode("utf-8", errors="ignore")
    assert 'name="language_code"' in body and "ta-IN" in body
    assert 'name="audio_file"' in body and 'name="format"' in body
    assert "கிசான்" in body and "bad-word" not in body  # bias list validated


@respx.mock
async def test_prisma_retries_on_503_then_succeeds(live, monkeypatch):
    monkeypatch.setattr("app.core.http._backoff", lambda a: 0)
    route = respx.post(f"{BASE}/stt/v3").mock(side_effect=[
        httpx.Response(503), httpx.Response(200, json={"transcript": "ok", "request_id": "r"})])
    async with httpx.AsyncClient() as c:
        r = await PrismaSTT(live, c).transcribe_segments([tone_wav(1)], "ta-IN")
    assert r.transcript == "ok" and route.call_count == 2


@respx.mock
async def test_prisma_400_is_not_retried(live):
    route = respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(
        400, json={"success": False, "error": {"type": "INVALID_REQUEST_ERROR", "message": "too long"}}))
    async with httpx.AsyncClient() as c:
        with pytest.raises(UpstreamError):
            await PrismaSTT(live, c).transcribe_segments([tone_wav(1)], "ta-IN")
    assert route.call_count == 1


@respx.mock
async def test_timbre_request_and_cache(live):
    route = respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"WAVDATA"))
    async with httpx.AsyncClient() as c:
        tts = TimbreTTS(live, c)
        a = await tts.synthesize("வணக்கம்", "ta-IN", "web")
        b = await tts.synthesize("வணக்கம்", "ta-IN", "web")
    assert a.audio == b"WAVDATA" and not a.cached and b.cached
    assert route.call_count == 1  # second call served from cache: zero credits
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "timbre-v2.5" and sent["voice"] == "Trisha" and sent["language"] == "ta-IN"
    assert sent["audio_config"]["container"] == "wav"


@respx.mock
async def test_timbre_phone_profile_is_8khz_wav(live):
    route = respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"WAV"))
    async with httpx.AsyncClient() as c:
        r = await TimbreTTS(live, c).synthesize("hello", "en-IN", "phone")
    sent = json.loads(route.calls[0].request.content)
    assert sent["audio_config"]["sample_rate"] == 8000 and r.content_type == "audio/wav" and sent["voice"] == "Kaveri"


@respx.mock
async def test_evon_openai_compatible_and_strips_think(live):
    respx.post("http://localhost:8000/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": "gnani/gnani-evon-v3.3-30B-A3B",
        "choices": [{"message": {"content": "<think>reasoning</think>ஆண்டுக்கு 6,000 ரூபாய். [1]"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20}}))
    async with httpx.AsyncClient() as c:
        r = await EvonLLM(live, c).chat([{"role": "user", "content": "q"}])
    assert r.text == "ஆண்டுக்கு 6,000 ரூபாய். [1]" and r.prompt_tokens == 100


@respx.mock
async def test_pipeline_falls_back_when_evon_down(tmp_path, monkeypatch):
    """Evon unreachable -> helpline still answers from the KB (extractive) instead of failing."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setattr("app.core.http._backoff", lambda a: 0)
    respx.post("http://localhost:8000/v1/chat/completions").mock(side_effect=httpx.ConnectError("down"))
    respx.get("http://localhost:8000/v1/models").mock(side_effect=httpx.ConnectError("down"))
    s = make_settings(tmp_path, provider_mode="live")
    with TestClient(create_app(s)) as c:
        j = c.post("/api/v1/query/text", json={"text": "PM Kisan எவ்வளவு பணம்?"}).json()
        ready = c.get("/readyz").json()
    assert j["fallback"] is True and not j["escalated"] and "6,000" in j["answer"]
    assert ready["ready"] and ready["checks"]["evon_reachable"] is False


@respx.mock
async def test_fallback_escalates_weak_matches(tmp_path, monkeypatch):
    """Evon down + weak retrieval (off-topic question) -> escalate, never read a random passage."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setattr("app.core.http._backoff", lambda a: 0)
    respx.post("http://localhost:8000/v1/chat/completions").mock(side_effect=httpx.ConnectError("down"))
    with TestClient(create_app(make_settings(tmp_path, provider_mode="live"))) as c:
        j = c.post("/api/v1/query/text", json={"text": "நாளை மழை வருமா"}).json()
    assert j["escalated"] and j["ticket"]
