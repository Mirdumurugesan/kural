# Benchmarks (live Gnani APIs, run 5 Oct 2026)

## Noisy telephony: Prisma v2.5 + Kural audio front-end
Six synthetic Tamil questions were spoken by Timbre, degraded to an 8 kHz μ-law phone call with background noise
at each SNR, then transcribed by Prisma (verbatim). CER = character error rate vs the original text (lower is better).

| SNR (dB) | CER raw | CER after Kural denoise | Right scheme retrieved |
|---|---|---|---|
| 20 | 1.2% | 0.8% | 6/6 |
| 10 | 1.2% | 3.0% | 6/6 |
| 5 | 2.7% | 1.2% | 6/6 |
| 0 | 7.7% | 6.5% | 6/6 |

At 0 dB the noise is as loud as the voice, and Kural still routed every question to the correct scheme (24/24 overall).
The denoise chain helps at 20, 5 and 0 dB but is slightly worse at 10 dB, so treat it as a modest gain.
Reproduce with `python scripts/eval_noise.py` (or `noise_test.bat` on Windows).

## Round trip: Timbre → Prisma
- Said: பிஎம் கிசான் திட்டத்தில் விவசாயிகளுக்கு ஆண்டுக்கு ஆறாயிரம் ரூபாய் கிடைக்கும்.
- Heard: பிஎம் கிசான் திட்டத்தில் விவசாயிகளுக்கு ஆண்டுக்கு ₹6,000 கிடைக்கும் (ITN on)
- Timbre ~1.9 s (Trisha voice), Prisma ~1.0 s

## Retrieval (offline, free)
20/20 top-1 across Tamil (7), romanised Tanglish (6), code-mixed (2) and English (5) questions. 2 of 3 off-topic
questions were rejected by retrieval itself; the third is left to Evon's NO_ANSWER rule.

## Timbre output format reliability (finding)
Same texts, same voice, sent to `POST /api/v1/tts/inference` 2.5 s apart:

| container | succeeded |
|---|---|
| mp3 (24 kHz, 64k) | 2 of 9 (HTTP 500 "technical difficulties" on the rest) |
| wav (24 kHz, linear PCM) | 9 of 9 |

Kural therefore requests WAV for both web and phone. Reported to the Gnani team.
Reproduce with `python scripts/tts_probe.py`.
