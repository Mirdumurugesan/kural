"""Kural — Tamil-first voice helpline on Gnani AI (Prisma STT, Evon LLM, Timbre TTS)."""
from __future__ import annotations

import logging
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, api, ops
from app.config import ROOT, Settings, get_settings
from app.core.db import DB
from app.core.errors import KuralError
from app.core.logging import log, request_id_var, setup_logging
from app.core.security import RateLimiter
from app.pipeline import Pipeline
from app.rag.store import HybridIndex
from app.telephony.twilio import router as twilio_router

logger = logging.getLogger("kural")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = httpx.AsyncClient(timeout=settings.http_timeout_s,
                                   limits=httpx.Limits(max_connections=50, max_keepalive_connections=20))
        index = HybridIndex()
        n = index.load_dir(settings.kb_dir)
        db = DB(settings.db_path)
        app.state.settings = settings
        app.state.pipeline = Pipeline(settings, db, index, client)
        app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
        app.state.metrics = {"requests": Counter()}
        if settings.provider_mode == "live" and not settings.gnani_api_key:
            log(logger, logging.WARNING, "gnani_api_key_missing")
        if settings.environment == "prod" and settings.admin_api_key == "change-me":
            raise RuntimeError("Set ADMIN_API_KEY before running in prod")
        log(logger, logging.INFO, "startup", kb_chunks=n, mode=settings.provider_mode, env=settings.environment)
        yield
        await client.aclose()

    app = FastAPI(title="Kural API", version="1.0.0", lifespan=lifespan,
                  description="Tamil-first voice helpline for government schemes, built on Gnani AI "
                              "Prisma (STT), Evon (LLM) and Timbre (TTS).")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def context_mw(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
        finally:
            request_id_var.reset(token)
        resp.headers["x-request-id"] = rid
        resp.headers["x-response-time-ms"] = str(int((time.perf_counter() - t0) * 1000))
        resp.headers["x-content-type-options"] = "nosniff"
        resp.headers["referrer-policy"] = "no-referrer"
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        if hasattr(request.app.state, "metrics"):
            request.app.state.metrics["requests"][(path, resp.status_code)] += 1
        return resp

    @app.exception_handler(KuralError)
    async def kural_error(_: Request, exc: KuralError):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details,
                                               "request_id": request_id_var.get()}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request",
                                                                "details": exc.errors()}})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled_error")
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Unexpected error",
                                                                "request_id": request_id_var.get()}})

    app.include_router(api)
    app.include_router(admin)
    app.include_router(ops)
    app.include_router(twilio_router)

    web = ROOT / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/", include_in_schema=False)
    async def index_page():
        return FileResponse(web / "index.html")

    @app.get("/admin", include_in_schema=False)
    async def admin_page():
        return FileResponse(web / "admin.html")

    return app


app = create_app()
