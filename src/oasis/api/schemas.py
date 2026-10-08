"""HTTP request/response schemas (design §12). Validation happens here, at the trust boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from oasis.types import InstrumentId, Mode, Role

MAX_MESSAGE_CHARS = 2000


class ConsentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["assessment_consent"]
    accept: bool


class AnswerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["assessment_answer"]
    value: int = Field(ge=0, le=3)
    instrument: InstrumentId
    item: int | None = Field(ge=1, le=9)  # None answers the functional question


class StepAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["assessment_pause", "assessment_resume", "assessment_abort"]


Action = Annotated[ConsentAction | AnswerAction | StepAction, Field(discriminator="type")]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # With an action this is the label of the button pressed, so history stays readable
    # and the safety gate still sees text (design §12).
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Client clock: used later for local hour-of-day only, never for latency (design §9.1).
    client_ts: AwareDatetime
    action: Action | None = None


class AssessmentCardOut(BaseModel):
    step: Literal["offer", "item", "functional", "result", "paused"]
    instrument: InstrumentId
    name: str
    item: int | None
    item_count: int | None
    stem: str | None
    options: list[str]
    total: int | None
    band: str | None


class ChatResponse(BaseModel):
    turn_id: str
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: list[str]
    assessment: AssessmentCardOut | None = None


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
