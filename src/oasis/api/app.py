"""Application factory: all wiring happens here, so nothing else holds global state."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from oasis.api.middleware import error_response, security_middleware
from oasis.api.pages import load_disclosure, render_index, render_settings
from oasis.api.routes import ApiError, build_router
from oasis.assessment.instruments import load_all as load_assessment_content
from oasis.core.engine import ChatEngine
from oasis.core.signals import load_all as load_signal_content
from oasis.guard.checks import load_rules as load_reply_checks
from oasis.llm.client import LLMClient
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.psychoed.selector import load_all as load_psychoed
from oasis.router.exercise import load_all as load_techniques
from oasis.router.weights import config as router_config
from oasis.safety.gate import RuleBasedSafetyGate, SafetyGate
from oasis.safety.resources import Resources, load_resources
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import Repository, StorageError
from oasis.storage.split import SplitRepository
from oasis.storage.sqlite import SQLiteRepository
from oasis.style.framing import load_framing
from oasis.tracking.features import load_config as load_tracking

log = logging.getLogger("oasis.app")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _default_llm(settings: Settings) -> LLMClient:
    if settings.llm_backend == "fake":
        return FakeLLM()
    return LlamaServerClient(
        base_url=settings.llm_url,
        model=settings.llm_model,
        connect_timeout_s=settings.llm_connect_timeout_s,
        sampling={
            "temperature": settings.llm_temperature,
            "top_p": settings.llm_top_p,
            "top_k": settings.llm_top_k,
            "min_p": settings.llm_min_p,
        },
    )


def _default_repo(settings: Settings) -> Repository:
    if settings.storage_backend == "memory":
        return MemoryRepository()
    return SQLiteRepository(settings.db_path, busy_timeout_ms=settings.sqlite_busy_timeout_ms)


async def expire_idle(repo: Repository, days: int) -> int:
    """Delete saved conversations with no message for `days` days, through the same erasure
    as the Delete button (Phase 13, data notice). Storage trouble is logged and retried on
    the next run; it never stops OASIS starting. Returns how many were deleted."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    deleted = 0
    try:
        for user_id in await repo.idle_users(cutoff):
            await repo.delete_user(user_id)
            deleted += 1
    except StorageError as exc:
        log.error("expiry incomplete: %s", type(exc).__name__)
    if deleted:
        log.info("expired %d saved conversations", deleted)  # a count, never an ID
    return deleted


async def _every_day(repo: Repository, days: int) -> None:
    while True:
        await asyncio.sleep(24 * 3600)
        await expire_idle(repo, days)


def create_app(
    settings: Settings | None = None,
    *,
    safety: SafetyGate | None = None,
    llm: LLMClient | None = None,
    repo: Repository | None = None,
    crisis_resources: Resources | None = None,
) -> FastAPI:
    settings = settings or Settings()
    # Safety content is loaded and validated before anything else; invalid patterns or
    # resources stop the app here (rules S5).
    safety = safety or RuleBasedSafetyGate(load_ruleset())
    load_assessment_content()
    # Signal lexicons, router weights, exercise scripts, psychoeducation items and reply
    # checks: a bad file stops startup here.
    load_signal_content()
    router_config()
    load_techniques()
    load_psychoed()
    load_reply_checks()
    load_tracking()
    load_framing()
    disclosure = load_disclosure()
    resources = crisis_resources or load_resources()
    index_html = render_index(
        (WEB_DIR / "index.html").read_text(encoding="utf-8"), resources, disclosure
    )
    settings_html = render_settings(
        (WEB_DIR / "settings.html").read_text(encoding="utf-8"), resources
    )

    # Each session is saved or ephemeral, chosen when it starts (FR-PRV-4).
    ephemeral = MemoryRepository(idle_timeout_s=settings.ephemeral_idle_timeout_s)
    store = SplitRepository(repo or _default_repo(settings), ephemeral)
    # The engine bounds the model client itself (BoundedLLM).
    engine = ChatEngine(safety=safety, llm=llm or _default_llm(settings), repo=store,
                        settings=settings, consent_version=disclosure.version)  # fmt: skip

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await expire_idle(store, settings.saved_idle_expiry_days)
        daily = asyncio.create_task(_every_day(store, settings.saved_idle_expiry_days))
        yield
        daily.cancel()
        with suppress(asyncio.CancelledError):
            await daily
        await engine.llm.aclose()
        await store.close()

    app = FastAPI(
        title="OASIS",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.middleware("http")(security_middleware(settings.max_body_bytes))

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names only — the default handler would echo the submitted text back.
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        return error_response(422, "invalid_turn", "Invalid request: " + ", ".join(fields))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    app.include_router(build_router(engine, store, frozenset(c.code for c in resources.countries)))

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(index_html)

    @app.get("/settings.html", include_in_schema=False)
    async def settings_page() -> HTMLResponse:
        return HTMLResponse(settings_html)

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
