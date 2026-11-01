"""HTTP request/response schemas (design §12). Validation happens here, at the trust boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from oasis.types import Directness, Formality, InstrumentId, Mode, Role

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
    item: int | None = Field(ge=1, le=9)


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

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
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
    preface: str | None = None
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: list[str]
    assessment: AssessmentCardOut | None = None
    exercise: ExerciseCardOut | None = None
    explanation_id: str | None = None
    style_suggestion: bool = False


class UserSettingsBody(BaseModel):
    """GET and PUT /settings (FR-CUL-1). The country is checked against the help card."""

    model_config = ConfigDict(extra="forbid")

    directness: Directness
    formality: Formality
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ephemeral: bool = False


class SessionResponse(BaseModel):
    session_id: str
    ephemeral: bool = False


class SessionStatus(BaseModel):
    ephemeral: bool
    consented: bool
    disclosure_version: str


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disclosure_version: str = Field(min_length=1, max_length=32)


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["DELETE"]


class HistoryTurn(BaseModel):
    turn_id: str
    role: Role
    content: str
    mode: Mode | None
    created_at: datetime
    explanation_id: str | None = None


class HistoryResponse(BaseModel):
    turns: list[HistoryTurn]
    assessment: AssessmentCardOut | None = None
    exercise: ExerciseCardOut | None = None


class FeatureInfoOut(BaseModel):
    name: str
    source: str | None
    note: str | None
    exploratory: bool


class SessionTrendOut(BaseModel):
    session: int
    started_at: str
    turns: int
    mean: dict[str, float | None]
    variance: dict[str, float | None]
    valence: list[float]
    is_current: bool


class TurnPointOut(BaseModel):
    at: str
    valence: float


class TrendsResponse(BaseModel):
    label: str
    features: list[FeatureInfoOut]
    sessions: list[SessionTrendOut]
    ewma: list[float]
    change_flags: list[bool]
    current: list[TurnPointOut]


class HealthResponse(BaseModel):
    status: str
    llm: str
    storage: str
    version: str
