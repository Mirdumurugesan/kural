"""Noisy-telephony benchmark for Prisma + Kural's audio front-end (synthetic speech only).

For each Tamil question: Timbre speaks it -> we degrade it to an 8 kHz mu-law phone call with
noise at several SNRs -> Prisma transcribes (a) the raw degraded audio and (b) after Kural's
denoise chain -> character error rate (CER) vs the original text. Also checks whether retrieval
still finds the right scheme. Writes eval_out/noise_report.md.
Credits: ~6 questions x 4 SNRs x 2 runs ≈ 48 short STT calls + 6 TTS calls.
Run:  python scripts/eval_noise.py"""
from __future__ import annotations

import asyncio
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from app import audio as A  # noqa: E402
from app.config import ROOT, get_settings  # noqa: E402
from app.gnani.stt import PrismaSTT  # noqa: E402
from app.gnani.tts import TimbreTTS  # noqa: E402
from app.rag.store import HybridIndex  # noqa: E402

QUESTIONS = [
    ("பிஎம் கிசான் திட்டத்தில் எவ்வளவு பணம் கிடைக்கும்", "pm-kisan"),
    ("மகளிர் உரிமைத் தொகை யாருக்கு கிடைக்கும்", "kmut"),
    ("மருத்துவக் காப்பீடு அட்டை எங்கே வாங்குவது", "pmjay-cmchis"),
    ("பயிர் காப்பீடு பிரீமியம் எவ்வளவு", "pmfby"),
    ("கல்லூரி மாணவிகளுக்கு மாதம் ஆயிரம் ரூபாய் திட்டம்", "pudhumai-penn-tamil-pudhalvan"),
    ("கிசான் கடன் அட்டை வட்டி எவ்வளவு", "kcc"),
]
SNRS = [20, 10, 5, 0]


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    return "".join(ch for ch in t if ch.isalnum() or unicodedata.category(ch).startswith("M"))


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rc != hc))
    return d[len(h)] / max(1, len(r))


async def main() -> None:
    s = get_settings(); s.provider_mode = "live"
    s.stt_format = "verbatim"  # score spoken words; ITN ("ஆயிரம் ரூபாய்" -> "₹1,000") would count as errors
    if not s.gnani_api_key:
        sys.exit("Set GNANI_API_KEY in .env first")
    if not A.ffmpeg_available():
        sys.exit("ffmpeg is required for the denoise comparison (winget install Gyan.FFmpeg)")
    idx = HybridIndex(); idx.load_dir(ROOT / "kb")
    rows = []
    async with httpx.AsyncClient(timeout=60) as c:
        tts, stt = TimbreTTS(s, c), PrismaSTT(s, c)
        for q, doc in QUESTIONS:
            clean = await A.normalize((await tts.synthesize(q, "ta-IN", "wav16")).audio, denoise=False)
            for snr in SNRS:
                degraded = A.to_wav(A.simulate_phone_line(clean, snr))
                raw_pcm = await A.normalize(degraded, denoise=False)
                den_pcm = await A.normalize(degraded, denoise=True)
                raw = (await stt.transcribe_segments([A.to_wav(raw_pcm)], "ta-IN")).transcript
                den = (await stt.transcribe_segments([A.to_wav(den_pcm)], "ta-IN")).transcript
                hit = bool((h := idx.search(den, k=1, min_score=0.08)) and h[0].chunk.doc_id == doc)
                rows.append((q, snr, cer(q, raw), cer(q, den), hit, den))
                print(f"SNR {snr:>2} dB  CER raw {cer(q, raw):.2f}  denoised {cer(q, den):.2f}  retrieval {'✓' if hit else '✗'}  | {den}")
    lines = ["# Kural noisy-telephony benchmark", "",
             "Synthetic Tamil questions (Timbre) → 8 kHz μ-law phone channel + noise → Prisma v2.5 (verbatim).",
             "CER = character error rate vs the original text (lower is better). Retrieval = right scheme found.", "",
             "| SNR (dB) | CER raw | CER after Kural denoise | Retrieval top-1 |", "|---|---|---|---|"]
    for snr in SNRS:
        sub = [r for r in rows if r[1] == snr]
        lines.append(f"| {snr} | {sum(r[2] for r in sub) / len(sub):.3f} | {sum(r[3] for r in sub) / len(sub):.3f} | "
                     f"{sum(r[4] for r in sub)}/{len(sub)} |")
    out = Path("eval_out"); out.mkdir(exist_ok=True)
    (out / "noise_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines)); print("\nSaved eval_out/noise_report.md")


if __name__ == "__main__":
    asyncio.run(main())
