"""Record real Gnani responses for the demo video (synthetic caller voice, per contest rules).
For each scripted question: Timbre (caller voice) speaks it -> degraded to a noisy 8 kHz phone call ->
the full Kural pipeline (Prisma -> retrieval -> Evon / fallback -> Timbre) answers it.
Everything is saved to eval_out/demo/ so the video shows genuine outputs.
Run:  python scripts/demo_capture.py"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from app import audio as A  # noqa: E402
from app.config import ROOT, get_settings  # noqa: E402
from app.core.db import DB  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.gnani.tts import TimbreTTS  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from app.rag.store import HybridIndex  # noqa: E402

CALLER_VOICE = "Vedika"  # a different Tamil Timbre voice plays the caller
TURNS = [
    ("பிஎம் கிசான் பணம் இன்னும் வரல, என்ன பண்ணணும்?", 5),
    ("மகளிர் உரிமைத் தொகை யாருக்கு கிடைக்கும்?", 5),
    ("நாளை மழை வருமா?", 10),
]


async def main() -> None:
    setup_logging("INFO")
    s = get_settings(); s.provider_mode = "live"
    s.db_path = ROOT / "data" / "demo.db"
    if not s.gnani_api_key:
        sys.exit("Set GNANI_API_KEY in .env first")
    out = ROOT / "eval_out" / "demo"; out.mkdir(parents=True, exist_ok=True)
    idx = HybridIndex(); idx.load_dir(s.kb_dir)
    async with httpx.AsyncClient(timeout=60) as c:
        pipe = Pipeline(s, DB(s.db_path), idx, c)
        caller = TimbreTTS(s, c); caller.voices["ta-IN"] = CALLER_VOICE
        session = None
        for n, (q, snr) in enumerate(TURNS, 1):
            clean = await A.normalize((await caller.synthesize(q, "ta-IN", "wav16")).audio, denoise=False)
            phone = A.to_wav(A.simulate_phone_line(clean, snr))
            (out / f"q{n}.wav").write_bytes(phone)
            r = await pipe.handle_audio(phone, language="ta-IN", session_id=session, channel="web-voice")
            session = r.session_id
            d = r.public()
            if d.get("audio_b64"):
                ext = "wav" if "wav" in (d.get("audio_content_type") or "") else "mp3"
                (out / f"a{n}.{ext}").write_bytes(base64.b64decode(d["audio_b64"]))
            d["question_text"], d["snr_db_simulated"] = q, snr
            (out / f"turn{n}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{n}] SNR {snr} dB | heard: {r.transcript} | answer: {r.answer[:120]} | escalated={r.escalated} "
                  f"fallback={r.fallback} | {r.timings_ms}")
    print("Saved to eval_out/demo/")


if __name__ == "__main__":
    asyncio.run(main())
