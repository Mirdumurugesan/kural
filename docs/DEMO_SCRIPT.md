# Demo scripts

> Use synthetic data only (contest rule): no real Aadhaar, phone or bank numbers on screen or in audio.

## 60-second cut (for the "Demo Day Drop" award and your LinkedIn/X post)

| Time | On screen | Voice-over / caption |
|---|---|---|
| 0–5 s | A phone ringing; caption "A farmer's PM-KISAN money hasn't arrived." | "In Tamil Nadu, getting a straight answer about your scheme money means queues, agents or English websites." |
| 5–20 s | Kural web app, **Phone-line mode ON, SNR 5 dB**. Say: *"PM Kisan panam varala, enna pannanum?"* | Caption: "Noisy 8 kHz phone audio, Tanglish." |
| 20–30 s | Transcript appears in Tamil, then the answer in Tamil **plays aloud** (Timbre), with the source chip `pmkisan.gov.in` | Caption: "Prisma heard it, Evon answered from verified docs, Timbre spoke it." |
| 30–38 s | Hover over the latency bar (stt / retrieve / llm / tts) and the "Tanglish detected" pill | "Every answer is cited and timed." |
| 38–46 s | Ask "bitcoin price today", which escalates with a ticket number spoken in Tamil | "If it doesn't know, it doesn't guess. It books a callback." |
| 46–55 s | Admin dashboard: knowledge gaps, tickets, credits meter, language split | "Officers see what citizens are asking." |
| 55–60 s | Logo card: **Kural · குரல்**, "Built on Gnani Prisma · Evon · Timbre", #GnaniAI #GreatIndianAIInternshipChallenge | "Kural. A voice for every citizen." |

**Recording tips:** use OBS or the Windows Game Bar (Win+G) at 1080p, and turn browser zoom up to 125%. Record the
system audio so Timbre's voice is heard. Add Tamil and English captions, because most people scroll with sound off.

## 3-minute walkthrough (for the submission / interview)
1. **Problem (20 s):** who calls, why English IVRs fail, and noisy rural audio.
2. **Live demo (80 s):** clean Tamil question → Tanglish question → phone-line mode at 0 dB → follow-up question in the same session ("தகுதி என்ன?") → out-of-scope escalation.
3. **Phone call (25 s):** call the Twilio number and pick Tamil (if set up).
4. **Under the hood (40 s):** architecture diagram (`docs/ARCHITECTURE.md`), the noise benchmark table (`eval_out/noise_report.md`), retrieval 20/20, and the Evon-down fallback (stop Evon, ask again, still answers).
5. **Impact and next steps (15 s):** more departments' documents, realtime streaming STT, WhatsApp voice notes.
