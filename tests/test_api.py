from tests.conftest import make_settings, tone_wav
from fastapi.testclient import TestClient
from app.main import create_app

ADMIN = {"X-Admin-Key": "test-admin"}


def test_health_and_ready(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"]["kb_loaded"]


def test_text_query_tamil_grounded(client):
    r = client.post("/api/v1/query/text", json={"text": "பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்?", "speak": True})
    j = r.json()
    assert r.status_code == 200, j
    assert j["language"] == "ta-IN"
    assert j["sources"] and j["sources"][0]["doc_id"] == "pm-kisan"
    assert not j["escalated"]
    assert j["audio_b64"]  # TTS ran
    assert "[1]" not in j["answer"]  # citations stripped for speech
    assert set(j["timings_ms"]) >= {"retrieve", "llm", "tts", "total"}


def test_out_of_scope_escalates_with_ticket(client):
    j = client.post("/api/v1/query/text", json={"text": "bitcoin price today"}).json()
    assert j["escalated"] and j["ticket"].startswith("TKT-")
    assert j["sources"] == []
    tix = client.get("/api/v1/admin/tickets", headers=ADMIN).json()
    assert any(t["id"] == j["ticket"] for t in tix)


def test_pii_is_redacted_before_storage(client):
    j = client.post("/api/v1/query/text", json={"text": "my aadhaar 2345 6789 0123 and phone 9876543210, PM Kisan status?"}).json()
    assert "2345" not in j["transcript"] and "9876543210" not in j["transcript"]
    assert {"AADHAAR", "PHONE"} <= set(j["pii_redacted"])
    turns = client.get("/api/v1/admin/turns", headers=ADMIN).json()
    assert all("9876543210" not in (t["transcript"] or "") for t in turns)


def test_voice_query_mock_pipeline(client):
    r = client.post("/api/v1/query/voice", files={"audio": ("q.wav", tone_wav(2.5), "audio/wav")},
                    data={"language": "ta-IN"})
    j = r.json()
    assert r.status_code == 200, j
    assert j["transcript"] and j["audio_info"]["duration_s"] > 2
    assert "stt" in j["timings_ms"] and "preprocess" in j["timings_ms"]


def test_voice_query_phone_simulation(client):
    j = client.post("/api/v1/query/voice", files={"audio": ("q.wav", tone_wav(2.0), "audio/wav")},
                    data={"language": "ta-IN", "simulate_phone": "true", "simulate_snr_db": "5"}).json()
    assert j["audio_info"]["duration_s"] > 1.5


def test_too_short_audio_asks_to_repeat(client):
    j = client.post("/api/v1/query/voice", files={"audio": ("q.wav", tone_wav(0.2), "audio/wav")}).json()
    assert j["turn_id"].startswith("canned-no_speech")


def test_garbage_audio_is_400(client):
    r = client.post("/api/v1/query/voice", files={"audio": ("q.wav", b"not audio at all", "audio/wav")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_session_followup_uses_history(client):
    a = client.post("/api/v1/query/text", json={"text": "மகளிர் உரிமைத் தொகை பற்றி சொல்லுங்கள்"}).json()
    b = client.post("/api/v1/query/text", json={"text": "தகுதி என்ன?", "session_id": a["session_id"]}).json()
    assert b["session_id"] == a["session_id"]
    assert b["sources"] and b["sources"][0]["doc_id"] == "kmut"


def test_admin_requires_key(client):
    assert client.get("/api/v1/admin/analytics").status_code == 401
    assert client.get("/api/v1/admin/analytics", headers={"X-Admin-Key": "wrong"}).status_code == 401


def test_analytics_and_feedback(client):
    j = client.post("/api/v1/query/text", json={"text": "crop insurance premium for kharif"}).json()
    assert client.post("/api/v1/feedback", json={"turn_id": j["turn_id"], "rating": 1}).json()["ok"]
    a = client.get("/api/v1/admin/analytics", headers=ADMIN).json()
    assert a["turns"] >= 1 and a["feedback"]["n"] == 1
    assert "credits" in a and a["credits"]["budget"] == 5000


def test_kb_upload_and_retrieve(client):
    doc = "# Summary\nThe Kural test scheme gives 777 rupees to zebra farmers.\n"
    r = client.post("/api/v1/admin/kb/upload", headers=ADMIN, files={"file": ("z.md", doc.encode(), "text/markdown")},
                    data={"title": "Zebra Scheme", "source_url": "https://example.org", "aliases": "zebra"})
    assert r.status_code == 200
    j = client.post("/api/v1/query/text", json={"text": "zebra farmers scheme amount"}).json()
    assert j["sources"][0]["doc_id"] == "zebra-scheme"


def test_metrics_endpoint(client):
    client.get("/healthz")
    body = client.get("/metrics").text
    assert "kural_http_requests_total" in body and "kural_credits_used" in body


def test_rate_limit(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, rate_limit_per_minute=2))) as c:
        codes = [c.post("/api/v1/query/text", json={"text": "PM Kisan"}).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes


def test_credit_budget_blocks_paid_calls(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, credit_budget=0.0))) as c:
        r = c.post("/api/v1/query/voice", files={"audio": ("q.wav", tone_wav(2.0), "audio/wav")})
    assert r.status_code == 402


def test_twilio_flow(client):
    r = client.post("/telephony/twilio/voice", data={"From": "+911234567890"})
    assert "<Gather" in r.text
    r = client.post("/telephony/twilio/language", data={"Digits": "1", "From": "+911234567890"})
    assert "<Play>" in r.text and "<Record" in r.text
    key = r.text.split("/api/v1/audio/")[1].split("<")[0]
    assert client.get(f"/api/v1/audio/{key}").status_code == 200


def test_twilio_rejects_bad_signature(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, twilio_auth_token="secret"))) as c:
        assert c.post("/telephony/twilio/voice", data={"From": "x"}).status_code == 403


def test_validation_error_shape(client):
    r = client.post("/api/v1/query/text", json={"text": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_request_id_header(client):
    r = client.get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_tamil_question_gets_tamil_answer(client):
    j = client.post("/api/v1/query/text", json={"text": "பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்?"}).json()
    from app.lang import detect
    assert detect(j["answer"])["language"] == "ta-IN" and "6,000" in j["answer"]


def test_offtopic_followup_not_rescued_by_history(client):
    a = client.post("/api/v1/query/text", json={"text": "KCC loan ku collateral venuma"}).json()
    b = client.post("/api/v1/query/text", json={"text": "bitcoin price today", "session_id": a["session_id"]}).json()
    assert b["escalated"] and b["sources"] == []


def test_readme_not_indexed(client):
    assert all(d["id"].lower() != "readme" for d in client.get("/api/v1/schemes").json())


def test_unrelated_short_question_does_not_inherit_topic(client):
    a = client.post("/api/v1/query/text", json={"text": "மகளிர் உரிமைத் தொகை யாருக்கு கிடைக்கும்?"}).json()
    b = client.post("/api/v1/query/text", json={"text": "நாளை மழை வருமா?", "session_id": a["session_id"]}).json()
    assert all(src["doc_id"] != "kmut" for src in b["sources"])
