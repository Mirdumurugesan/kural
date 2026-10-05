"""Live smoke test of your Gnani key — run this first (uses a few credits).
1) Timbre TTS speaks a Tamil sentence  2) Prisma STT transcribes it back  3) Evon answers (if configured)
Run:  python scripts/gnani_smoke.py"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from app import audio as A  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.gnani.evon import EvonLLM  # noqa: E402
from app.gnani.stt import PrismaSTT  # noqa: E402
from app.gnani.tts import TimbreTTS  # noqa: E402

TEXT = "பிஎம் கிசான் திட்டத்தில் விவசாயிகளுக்கு ஆண்டுக்கு ஆறாயிரம் ரூபாய் கிடைக்கும்."


async def main() -> None:
    s = get_settings()
    if not s.gnani_api_key:
        sys.exit("Set GNANI_API_KEY in .env first")
    s.provider_mode = "live"
    out = Path("eval_out"); out.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=60) as c:
        print("1/3 Timbre TTS …", end=" ", flush=True)
        tts = await TimbreTTS(s, c).synthesize(TEXT, "ta-IN", "phone")
        (out / "smoke_tts.wav").write_bytes(tts.audio)
        print(f"ok — {len(tts.audio)} bytes, voice {tts.voice}, {tts.latency_ms} ms → eval_out/smoke_tts.wav")

        print("2/3 Prisma STT …", end=" ", flush=True)
        pcm = await A.normalize(tts.audio)
        stt = await PrismaSTT(s, c).transcribe_segments([A.to_wav(pcm)], "ta-IN")
        print(f"ok — {stt.latency_ms} ms\n    said : {TEXT}\n    heard: {stt.transcript}")

        print("3/3 Evon …", end=" ", flush=True)
        llm = EvonLLM(s, c)
        if await llm.health():
            r = await llm.chat([{"role": "user", "content": "ஒரு வரியில்: பிஎம் கிசான் என்றால் என்ன?"}], max_tokens=120)
            print(f"ok — {r.latency_ms} ms\n    {r.text}")
        else:
            print(f"not reachable at {s.evon_base_url} (Kural will use extractive fallback). See README › Evon.")


if __name__ == "__main__":
    asyncio.run(main())
