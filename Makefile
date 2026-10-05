.PHONY: install dev demo test eval-rag smoke eval-noise docker
install:      ; pip install -r requirements-dev.txt
dev:          ; uvicorn app.main:app --reload --port 8080
demo:         ; PROVIDER_MODE=mock uvicorn app.main:app --port 8080
test:         ; pytest -q
eval-rag:     ; python scripts/eval_rag.py
smoke:        ; python scripts/gnani_smoke.py
eval-noise:   ; python scripts/eval_noise.py
docker:       ; docker compose up --build
