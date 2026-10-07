"""In-memory backend: the ephemeral twin of SQLite. Writes nothing to disk."""

from __future__ import annotations

import uuid

from oasis.storage.repository import SessionInfo, StorageUnavailable, utc_now
from oasis.types import Mode, Role, TurnRecord


class MemoryRepository:
    # No lock: every method body runs without awaiting, so on one event loop it is atomic.

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}  # session_hash -> user_id
        self._turns: dict[str, list[TurnRecord]] = {}  # session_hash -> turns

    async def create_user_session(self, session_hash: str) -> str:
        user_id = uuid.uuid4().hex
        self._sessions[session_hash] = user_id
        self._turns[session_hash] = []
        return user_id

    async def get_session(self, session_hash: str) -> SessionInfo | None:
        user_id = self._sessions.get(session_hash)
        return SessionInfo(user_id) if user_id else None

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
    ) -> TurnRecord:
        if self._sessions.get(session_hash) != user_id:
            raise StorageUnavailable("session not found for user")
        turns = self._turns[session_hash]
        record = TurnRecord(turn_id, len(turns) + 1, role, content, mode, utc_now())
        turns.append(record)
        return record

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        if self._sessions.get(session_hash) != user_id or limit <= 0:
            return []
        return list(self._turns[session_hash][-limit:])

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
