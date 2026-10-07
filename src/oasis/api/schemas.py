"""HTTP request/response schemas (design §12). Validation happens here, at the trust boundary."""

from __future__ import annotations

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from oasis.types import Mode, Role

MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Client clock: used later for local hour-of-day only, never for latency (design §9.1).
    client_ts: AwareDatetime


class ChatResponse(BaseModel):
    turn_id: str
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: list[str]


class SessionResponse(BaseModel):
    session_id: str


class HistoryTurn(BaseModel):
    turn_id: str
    role: Role
    content: str
    mode: Mode | None
    created_at: datetime


class HistoryResponse(BaseModel):
    turns: list[HistoryTurn]


class HealthResponse(BaseModel):
    status: str
    llm: str
    storage: str
    version: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail
