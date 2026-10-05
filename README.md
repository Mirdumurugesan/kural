# Kural · குரல்

**A Tamil-first voice helpline for government schemes, built on Gnani AI's own models.**
A farmer, a woman head of family or a college student calls (or taps the mic) and asks in Tamil, Tanglish or English:
*"PM Kisan panam varala, enna pannanum?"* Kural listens through a noisy phone line, finds the answer in verified
scheme documents, and **speaks it back in Tamil** with the official source attached. If it isn't sure, it doesn't
guess: it raises a callback ticket for a human officer.

| Stage | Gnani model | How Kural uses it |
|---|---|---|
| Listen | **Prisma v2.5** (STT) | `ta-IN` REST, ITN on (₹, numbers), scheme-name word boosting, silence-aware 28 s segmentation |
| Think | **Evon v3.3** (30B, open weights) | Grounded answer from retrieved passages only, Tamil/Tanglish style rules, citations |
| Speak | **Timbre v2.5** (TTS) | Tamil voice *Trisha*; 16 kHz WAV for web, 8 kHz WAV for phone lines; disk cache = zero repeat credits |

---

## Why it's built this way

- **Noisy phone audio:** an ffmpeg front-end (high-pass, spectral denoise, dynamic normalisation) runs before Prisma,
  along with an SNR estimate per call. A *phone-line mode* in the UI degrades your own voice to 8 kHz μ-law plus noise,
  so judges can hear the robustness for themselves. `scripts/eval_noise.py` measures it.
- **Tamil + Tanglish retrieval:** Tamil is agglutinative (திட்டம் / திட்டத்தில் / திட்டத்திற்கு), so plain BM25 misses
  matches. Kural fuses word-BM25 with character n-gram TF-IDF using Reciprocal Rank Fusion. On the 20-question
  benchmark (Tamil, romanised Tanglish, code-mixed and English) top-1 is 20/20.
- **Never makes things up:** answers come only from the knowledge base. Out-of-scope questions get escalated with a
  ticket number, and admins see these as *knowledge gaps*.
- **Never goes silent:** if Evon is unreachable, a circuit breaker trips and Kural reads out the best-matching
  verified passage instead (extractive fallback). Prisma and Timbre calls retry with backoff on 429 and 5xx.
- **Safe with data:** Aadhaar, PAN, phone, account and email numbers are redacted before anything is stored. Caller
  numbers are hashed. Twilio webhooks are signature-checked. Admin APIs need a key. Per-IP rate limiting is built in.
- **Credit-aware:** an estimated-credit ledger and a hard budget stop sit in front of every paid call, so the 5,000
  programme credits can't be burned by accident.

## Quick start

### Windows (PowerShell)
```powershell
winget install Gyan.FFmpeg         # once; reopen PowerShell afterwards
cd $HOME\Documents\kural
powershell -ExecutionPolicy Bypass -File run.ps1 -Mock   # offline demo, no credits
# then edit .env (GNANI_API_KEY=...) and run without -Mock for the real models
```

### macOS / Linux
```bash
cp .env.example .env               # add GNANI_API_KEY
pip install -r requirements-dev.txt
make demo                          # offline mock mode on :8080
make dev                           # live mode
```

### Docker
```bash
docker compose up --build          # app on :8080
docker compose --profile gpu up    # + self-hosted Evon via vLLM on an NVIDIA GPU
```

Open **http://localhost:8080** for the helpline, **/admin** for the dashboard and **/docs** for the OpenAPI reference.

### First live run
```bash
python scripts/gnani_smoke.py      # Timbre speaks Tamil → Prisma hears it back → Evon replies
python scripts/eval_rag.py         # retrieval benchmark (free)
python scripts/eval_noise.py       # noisy-phone CER benchmark (~50 short STT calls)
```

## Hosting Evon v3.3

Evon is open-weight (Apache 2.0, on Hugging Face as `gnani/gnani-evon-v3.3-30B-A3B`; no inference provider hosts it yet). Kural talks
to it over the standard OpenAI `/v1/chat/completions` API, so any of these work. Set `EVON_BASE_URL` to match:

1. **Ask Gnani first:** check the Discord to see whether participants get a hosted Evon endpoint. That's the easiest option.
2. **Hugging Face Inference Endpoint** (one A100 80 GB or L40S class GPU): use the vLLM container, then
   `EVON_BASE_URL=https://<endpoint>/v1` and `EVON_API_KEY=<hf token>`.
3. **Your own GPU box:** `vllm serve gnani/gnani-evon-v3.3-30B-A3B --trust-remote-code --max-model-len 32768 --reasoning-parser nano_v3` (vLLM ≥ 0.12). Kural sends `enable_thinking: false` for low-latency spoken answers.

Until it's connected, `/readyz` reports `evon_reachable: false` and Kural answers extractively from the knowledge base.
The demo still works end to end with Prisma and Timbre.

## Phone line (Twilio)

1. Expose the app publicly (for example `cloudflared tunnel --url http://localhost:8080`) and set `PUBLIC_BASE_URL`.
2. In the Twilio console, set your number's *A call comes in* webhook to `POST {PUBLIC_BASE_URL}/telephony/twilio/voice`.
3. Set `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` (this enables signature validation).

Call flow: language menu (1 Tamil, 2 English, 3 Hindi) → Tamil greeting from Timbre → beep → caller asks → Prisma →
Evon → Timbre at 8 kHz → "anything else?" → loop. Every turn appears on the admin dashboard with `channel=phone`.

## API (summary)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/query/voice` | multipart `audio`, `language`, `session_id`, `simulate_phone`, `simulate_snr_db` |
| POST | `/api/v1/query/text` | `{text, language, session_id, speak}` |
| POST | `/api/v1/feedback` | `{turn_id, rating: 1 \| -1}` |
| GET | `/api/v1/audio/{key}` | reply audio (used by telephony `<Play>`) |
| GET | `/api/v1/schemes` | knowledge base documents |
| GET | `/api/v1/admin/analytics` · `/turns` · `/tickets` | dashboard data (needs `X-Admin-Key`) |
| POST | `/api/v1/admin/kb/upload` · `/kb/reindex` | knowledge-base management |
| GET | `/healthz` · `/readyz` · `/metrics` | liveness, readiness, Prometheus |

Each response carries `x-request-id`. Logs are JSON with the same id, so one call can be traced across STT, LLM and TTS.

## Project layout
```
app/
  main.py            FastAPI app, middleware, error handling
  pipeline.py        the voice turn: audio → STT → RAG → LLM → guardrails → TTS
  audio.py           ffmpeg denoise chain, SNR analysis, segmentation, phone-line simulator
  gnani/             Prisma STT, Timbre TTS, Evon LLM clients (retries, circuit breakers)
  rag/store.py       hybrid BM25 + char-n-gram retriever
  lang.py            script / Tanglish detection
  core/              config, SQLite store, security, structured logging, resilient HTTP
  telephony/         Twilio voice webhooks
web/                 citizen helpline UI + admin dashboard (no build step)
kb/                  scheme knowledge base (Markdown, Tamil + English)
scripts/             smoke test, retrieval eval, noise eval
tests/               34 tests: API, wire-format contracts with Gnani, units
docs/                architecture, submission text, demo script, social posts, requirement checklist
```

## Tests
```bash
pytest -q        # 34 tests, fully offline (mock providers + respx-mocked Gnani endpoints)
```

## Data and licence
The knowledge base is compiled from public scheme information for demonstration and contains **no personal data**.
Verify amounts and rules against the linked official sources before any real deployment. Use only synthetic voices and
data in demos, per the contest rules. Code is MIT licensed.
