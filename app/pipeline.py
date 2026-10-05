"""The voice turn: audio -> clean -> Prisma STT -> retrieve -> Evon -> guardrails -> Timbre TTS."""
from __future__ import annotations

import base64
import logging
import re
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

import httpx

from app import audio as A
from app.config import Settings
from app.core.db import DB
from app.core.errors import BadRequest, KuralError, UpstreamError
from app.core.logging import log
from app.core.security import CreditGuard, redact
from app.gnani.evon import EvonLLM
from app.gnani.stt import PrismaSTT
from app.gnani.tts import TimbreTTS
from app.lang import LANG_NAMES, detect
from app.prompts import MIX_RULES, SYSTEM_PROMPT, USER_TEMPLATE, msg
from app.rag.store import Hit, HybridIndex

logger = logging.getLogger("kural.pipeline")
CITE_RE = re.compile(r"\s*\[(\d+)\]")
FOLLOWUP_RE = re.compile(
    r"(தகுதி|விண்ணப்ப|ஆவண|எப்படி|எப்டி|எங்கே|எங்க|எவ்வளவு|எவ்ளோ|எப்போ|எப்பொழுது|கடைசி தேதி|உதவி எண்|யாருக்கு|"
    r"அதுக்கு|அதற்கு|இதுக்கு|இதற்கு|அந்த திட்ட|"
    r"\b(eligib\w*|apply|application|documents?|how|when|where|how much|helpline|deadline|status|amount|"
    r"epdi|eppadi|evlo|evvalavu|yaarukku|enga|adhukku|idhukku)\b)", re.I)
MD_RE = re.compile(r"[*_#`>]+")


@dataclass
class TurnResult:
    turn_id: str
    session_id: str
    language: str
    code_mixed: bool
    transcript: str
    answer: str
    sources: list[dict]
    confidence: float
    escalated: bool
    ticket: str | None
    fallback: bool
    audio_info: dict | None
    timings_ms: dict = field(default_factory=dict)
    audio_b64: str | None = None
    audio_content_type: str | None = None
    pii_redacted: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return asdict(self)


def extractive_answer(body: str, lang: str, max_chars: int = 240) -> str:
    """First sentences of the passage written in the caller's script (KB paragraphs are bilingual)."""
    lines = [l for l in body.splitlines() if not l.lstrip().startswith("#")]  # drop headings, keep their paragraphs
    paras = [p.strip() for p in "\n".join(lines).split("\n\n") if p.strip()]
    same = [p for p in paras if detect(p)["language"] == lang] or paras
    text = " ".join(same)
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    out = ""
    for sent in sentences:
        if out and len(out) + len(sent) > max_chars:
            break
        out += sent + " "
    return out.strip()[:max_chars]


class AudioStore:
    """Small LRU so telephony can fetch the reply by URL (<Play>)."""

    def __init__(self, cap: int = 500):
        self.cap, self.d = cap, OrderedDict()

    def put(self, key: str, audio: bytes, ctype: str) -> None:
        self.d[key] = (audio, ctype)
        self.d.move_to_end(key)
        while len(self.d) > self.cap:
            self.d.popitem(last=False)

    def get(self, key: str):
        return self.d.get(key)


class Pipeline:
    def __init__(self, settings: Settings, db: DB, index: HybridIndex, client: httpx.AsyncClient):
        self.s, self.db, self.index = settings, db, index
        self.stt = PrismaSTT(settings, client)
        self.tts = TimbreTTS(settings, client)
        self.llm = EvonLLM(settings, client)
        self.credits = CreditGuard(db, settings.credit_budget, settings.credit_cost_stt_per_min,
                                   settings.credit_cost_tts_per_1k_chars, settings.credit_alert_ratio)
        self.audio_store = AudioStore()

    # ------------------------------------------------------------------ audio entry
    async def handle_audio(self, raw: bytes, *, language: str, session_id: str | None, channel: str,
                           speak: bool = True, tts_profile: str = "web", caller_hash: str = "",
                           simulate_phone_snr: float | None = None) -> TurnResult:
        t0 = time.perf_counter()
        stt_lang = self.s.stt_default_language if language in ("auto", "", None) else language
        if simulate_phone_snr is not None:  # demo: degrade to a noisy 8 kHz phone call first
            raw = A.to_wav(A.simulate_phone_line(await A.normalize(raw, denoise=False), simulate_phone_snr))
        pcm = await A.normalize(raw, denoise=True)
        info = A.analyze(pcm)
        if info.duration_s > self.s.max_audio_seconds:
            raise BadRequest(f"Audio longer than {self.s.max_audio_seconds}s")
        prep_ms = int((time.perf_counter() - t0) * 1000)
        if info.duration_s < 0.4:
            return await self._canned("no_speech", stt_lang, session_id, channel, info, speak, tts_profile, caller_hash)

        self.credits.ensure_available()
        segments = [A.to_wav(s) for s in A.segment(pcm, self.s.stt_segment_seconds)]
        stt = await self.stt.transcribe_segments(segments, stt_lang, self.index.vocabulary_for_bias())
        self.credits.record_stt(info.duration_s)
        if not stt.transcript.strip():
            return await self._canned("no_speech", stt_lang, session_id, channel, info, speak, tts_profile, caller_hash)

        return await self.handle_text(
            stt.transcript, language=stt_lang, session_id=session_id, channel=channel, speak=speak,
            tts_profile=tts_profile, audio_info=info, timings={"preprocess": prep_ms, "stt": stt.latency_ms},
            t0=t0, caller_hash=caller_hash,
        )

    # ------------------------------------------------------------------ text entry
    async def handle_text(self, text: str, *, language: str = "auto", session_id: str | None = None,
                          channel: str = "web-text", speak: bool = False, tts_profile: str = "web",
                          audio_info: A.AudioInfo | None = None, timings: dict | None = None,
                          t0: float | None = None, caller_hash: str = "") -> TurnResult:
        t0 = t0 or time.perf_counter()
        timings = dict(timings or {})
        text = text.strip()[:2000]
        if not text:
            raise BadRequest("Empty question")
        clean_text, pii = redact(text) if self.s.redact_pii else (text, [])
        det = detect(clean_text)
        # explicit choice wins for plain English text; otherwise follow the script the caller used
        lang = language if language not in ("auto", "", None) and det["language"] == "en-IN" and not det["code_mixed"] else det["language"]
        sid = self.db.ensure_session(session_id, channel, lang, caller_hash)

        # ---- retrieval (with short conversational memory for follow-ups) ----
        t = time.perf_counter()
        history = self.db.history(sid, limit=3)
        hits = self.index.search(clean_text, k=self.s.rag_top_k, min_score=self.s.rag_min_score)
        if history and len(clean_text) <= 40 and FOLLOWUP_RE.search(clean_text):
            # short follow-up about the same scheme ("தகுதி என்ன?", "how to apply?") -> resolve it against
            # the previous question. Questions without a follow-up cue (e.g. "நாளை மழை வருமா?") stand alone.
            hits = self.index.search(f"{history[-1]['transcript']} {clean_text}", k=self.s.rag_top_k,
                                     min_score=self.s.rag_min_score) or hits
        timings["retrieve"] = int((time.perf_counter() - t) * 1000)
        confidence = round(hits[0].score, 3) if hits else 0.0

        # ---- generation ----
        answer, fallback, model, escalated = "", False, "", False
        if hits:
            t = time.perf_counter()
            try:
                res = await self.llm.chat(self._messages(clean_text, hits, history, lang, det["code_mixed"]))
                answer, model = res.text, res.model
            except UpstreamError as exc:
                log(logger, logging.WARNING, "llm_fallback", error=exc.message)
                fallback, model = True, "extractive-fallback"
                answer = self._extractive(hits, lang) if confidence >= self.s.rag_fallback_min_score else "NO_ANSWER"
            timings["llm"] = int((time.perf_counter() - t) * 1000)
        if not hits or "NO_ANSWER" in answer or not answer.strip():
            escalated = True

        used = sorted({int(n) for n in CITE_RE.findall(answer) if 0 < int(n) <= len(hits)}) or ([1] if hits and not escalated else [])
        sources = [{"n": i, "doc_id": hits[i - 1].chunk.doc_id, "title": hits[i - 1].chunk.title,
                    "url": hits[i - 1].chunk.source_url, "score": round(hits[i - 1].score, 3)} for i in used]
        spoken = self._speakable(answer)

        ticket = None
        turn_id = self.db.add_turn(
            session_id=sid, channel=channel, language=lang, transcript=clean_text, answer=spoken,
            sources=sources, confidence=confidence, escalated=int(escalated),
            audio_seconds=audio_info.duration_s if audio_info else None,
            snr_db=audio_info.snr_db if audio_info else None, noisy=int(audio_info.noisy) if audio_info else 0,
            stt_ms=timings.get("stt"), rag_ms=timings.get("retrieve"), llm_ms=timings.get("llm"),
            llm_model=model, fallback=int(fallback),
        )
        if escalated:
            ticket = self.db.add_ticket(turn_id, sid, "no_grounded_answer")
            spoken = msg("escalate", lang, ticket=" ".join(ticket[4:]))  # spell ticket out slowly
            sources = []
            self.db._exec("UPDATE turns SET answer=? WHERE id=?", (spoken, turn_id))

        result = TurnResult(turn_id, sid, lang, det["code_mixed"], clean_text, spoken, sources, confidence,
                            escalated, ticket, fallback, asdict(audio_info) if audio_info else None, timings,
                            pii_redacted=pii)
        if speak:
            await self._speak(result, tts_profile)
        result.timings_ms["total"] = int((time.perf_counter() - t0) * 1000)
        self.db._exec("UPDATE turns SET tts_ms=?, total_ms=? WHERE id=?",
                      (result.timings_ms.get("tts"), result.timings_ms["total"], turn_id))
        log(logger, logging.INFO, "turn_done", turn_id=turn_id, lang=lang, escalated=escalated,
            fallback=fallback, confidence=confidence, **{f"{k}_ms": v for k, v in result.timings_ms.items()})
        return result

    # ------------------------------------------------------------------ helpers
    def _messages(self, q: str, hits: list[Hit], history: list[dict], lang: str, mixed: bool) -> list[dict]:
        ctx = "\n".join(f"[{i}] {h.chunk.title} ({h.chunk.source_url})\n{h.chunk.body}" for i, h in enumerate(hits, 1))
        hist = "\n".join(f"Caller: {h['transcript']}\nKural: {h['answer']}" for h in history) or "(none)"
        return [
            {"role": "system", "content": SYSTEM_PROMPT.format(lang_name=LANG_NAMES.get(lang, "English"), mix_rule=MIX_RULES[mixed])},
            {"role": "user", "content": USER_TEMPLATE.format(context=ctx, history=hist, question=q)},
        ]

    def _extractive(self, hits: list[Hit], lang: str) -> str:
        """Evon down -> read out the best matching passage lines in the caller's script."""
        return extractive_answer(hits[0].chunk.body, lang) + " [1]"

    @staticmethod
    def _speakable(text: str) -> str:
        text = CITE_RE.sub("", text)
        text = MD_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    async def _speak(self, r: TurnResult, profile: str) -> None:
        t = time.perf_counter()
        try:
            self.credits.ensure_available()
            tts = await self.tts.synthesize(r.answer, r.language, profile)
            if not tts.cached:
                self.credits.record_tts(tts.chars)
            r.audio_b64 = base64.b64encode(tts.audio).decode()
            r.audio_content_type = tts.content_type
            self.audio_store.put(r.turn_id, tts.audio, tts.content_type)
        except KuralError as exc:  # text answer still returned if TTS fails
            log(logger, logging.WARNING, "tts_failed", error=exc.message)
        r.timings_ms["tts"] = int((time.perf_counter() - t) * 1000)

    async def _canned(self, key, lang, session_id, channel, info, speak, profile, caller_hash) -> TurnResult:
        sid = self.db.ensure_session(session_id, channel, lang, caller_hash)
        text = msg(key, lang)
        r = TurnResult("canned-" + key, sid, lang, False, "", text, [], 0.0, False, None, False,
                       asdict(info) if info else None, {})
        if speak:
            await self._speak(r, profile)
            r.turn_id = f"canned-{key}-{lang}-{profile}"
            if r.audio_b64:
                self.audio_store.put(r.turn_id, base64.b64decode(r.audio_b64), r.audio_content_type)
        return r

    async def speak_text(self, text: str, lang: str, profile: str = "phone") -> str:
        """Pre-render a fixed prompt (greeting etc.), return its audio key."""
        key = f"prompt-{lang}-{profile}-{abs(hash(text))}"
        if not self.audio_store.get(key):
            tts = await self.tts.synthesize(text, lang, profile)
            if not tts.cached:
                self.credits.record_tts(tts.chars)
            self.audio_store.put(key, tts.audio, tts.content_type)
        return key
