"""Storage interface shared by every backend. Every method is scoped to one user (rules P5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from oasis.types import Mode, Role, TurnRecord


class StorageError(Exception):
    """Base class. Messages never include stored content."""


class StorageUnavailable(StorageError):
    pass


class StorageBusy(StorageError):
    pass


@dataclass(frozen=True)
class SessionInfo:
    user_id: str


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

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
