"""Application factory: all wiring happens here, so nothing else holds global state."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from oasis.api.middleware import error_response, security_middleware
from oasis.api.pages import render_index
from oasis.api.routes import ApiError, build_router
from oasis.core.engine import ChatEngine
from oasis.llm.client import BoundedLLM, LLMClient
from oasis.llm.fake import FakeLLM
from oasis.llm.llama_server import LlamaServerClient
from oasis.safety.gate import RuleBasedSafetyGate, SafetyGate
from oasis.safety.resources import Resources, load_resources
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import Repository
from oasis.storage.sqlite import SQLiteRepository

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
    safety = safety or RuleBasedSafetyGate.load()
    index_html = render_index(
        (WEB_DIR / "index.html").read_text(encoding="utf-8"),
        crisis_resources or load_resources(),
    )

    bounded = BoundedLLM(
        llm or _default_llm(settings),
        max_concurrency=settings.llm_max_concurrency,
        queue_limit=settings.llm_queue_limit,
    )
    store = repo or _default_repo(settings)
    engine = ChatEngine(safety=safety, llm=bounded, repo=store, settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await bounded.aclose()
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

    app.include_router(build_router(engine))

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(index_html)

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
