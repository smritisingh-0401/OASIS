"""In-memory backend: the ephemeral twin of SQLite. Writes nothing to disk."""

from __future__ import annotations

import uuid

from oasis.storage.repository import (
    AUDIT_EVENTS,
    AuditRecord,
    SessionInfo,
    StorageUnavailable,
    utc_now,
)
from oasis.types import AssessmentRecord, Mode, Role, TurnRecord

_MAX_TOTAL = {"PHQ9": 27, "GAD7": 21}


class MemoryRepository:
    # No lock: every method body runs without awaiting, so on one event loop it is atomic.

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}  # session_hash -> user_id
        self._turns: dict[str, list[TurnRecord]] = {}  # session_hash -> turns
        self._post_crisis: set[str] = set()  # session hashes
        self._audit: dict[str, list[AuditRecord]] = {}  # user_id -> records
        self._assessments: dict[str, list[AssessmentRecord]] = {}  # user_id -> records

    async def create_user_session(self, session_hash: str) -> str:
        user_id = uuid.uuid4().hex
        self._sessions[session_hash] = user_id
        self._turns[session_hash] = []
        return user_id

    async def get_session(self, session_hash: str) -> SessionInfo | None:
        user_id = self._sessions.get(session_hash)
        return SessionInfo(user_id, session_hash in self._post_crisis) if user_id else None

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

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None:
        if self._sessions.get(session_hash) != user_id:
            raise StorageUnavailable("session not found for user")
        if value:
            self._post_crisis.add(session_hash)
        else:
            self._post_crisis.discard(session_hash)

    async def append_audit(self, user_id: str, event: str, detail_json: str) -> None:
        if event not in AUDIT_EVENTS or user_id not in self._sessions.values():
            raise StorageUnavailable("invalid audit entry")
        self._audit.setdefault(user_id, []).append(AuditRecord(event, detail_json, utc_now()))

    async def list_audit(self, user_id: str) -> list[AuditRecord]:
        return list(self._audit.get(user_id, []))

    async def save_assessment(self, user_id: str, record: AssessmentRecord) -> None:
        # Mirrors the SQLite CHECK constraints so both backends reject the same records.
        valid = (
            user_id in self._sessions.values()
            and len(record.answers) <= 9
            and all(v in (0, 1, 2, 3) for v in record.answers)
            and (record.status != "scored" or (record.total is not None and record.band))
            and (record.total is None or 0 <= record.total <= _MAX_TOTAL[record.instrument])
            and all(r.assessment_id != record.assessment_id
                    for uid, rs in self._assessments.items() if uid != user_id for r in rs)
        )  # fmt: skip
        if not valid:
            raise StorageUnavailable("invalid assessment")
        records = self._assessments.setdefault(user_id, [])
        records[:] = [r for r in records if r.assessment_id != record.assessment_id] + [record]
        records.sort(key=lambda r: r.created_at)

    async def list_assessments(self, user_id: str) -> list[AssessmentRecord]:
        return list(self._assessments.get(user_id, []))

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
