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


class ExerciseConsentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["exercise_consent"]
    accept: bool


class ExerciseStopAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["exercise_stop"]


Action = Annotated[
    ConsentAction | AnswerAction | StepAction | ExerciseConsentAction | ExerciseStopAction,
    Field(discriminator="type"),
]


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
    options: list[str]
    total: int | None
    band: str | None


class ExerciseCardOut(BaseModel):
    step: Literal["offer", "active"]
    mode: Mode
    name: str
    item: int | None
    item_count: int | None
    instruction: str | None = None


class ChatResponse(BaseModel):
    turn_id: str
    preface: str | None = None  # a fixed message shown as its own bubble before `reply`
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: list[str]
    assessment: AssessmentCardOut | None = None
    exercise: ExerciseCardOut | None = None
    # GET /explanations/{explanation_id}; None for a crisis reply or an unsaved turn.
    explanation_id: str | None = None


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ephemeral: bool = False  # kept in memory only, never written to disk (FR-PRV-4)


class SessionResponse(BaseModel):
    session_id: str
    ephemeral: bool = False


class SessionStatus(BaseModel):
    ephemeral: bool
    consented: bool  # accepted the current data notice
    disclosure_version: str


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disclosure_version: str = Field(min_length=1, max_length=32)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["DELETE"]  # typed by the user on the settings page


class HistoryTurn(BaseModel):
    turn_id: str
    role: Role
    content: str
    mode: Mode | None
    created_at: datetime
    explanation_id: str | None = None


class HistoryResponse(BaseModel):
    turns: list[HistoryTurn]
    assessment: AssessmentCardOut | None = None  # card of the open questionnaire, if any
    exercise: ExerciseCardOut | None = None  # open exercise offer or running exercise, if any


class FeatureInfoOut(BaseModel):
    name: str
    source: str | None  # a checked citation; None when exploratory (FR-TRK-4)
    note: str | None
    exploratory: bool


class SessionTrendOut(BaseModel):
    session: int
    started_at: str
    turns: int
    mean: dict[str, float | None]
    variance: dict[str, float | None]


class TurnPointOut(BaseModel):
    at: str
    valence: float


class TrendsResponse(BaseModel):
    label: str  # "language-based mood trend, not a clinical measure" (FR-TRK-3)
    features: list[FeatureInfoOut]
    sessions: list[SessionTrendOut]
    ewma: list[float]
    change_flags: list[bool]
    current: list[TurnPointOut]  # this session, turn by turn


class HealthResponse(BaseModel):
    status: str
    llm: str
    storage: str
    version: str
