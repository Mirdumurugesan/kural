# Submission kit: paste into the participant workspace

## Project title
**Kural (குரல்): a Tamil voice helpline for government schemes, built on Gnani Prisma, Evon and Timbre**

## The problem
Many eligible families miss out on welfare benefits, or get stuck halfway, because they can't get a straight answer. A farmer in
Tamil Nadu whose PM-KISAN instalment hasn't arrived, or a woman whose Magalir Urimai Thogai application was rejected,
usually has to read an English website, wait in a queue at an e-Sevai centre, or pay an agent. Many of these callers are
on feature phones, in noisy fields or markets, and speak Tamil mixed with English ("eKYC pannanum", "bank account link
aagala"). Text chatbots and English IVRs don't work for them.

## Who will use it
- **Citizens:** farmers, women heads of families, rural students and senior citizens who call or speak into a phone in Tamil/Tanglish.
- **Helpline and e-Sevai operators:** use the admin dashboard to see what people ask, which questions go unanswered (knowledge gaps) and which callbacks are pending.
- **Departments / NGOs:** upload new circulars as Markdown and the helpline can answer about them within seconds.

## What it does
1. The caller speaks in Tamil, Tanglish or English, on the web or over a phone line (Twilio).
2. A noise-cleaning front-end tuned for telephony prepares the audio, and **Gnani Prisma v2.5** transcribes it (ta-IN, with ITN for rupee amounts, plus scheme-name word boosting).
3. Personal numbers (Aadhaar, PAN, phone, bank account) are redacted before anything is stored or sent to the LLM.
4. A hybrid retriever built for Tamil morphology finds the relevant passages from verified scheme documents.
5. **Gnani Evon v3.3** writes a short, spoken-style answer in the caller's language, using only those passages, and cites them.
6. **Gnani Timbre v2.5** speaks the answer in a natural Tamil voice (8 kHz for phone lines).
7. If the answer isn't in the documents, Kural doesn't guess. It gives the caller a ticket number and logs a callback for a human officer.

## Gnani AI models / APIs used
| Model | API | Usage |
|---|---|---|
| Prisma v2.5 | `POST /stt/v3` (REST) | Tamil speech-to-text: ITN, `bias_list` word boosting, segmented long audio |
| Timbre v2.5 | `POST /api/v1/tts/inference` | Tamil/English/Hindi speech: voices Trisha, Kaveri, Nalini; 16 kHz WAV for web, 8 kHz WAV for telephony |
| Evon v3.3 (30B-A3B) | OpenAI-compatible chat completions (vLLM) | Grounded answer generation in Tamil/Tanglish with citations |

## Engineering highlights
- **Noisy telephony:** ffmpeg denoise chain, per-call SNR estimate, an 8 kHz μ-law phone simulator, and a live benchmark: on a degraded 8 kHz phone line Prisma + Kural keep character errors at 0.8% (20 dB SNR) and 6.5% (0 dB SNR), with the right scheme retrieved 24/24 times (`docs/BENCHMARKS.md`).
- **Tanglish:** script-ratio and romanised-Tamil lexicon detection; character n-gram retrieval robust to Tamil suffixes. Retrieval top-1 is 20/20 across Tamil, romanised Tanglish, code-mixed and English questions.
- **Production readiness:** retries with backoff, circuit breakers, extractive fallback when the LLM is down, PII redaction, rate limiting, admin auth, Twilio signature checks, structured JSON logs with request IDs, Prometheus metrics, health and readiness probes, a credit-budget guard, a TTS cache, Docker, CI, and 34 automated tests.

## Team and contributions
**Mirdula M** (solo), Integrated M.Tech CSE, Sri Ramakrishna Engineering College, Coimbatore: problem framing, system
design, Gnani API integration (Prisma/Timbre/Evon), audio pipeline, retrieval, telephony, UI, evaluation and demo.
*(If you add a teammate, split these lines by who did what, since offers are decided individually.)*

## Award categories this fits
Main Character (Tamil) · Mixed Vibes (Tanglish) · Real Deal (farmers, rural women) · Noise Canceller (telephony audio) ·
Solo Ninja · Small Town, Big Build (Coimbatore) · Demo Day Drop (60-second video). Only one award can be won, so lead with
the Tamil-on-noisy-phone story.

## Links to fill in
- Demo video: `<YouTube / LinkedIn video URL>`
- LinkedIn post: `<url>`
- X post: `<url>`
- Code: `<GitHub repo URL>`
