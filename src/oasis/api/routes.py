"""Phase 1 endpoints: /health, /session, /chat, /history."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query

import oasis
from oasis.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryResponse,
    HistoryTurn,
    SessionResponse,
)
from oasis.core.engine import ChatEngine, InvalidSession
from oasis.core.templates import TEMPLATES
from oasis.storage.repository import StorageError

log = logging.getLogger("oasis.api")

SESSION_HEADER = "X-OASIS-Session"
SessionHeader = Annotated[str | None, Header(alias=SESSION_HEADER)]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


INVALID_SESSION = ApiError(401, "invalid_session", "Session not found. Start a new session.")
STORAGE_DOWN = ApiError(503, "storage_unavailable", "Saved data is unavailable right now.")


def hash_token(token: str | None) -> str:
    """Only the SHA-256 of the bearer token is stored or compared."""
    return hashlib.sha256(token.encode()).hexdigest() if token else ""


def build_router(engine: ChatEngine) -> APIRouter:
    router = APIRouter()
    repo = engine.repo

    @router.get("/health")
    async def health() -> HealthResponse:
        llm_up, storage_up = await asyncio.gather(engine.llm.health(), repo.ping())
        return HealthResponse(
            status="ok",
            llm="up" if llm_up else "down",
            storage="up" if storage_up else "down",
            version=oasis.__version__,
        )

    @router.post("/session", status_code=201)
    async def create_session() -> SessionResponse:
        token = secrets.token_urlsafe(32)  # 256 bits
        try:
            await repo.create_user_session(hash_token(token))
        except StorageError:
            raise STORAGE_DOWN from None
        return SessionResponse(session_id=token)

    @router.post("/chat")
    async def chat(body: ChatRequest, session: SessionHeader = None) -> ChatResponse:
        try:
            async with asyncio.timeout(engine.settings.request_timeout_s):
                result = await engine.handle_turn(hash_token(session), body.message)
        except InvalidSession:
            raise INVALID_SESSION from None
        except Exception as exc:  # last line of defence: the user always gets a reply
            log.error("chat failed: %s", type(exc).__name__)  # type only: messages may hold text
            reason = "request.deadline" if isinstance(exc, TimeoutError) else "internal.error"
            return ChatResponse(
                turn_id=uuid.uuid4().hex,
                reply=TEMPLATES["llm_unavailable"],
                mode="fallback",
                templated=True,
                persisted=False,
                degraded=[reason],
            )
        return ChatResponse(
            turn_id=result.turn_id,
            reply=result.reply,
            mode=result.mode,
            templated=result.templated,
            persisted=result.persisted,
            degraded=sorted(result.degraded),
        )

    @router.get("/history")
    async def history(
        session: SessionHeader = None, limit: Annotated[int, Query(ge=1, le=200)] = 50
    ) -> HistoryResponse:
        session_hash = hash_token(session)
        try:
            info = await repo.get_session(session_hash)
            if info is None:
                raise INVALID_SESSION
            turns = await repo.recent_turns(info.user_id, session_hash, limit)
        except StorageError:
            raise STORAGE_DOWN from None
        return HistoryResponse(
            turns=[
                HistoryTurn(
                    turn_id=t.turn_id,
                    role=t.role,
                    content=t.content,
                    mode=t.mode,
                    created_at=t.created_at,
                )
                for t in turns
            ]
        )

    return router
