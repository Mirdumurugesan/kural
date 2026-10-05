# Contest requirement checklist

| Requirement (from the Gnani email and programme page) | Where it's covered | Status |
|---|---|---|
| Project must use Gnani AI models/APIs | Prisma (`app/gnani/stt.py`), Timbre (`app/gnani/tts.py`), Evon (`app/gnani/evon.py`) | ✅ Built |
| Describe the problem, models, users and each member's contribution in the workspace | `docs/SUBMISSION.md` (copy-paste ready) | ✅ Drafted, **you paste it** |
| Build the project | This repo, with 34 tests passing | ✅ Built |
| Record a demo or video of it working | `demo/kural_demo_60s.mp4` (real Gnani outputs; reproducible via `demo_capture.bat`) | ✅ Done, **you review** |
| Written project explanation | `docs/SUBMISSION.md`, `docs/ARCHITECTURE.md`, `README.md` | ✅ |
| List of Gnani models/APIs used | `docs/SUBMISSION.md` table | ✅ |
| Public demo on LinkedIn or X with #GnaniAI and #GreatIndianAIInternshipChallenge | `docs/SOCIAL_POSTS.md` | ⏳ **You post** |
| Nominate those posts in the workspace | — | ⏳ **You nominate** |
| No real phone, account, Aadhaar or PAN numbers or recorded calls; synthetic data only | PII redaction (`core/security.py`), KB contains public info only, noise eval uses TTS-generated speech | ✅ |
| Submit before Nov 10, 2026 (no extensions) | — | ⏳ Aim for Nov 6 |
| Award: regional language (Tamil) | ta-IN end to end, Tamil voice, Tamil KB | ✅ |
| Award: code-mixed (Tanglish) | `app/lang.py`, Tanglish prompt rule, romanised retrieval | ✅ |
| Award: noisy telephonic audio | `app/audio.py`, phone-line mode, live benchmark in `docs/BENCHMARKS.md`, Twilio channel | ✅ |
| Award: real-world impact | Farmers, women, students, health cover; escalation to humans | ✅ |
| Award: best 60-second demo | `demo/kural_demo_60s.mp4` | ✅ |
| Award: Tier 2/3 town | Coimbatore | ✅ |

## Your to-do list
1. [x] Live smoke test passed (Timbre → Prisma round trip). Still to do: check credit usage on the Gnani dashboard and set `CREDIT_COST_*` in `.env` to match.
2. [ ] Ask on Discord whether there's a hosted Evon endpoint. Otherwise set one up (README › Hosting Evon).
3. [x] Noise benchmark run (`docs/BENCHMARKS.md`); numbers are already in the Week 3 post.
4. [x] Public repo: https://github.com/Mirdumurugesan/kural (CI green). Run `push_to_github.bat` after any change.
5. [ ] Fill in the workspace from `docs/SUBMISSION.md`.
6. [ ] Post weekly (`docs/SOCIAL_POSTS.md`); post `demo/kural_demo_60s.mp4` in the final week (re-record after Evon is connected if possible).
7. [ ] Submit by Nov 6 with links to the video and the nominated posts.
