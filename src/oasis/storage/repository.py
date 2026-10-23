"""Storage interface shared by every backend. Every method is scoped to one user (rules P5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from oasis.types import AssessmentRecord, Mode, Role, SignalRecord, TurnFeatures, TurnRecord


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
    router_state: str = "{}"  # JSON owned by the router; storage never interprets it
    consent_version: str | None = None  # the data notice the user accepted, if any


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
        explanation_json: str | None = None,
    ) -> TurnRecord:
        """Append one turn; invalid explanation JSON is rejected."""
        ...

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        """The last `limit` turns of the session, oldest first."""
        ...

    async def get_explanation(self, user_id: str, turn_id: str) -> str | None:
        """The stored explanation JSON of one of this user's turns, if it has one."""
        ...

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None: ...

    async def set_router_state(self, user_id: str, session_hash: str, state_json: str) -> None: ...

    async def set_consent(self, user_id: str, disclosure_version: str) -> None:
        """Record acceptance of a data notice, replacing any earlier one."""
        ...

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

    async def append_signals(
        self, user_id: str, session_hash: str, features: TurnFeatures
    ) -> None: ...

    async def list_signals(self, user_id: str) -> list[SignalRecord]:
        """This user's per-turn features across all their sessions, oldest first."""
        ...

    async def export_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """Every stored row of this user, by table (rules P9). Empty lists for an unknown user."""
        ...

    async def delete_user(self, user_id: str) -> None:
        """Remove the user and everything stored about them; unknown users are a no-op."""
        ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
