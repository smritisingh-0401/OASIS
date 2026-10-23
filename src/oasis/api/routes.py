"""HTTP endpoints: /health, /session, /consent, /chat, /history, /trends, /explanations,
/export and /account."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import secrets
import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Query, Response

import oasis
from oasis.api.pages import load_disclosure
from oasis.api.schemas import (
    Action,
    AnswerAction,
    AssessmentCardOut,
    ChatRequest,
    ChatResponse,
    ConsentRequest,
    DeleteRequest,
    ExerciseCardOut,
    ExerciseConsentAction,
    ExerciseStopAction,
    FeatureInfoOut,
    HealthResponse,
    HistoryResponse,
    HistoryTurn,
    SessionRequest,
    SessionResponse,
    SessionStatus,
    SessionTrendOut,
    StepAction,
    TrendsResponse,
    TurnPointOut,
)
from oasis.assessment import flow
from oasis.core.engine import ChatEngine, ConsentRequired, InvalidSession
from oasis.core.templates import TEMPLATES
from oasis.router.exercise import card_for
from oasis.router.router import load_state
from oasis.storage.repository import SessionInfo, StorageError, utc_now
from oasis.storage.split import SplitRepository
from oasis.tracking.aggregate import trend
from oasis.tracking.features import load_config as load_tracking
from oasis.types import AssessmentAction, ExerciseAction, ExerciseCard

log = logging.getLogger("oasis.api")

SESSION_HEADER = "X-OASIS-Session"
SessionHeader = Annotated[str | None, Header(alias=SESSION_HEADER)]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


INVALID_SESSION = ApiError(401, "invalid_session", "Session not found. Start a new session.")
STORAGE_DOWN = ApiError(503, "storage_unavailable", "Saved data is unavailable right now.")
NO_EXPLANATION = ApiError(404, "not_found", "No explanation for this reply.")
CONSENT_REQUIRED = ApiError(
    403, "consent_required", "Please review and accept the data notice first."
)
OUTDATED_NOTICE = ApiError(422, "invalid_consent", "That is not the current data notice.")


def hash_token(token: str | None) -> str:
    """Only the SHA-256 of the bearer token is stored or compared."""
    return hashlib.sha256(token.encode()).hexdigest() if token else ""


def _action(action: Action | None) -> AssessmentAction | ExerciseAction | None:
    if action is None:
        return None
    if isinstance(action, ExerciseConsentAction):
        return ExerciseAction("accept" if action.accept else "decline")
    if isinstance(action, ExerciseStopAction):
        return ExerciseAction("stop")
    if isinstance(action, AnswerAction):
        return AssessmentAction("answer", action.value, action.instrument, action.item)
    if isinstance(action, StepAction):
        kinds = {"assessment_pause": "pause", "assessment_resume": "resume",
                 "assessment_abort": "abort"}  # fmt: skip
        return AssessmentAction(kinds[action.type])  # type: ignore[arg-type]
    return AssessmentAction("accept" if action.accept else "decline")


def _exercise_out(card: ExerciseCard | None) -> ExerciseCardOut | None:
    return ExerciseCardOut(**asdict(card)) if card else None


def build_router(engine: ChatEngine, repo: SplitRepository) -> APIRouter:
    router = APIRouter()

    async def resolve(session: str | None) -> tuple[str, SessionInfo]:
        """The session's hash and stored state; 401 if unknown, 503 if storage is down."""
        session_hash = hash_token(session)
        try:
            info = await repo.get_session(session_hash)
        except StorageError:
            raise STORAGE_DOWN from None
        if info is None:
            raise INVALID_SESSION
        return session_hash, info

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
    async def create_session(body: SessionRequest | None = None) -> SessionResponse:
        ephemeral = body is not None and body.ephemeral
        token = secrets.token_urlsafe(32)  # 256 bits
        try:
            await repo.create_user_session(hash_token(token), ephemeral=ephemeral)
        except StorageError:
            raise STORAGE_DOWN from None
        return SessionResponse(session_id=token, ephemeral=ephemeral)

    @router.get("/session")
    async def session_status(session: SessionHeader = None) -> SessionStatus:
        session_hash, info = await resolve(session)
        version = load_disclosure().version
        return SessionStatus(
            ephemeral=repo.is_ephemeral(session_hash),
            consented=info.consent_version == version,
            disclosure_version=version,
        )

    @router.post("/consent", status_code=204)
    async def consent(body: ConsentRequest, session: SessionHeader = None) -> Response:
        session_hash, info = await resolve(session)
        if body.disclosure_version != load_disclosure().version:
            raise OUTDATED_NOTICE  # accepted text must be the text shown
        detail = json.dumps({"disclosure_version": body.disclosure_version})
        try:
            await repo.set_consent(info.user_id, body.disclosure_version)
            await repo.append_audit(info.user_id, "consent_given", detail)
        except StorageError:
            raise STORAGE_DOWN from None
        engine.remember_consent(session_hash)
        return Response(status_code=204)

    @router.get("/export")
    async def export(session: SessionHeader = None) -> Response:
        """Everything stored about the user, as a download (FR-PRV-2, rules P9)."""
        session_hash, info = await resolve(session)
        try:
            tables = await repo.export_user(info.user_id)
        except StorageError:
            raise STORAGE_DOWN from None
        body = {"format": "oasis-export/1", "exported_at": utc_now(),
                "ephemeral": repo.is_ephemeral(session_hash), "tables": tables}  # fmt: skip
        return Response(
            json.dumps(body, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="oasis-export.json"'},
        )

    @router.delete("/account", status_code=204)
    async def delete_account(body: DeleteRequest, session: SessionHeader = None) -> Response:
        """Delete the user and everything about them (FR-PRV-3); cannot be undone."""
        session_hash, info = await resolve(session)
        try:
            await repo.delete_user(info.user_id)
        except StorageError:
            raise STORAGE_DOWN from None
        engine.forget(session_hash)
        return Response(status_code=204)

    @router.post("/chat")
    async def chat(
        body: ChatRequest, background: BackgroundTasks, session: SessionHeader = None
    ) -> ChatResponse:
        session_hash = hash_token(session)
        try:
            async with asyncio.timeout(engine.settings.request_timeout_s):
                result = await engine.handle_turn(
                    session_hash, body.message, _action(body.action), client_ts=body.client_ts
                )
        except InvalidSession:
            raise INVALID_SESSION from None
        except ConsentRequired:
            raise CONSENT_REQUIRED from None
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
        if result.mode == "crisis":
            # Runs after the response is sent, so audit storage can never delay or block
            # the handoff (rules S2).
            background.add_task(
                engine.record_crisis, session_hash, result.verdict, result.escalated
            )
        return ChatResponse(
            turn_id=result.turn_id,
            preface=result.preface,
            reply=result.reply,
            mode=result.mode,
            templated=result.templated,
            persisted=result.persisted,
            degraded=sorted(result.degraded),
            assessment=AssessmentCardOut(**asdict(result.card)) if result.card else None,
            exercise=_exercise_out(result.exercise_card),
            explanation_id=result.explanation_id,
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
            records = await repo.list_assessments(info.user_id)
        except StorageError:
            raise STORAGE_DOWN from None
        open_rec, _ = flow.active(records, datetime.datetime.now(datetime.UTC))
        card = flow.card_for(open_rec) if open_rec else None
        return HistoryResponse(
            assessment=AssessmentCardOut(**asdict(card)) if card else None,
            exercise=_exercise_out(card_for(load_state(info.router_state))),
            turns=[
                HistoryTurn(
                    turn_id=t.turn_id,
                    role=t.role,
                    content=t.content,
                    mode=t.mode,
                    created_at=t.created_at,
                    explanation_id=t.turn_id if t.has_explanation else None,
                )
                for t in turns
            ],
        )

    @router.get("/trends")
    async def trends(session: SessionHeader = None) -> TrendsResponse:
        session_hash = hash_token(session)
        try:
            info = await repo.get_session(session_hash)
            if info is None:
                raise INVALID_SESSION
            records = await repo.list_signals(info.user_id)
        except StorageError:
            raise STORAGE_DOWN from None
        cfg = load_tracking()
        t = trend(records, session_hash, cfg)
        return TrendsResponse(
            label=t.label,
            features=[FeatureInfoOut(name=n, **asdict(i)) for n, i in cfg.features.items()],
            sessions=[SessionTrendOut(**asdict(s)) for s in t.sessions],
            ewma=t.ewma,
            change_flags=t.change_flags,
            current=[TurnPointOut(at=at, valence=v) for at, v in t.current],
        )

    @router.get("/explanations/{explanation_id}")
    async def explanation(explanation_id: str, session: SessionHeader = None) -> Response:
        """The stored record, byte for byte, so identical turns give identical bodies."""
        session_hash = hash_token(session)
        try:
            info = await repo.get_session(session_hash)
            if info is None:
                raise INVALID_SESSION
            body = await repo.get_explanation(info.user_id, explanation_id)
        except StorageError:
            raise STORAGE_DOWN from None
        if body is None:
            raise NO_EXPLANATION
        return Response(body, media_type="application/json")

    return router
