"""Storage interface shared by every backend. Every method is scoped to one user (rules P5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from oasis.types import AssessmentRecord, Mode, Role, TurnRecord


class StorageError(Exception):
    """Base class. Messages never include stored content."""


class StorageUnavailable(StorageError):
    pass


class StorageBusy(StorageError):
    pass


AUDIT_EVENTS = frozenset(
    {"crisis_handoff", "consent_given", "consent_withdrawn", "export", "settings_changed"}
)


@dataclass(frozen=True)
class SessionInfo:
    user_id: str
    post_crisis: bool = False


@dataclass(frozen=True)
class AuditRecord:
    event: str
    detail: str  # JSON; never message text
    created_at: str


class Repository(Protocol):
    async def create_user_session(self, session_hash: str) -> str:
        """Create a pseudonymous user with one session; return the user ID."""
        ...

    async def get_session(self, session_hash: str) -> SessionInfo | None: ...

    async def append_turn(
        self,
        user_id: str,
        session_hash: str,
        *,
        turn_id: str,
        role: Role,
        content: str,
        mode: Mode | None,
        trace_json: str | None,
    ) -> TurnRecord: ...

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        """The last `limit` turns of the session, oldest first."""
        ...

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None: ...

    async def append_audit(self, user_id: str, event: str, detail_json: str) -> None: ...

    async def list_audit(self, user_id: str) -> list[AuditRecord]:
        """Oldest first."""
        ...

    async def save_assessment(self, user_id: str, record: AssessmentRecord) -> None:
        """Insert or replace one assessment and its answers (the answers are replaced too)."""
        ...

    async def list_assessments(self, user_id: str) -> list[AssessmentRecord]:
        """This user's assessments, oldest first."""
        ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
