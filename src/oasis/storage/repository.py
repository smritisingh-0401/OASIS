"""Storage interface shared by every backend. Every method is scoped to one user (rules P5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from oasis.types import (
    AssessmentRecord,
    Mode,
    Role,
    SignalRecord,
    StyleProfile,
    TurnFeatures,
    TurnRecord,
)


class StorageError(Exception):
    """Base class. Messages never include stored content."""


class StorageUnavailable(StorageError):
    pass


class StorageBusy(StorageError):
    pass


class ErasureIncomplete(StorageError):
    """The user's rows are deleted, but another program holding the file open stopped their
    old bytes from being overwritten yet. The store finishes it as soon as it can."""


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
class UserSettings:
    """What the user chose in Settings (design §11): the style, and the help card's country
    (an ISO code from resources.yaml, checked by the API). Nothing here is ever inferred."""

    style: StyleProfile = field(default_factory=StyleProfile)
    country: str | None = None


@dataclass(frozen=True)
class AuditRecord:
    event: str
    detail: str  # JSON; never message text
    created_at: str


class Repository(Protocol):
    async def create_user_session(self, session_hash: str) -> str:
        """Create a pseudonymous user with one session; return the user ID."""
        ...

    async def add_session(self, user_id: str, session_hash: str) -> None:
        """Another conversation for an existing user (New chat); unknown user -> StorageError."""
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

    async def get_settings(self, user_id: str) -> UserSettings:
        """The user's settings; the defaults until they change them."""
        ...

    async def set_settings(self, user_id: str, value: UserSettings) -> None:
        """Replace the user's settings; values outside the allowed sets are rejected."""
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

    async def idle_users(self, before: datetime) -> list[str]:
        """Users with no message in any session since `before`, least recent first (saved
        conversations expire after a quiet spell, Phase 13)."""
        ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


def utc_stamp(at: datetime) -> str:
    """The stored timestamp format: UTC, milliseconds, "Z"; ordered like the times."""
    return at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now() -> str:
    return utc_stamp(datetime.now(UTC))
