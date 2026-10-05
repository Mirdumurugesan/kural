"""Public + admin HTTP API (OpenAPI docs at /docs)."""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.core.errors import BadRequest
from app.core.security import check_admin

api = APIRouter(prefix="/api/v1", tags=["helpline"])
admin = APIRouter(prefix="/api/v1/admin", tags=["admin"])
ops = APIRouter(tags=["ops"])


def _pipe(req: Request):
    return req.app.state.pipeline


def _limit(req: Request) -> None:
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "?").split(",")[0].strip()
    req.app.state.limiter.check(ip)


# ---------------------------------------------------------------- citizen endpoints
class TextQuery(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, examples=["PM Kisan la evvalavu panam kedaikum?"])
    language: str = Field("auto", examples=["auto", "ta-IN", "en-IN"])
    session_id: str | None = None
    speak: bool = False


@api.post("/query/text", summary="Ask in text (Tamil / Tanglish / English) and get a grounded answer")
async def query_text(body: TextQuery, request: Request):
    _limit(request)
    r = await _pipe(request).handle_text(body.text, language=body.language, session_id=body.session_id,
                                         channel="web-text", speak=body.speak)
    return r.public()


@api.post("/query/voice", summary="Ask by voice: audio in, spoken answer out")
async def query_voice(
    request: Request,
    audio: UploadFile = File(..., description="wav/mp3/ogg/webm/m4a, up to 2 min"),
    language: str = Form("ta-IN"),
    session_id: str | None = Form(None),
    speak: bool = Form(True),
    simulate_phone: bool = Form(False, description="Degrade to noisy 8 kHz phone audio first (demo)"),
    simulate_snr_db: float = Form(10.0),
):
    _limit(request)
    s = request.app.state.settings
    raw = await audio.read()
    if len(raw) > s.max_upload_mb * 1024 * 1024:
        raise BadRequest(f"File larger than {s.max_upload_mb} MB")
    r = await _pipe(request).handle_audio(raw, language=language, session_id=session_id, channel="web-voice",
                                          speak=speak, simulate_phone_snr=simulate_snr_db if simulate_phone else None)
    return r.public()


class Feedback(BaseModel):
    turn_id: str
    rating: int = Field(..., ge=-1, le=1, description="1 helpful, -1 not helpful")
    comment: str = Field("", max_length=500)


@api.post("/feedback")
async def feedback(body: Feedback, request: Request):
    _limit(request)
    _pipe(request).db.add_feedback(body.turn_id, body.rating, body.comment)
    return {"ok": True}


@api.get("/audio/{key}", summary="Fetch synthesized reply audio (used by telephony <Play>)")
async def get_audio(key: str, request: Request):
    item = _pipe(request).audio_store.get(key)
    if not item:
        return Response(status_code=404)
    audio, ctype = item
    return Response(audio, media_type=ctype, headers={"Cache-Control": "private, max-age=3600"})


@api.get("/schemes", summary="List knowledge-base documents")
async def schemes(request: Request):
    idx = _pipe(request).index
    return [{"id": k, "title": v.get("title"), "category": v.get("category"), "source_url": v.get("source_url"),
             "languages": v.get("languages")} for k, v in idx.docs.items()]


# ---------------------------------------------------------------- admin (X-Admin-Key)
def _admin(request: Request, key: str | None) -> None:
    check_admin(key, request.app.state.settings.admin_api_key)


@admin.get("/analytics")
async def analytics(request: Request, days: int = 7, x_admin_key: str | None = Header(None)):
    _admin(request, x_admin_key)
    p = _pipe(request)
    return {**p.db.analytics(days * 86400), "credits": p.credits.status(), "kb_chunks": len(p.index.chunks)}


@admin.get("/turns")
async def turns(request: Request, limit: int = 50, escalated_only: bool = False, x_admin_key: str | None = Header(None)):
    _admin(request, x_admin_key)
    where = "WHERE escalated=1" if escalated_only else ""
    return _pipe(request).db.q(f"SELECT * FROM turns {where} ORDER BY created_at DESC LIMIT ?", (min(limit, 500),))


@admin.get("/tickets")
async def tickets(request: Request, status: str = "open", x_admin_key: str | None = Header(None)):
    _admin(request, x_admin_key)
    return _pipe(request).db.q(
        "SELECT t.*, u.transcript, u.language FROM tickets t LEFT JOIN turns u ON u.id=t.turn_id "
        "WHERE t.status=? ORDER BY t.created_at DESC LIMIT 200", (status,))


@admin.post("/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, request: Request, x_admin_key: str | None = Header(None)):
    _admin(request, x_admin_key)
    _pipe(request).db._exec("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
    return {"ok": True}


@admin.post("/kb/upload", summary="Add/replace a knowledge-base document (.md or .txt) and re-index")
async def kb_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    source_url: str = Form(""),
    category: str = Form("general"),
    aliases: str = Form(""),
    x_admin_key: str | None = Header(None),
):
    _admin(request, x_admin_key)
    raw = (await file.read()).decode("utf-8", errors="ignore")
    if not raw.strip():
        raise BadRequest("Empty document")
    if len(raw) > 500_000:
        raise BadRequest("Document too large (max 500 KB)")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or f"doc-{int(time.time())}"
    s = request.app.state.settings
    path: Path = s.kb_dir / "uploaded" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = (f"---\ntitle: {title}\nsource_url: {source_url}\ncategory: {category}\n"
             f"aliases: {aliases}\nlanguages: auto\n---\n")
    body = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.S)
    path.write_text(front + body, encoding="utf-8")
    n = _pipe(request).index.load_dir(s.kb_dir)
    return {"ok": True, "doc_id": slug, "chunks_total": n}


@admin.post("/kb/reindex")
async def kb_reindex(request: Request, x_admin_key: str | None = Header(None)):
    _admin(request, x_admin_key)
    n = _pipe(request).index.load_dir(request.app.state.settings.kb_dir)
    return {"ok": True, "chunks_total": n}


# ---------------------------------------------------------------- ops
@ops.get("/healthz", summary="Liveness")
async def healthz():
    return {"status": "ok"}


@ops.get("/readyz", summary="Readiness: KB loaded, keys configured, Evon reachable")
async def readyz(request: Request):
    p, s = _pipe(request), request.app.state.settings
    checks = {
        "kb_loaded": len(p.index.chunks) > 0,
        "gnani_key_configured": bool(s.gnani_api_key) or s.provider_mode == "mock",
        "evon_reachable": await p.llm.health(),
        "credits_remaining": p.credits.status()["remaining"] > 0,
    }
    # Evon down is degraded (extractive fallback), not unready
    ready = checks["kb_loaded"] and checks["gnani_key_configured"] and checks["credits_remaining"]
    return Response(content=__import__("json").dumps({"ready": ready, "checks": checks}),
                    media_type="application/json", status_code=200 if ready else 503)


@ops.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
async def metrics(request: Request):
    p = _pipe(request)
    a = p.db.analytics(86400)
    m = request.app.state.metrics
    lines = [
        "# TYPE kural_http_requests_total counter",
        *[f'kural_http_requests_total{{path="{k[0]}",status="{k[1]}"}} {v}' for k, v in m["requests"].items()],
        "# TYPE kural_turns_24h gauge", f"kural_turns_24h {a['turns']}",
        "# TYPE kural_latency_avg_ms gauge", f"kural_latency_avg_ms {a['avg_latency_ms'] or 0}",
        "# TYPE kural_latency_p95_ms gauge", f"kural_latency_p95_ms {a['p95_latency_ms'] or 0}",
        "# TYPE kural_escalations_24h gauge", f"kural_escalations_24h {a['escalations']}",
        "# TYPE kural_llm_fallbacks_24h gauge", f"kural_llm_fallbacks_24h {a['llm_fallbacks']}",
        "# TYPE kural_credits_used gauge", f"kural_credits_used {p.credits.status()['used']}",
    ]
    return "\n".join(lines) + "\n"
