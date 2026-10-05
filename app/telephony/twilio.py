"""Phone channel via Twilio Programmable Voice (works with an Indian number or a trial number).

Call flow (pure TwiML, no Twilio SDK needed):
  /voice     -> language menu: 1 Tamil, 2 English, 3 Hindi (default Tamil after 4s)
  /language  -> greeting + <Record> (beep, max 30s, trim silence)
  /recording -> download 8 kHz recording -> Kural pipeline (phone profile) -> <Play> answer -> record again
Point the Twilio number's "A call comes in" webhook to  {PUBLIC_BASE_URL}/telephony/twilio/voice
Other telephony providers (Exotel, Plivo, SIP via LiveKit) plug in the same way: fetch audio, call
Pipeline.handle_audio(..., tts_profile="phone"), return the provider's play-audio verb.
"""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.logging import log
from app.core.security import hash_caller, twilio_signature_valid
from app.prompts import msg

router = APIRouter(prefix="/telephony/twilio", tags=["telephony"])
logger = logging.getLogger("kural.twilio")
LANG_BY_DIGIT = {"1": "ta-IN", "2": "en-IN", "3": "hi-IN"}
MENU = ("தமிழுக்கு ஒன்றை அழுத்தவும். For English press 2. हिंदी के लिए 3 दबाएं।")


def twiml(body: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


async def _verify(request: Request) -> dict:
    form = dict(await request.form())
    s = request.app.state.settings
    if s.twilio_auth_token:
        url = s.public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not twilio_signature_valid(s.twilio_auth_token, url, form, request.headers.get("X-Twilio-Signature", "")):
            log(logger, logging.WARNING, "twilio_bad_signature")
            raise PermissionError("bad signature")
    return form


def _record(base: str, lang: str, sid: str) -> str:
    return (f'<Record action="{base}/telephony/twilio/recording?lang={lang}&amp;sid={sid}" method="POST" '
            f'maxLength="30" timeout="3" playBeep="true" trim="trim-silence"/>')


@router.post("/voice")
async def voice(request: Request):
    try:
        await _verify(request)
    except PermissionError:
        return Response(status_code=403)
    base = request.app.state.settings.public_base_url.rstrip("/")
    return twiml(f'<Gather numDigits="1" timeout="4" action="{base}/telephony/twilio/language" method="POST">'
                 f'<Say language="en-IN">{escape(MENU)}</Say></Gather>'
                 f'<Redirect method="POST">{base}/telephony/twilio/language?Digits=1</Redirect>')


@router.post("/language")
async def language(request: Request):
    try:
        form = await _verify(request)
    except PermissionError:
        return Response(status_code=403)
    s, pipe = request.app.state.settings, request.app.state.pipeline
    digit = form.get("Digits") or request.query_params.get("Digits", "1")
    lang = LANG_BY_DIGIT.get(digit, "ta-IN")
    caller = hash_caller(form.get("From", ""), s.admin_api_key)
    sid = pipe.db.ensure_session(None, "phone", lang, caller)
    base = s.public_base_url.rstrip("/")
    key = await pipe.speak_text(msg("greeting", lang), lang, "phone")
    return twiml(f"<Play>{base}/api/v1/audio/{key}</Play>{_record(base, lang, sid)}")


@router.post("/recording")
async def recording(request: Request):
    try:
        form = await _verify(request)
    except PermissionError:
        return Response(status_code=403)
    s, pipe = request.app.state.settings, request.app.state.pipeline
    lang = request.query_params.get("lang", "ta-IN")
    sid = request.query_params.get("sid")
    base = s.public_base_url.rstrip("/")
    url = form.get("RecordingUrl")
    if not url:
        return twiml(f"<Say>{escape(msg('goodbye', 'en-IN'))}</Say><Hangup/>")
    try:
        auth = (s.twilio_account_sid, s.twilio_auth_token) if s.twilio_account_sid else None
        async with httpx.AsyncClient(timeout=15) as c:
            audio = (await c.get(url + ".wav", auth=auth)).content
        r = await pipe.handle_audio(audio, language=lang, session_id=sid, channel="phone", tts_profile="phone")
        play = f"<Play>{base}/api/v1/audio/{r.turn_id}</Play>" if r.audio_b64 else f"<Say>{escape(r.answer)}</Say>"
    except Exception as exc:  # never drop the caller: apologise and keep the line open
        log(logger, logging.ERROR, "phone_turn_failed", error=repr(exc))
        play = await _prompt(pipe, base, "error", lang)
    nxt = await _prompt(pipe, base, "anything_else", lang)
    return twiml(f"{play}{nxt}{_record(base, lang, sid or '')}")


async def _prompt(pipe, base: str, key: str, lang: str) -> str:
    """Play a pre-rendered Timbre prompt; if TTS itself is down, fall back to Twilio <Say>."""
    try:
        k = await pipe.speak_text(msg(key, lang), lang, "phone")
        return f"<Play>{base}/api/v1/audio/{k}</Play>"
    except Exception:
        return f'<Say language="en-IN">{escape(msg(key, "en-IN"))}</Say>'
