"""Saved or ephemeral, chosen per session (FR-PRV-4, design §11.1).

Each session is created in one store and stays there: the saved store (SQLite) or the
in-memory one, which writes nothing to disk. Every call goes to the store holding that session
or user, so an ephemeral session never reaches the database, not even for a read, and keeps
working while the database is down.
"""

from __future__ import annotations

import datetime
from typing import Any

from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import AuditRecord, Repository, SessionInfo, UserSettings
from oasis.types import AssessmentRecord, Mode, Role, SignalRecord, TurnFeatures, TurnRecord


class SplitRepository:
    def __init__(self, saved: Repository, ephemeral: MemoryRepository) -> None:
        self.saved = saved
        self.ephemeral = ephemeral

    def is_ephemeral(self, session_hash: str) -> bool:
        return self.ephemeral.has_session(session_hash)

    def _by_session(self, session_hash: str) -> Repository:
        return self.ephemeral if self.is_ephemeral(session_hash) else self.saved

    def _by_user(self, user_id: str) -> Repository:
        return self.ephemeral if self.ephemeral.has_user(user_id) else self.saved

    async def create_user_session(self, session_hash: str, *, ephemeral: bool = False) -> str:
        store = self.ephemeral if ephemeral else self.saved
        return await store.create_user_session(session_hash)

    async def add_session(self, user_id: str, session_hash: str) -> None:
        # A new conversation stays in the store holding the person: unsaved stays unsaved.
        await self._by_user(user_id).add_session(user_id, session_hash)

    async def get_session(self, session_hash: str) -> SessionInfo | None:
        return await self._by_session(session_hash).get_session(session_hash)

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
        return await self._by_session(session_hash).append_turn(
            user_id,
            session_hash,
            turn_id=turn_id,
            role=role,
            content=content,
            mode=mode,
            trace_json=trace_json,
            explanation_json=explanation_json,
        )

    async def get_explanation(self, user_id: str, turn_id: str) -> str | None:
        return await self._by_user(user_id).get_explanation(user_id, turn_id)

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        return await self._by_session(session_hash).recent_turns(user_id, session_hash, limit)

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None:
        await self._by_session(session_hash).set_post_crisis(user_id, session_hash, value)

    async def set_router_state(self, user_id: str, session_hash: str, state_json: str) -> None:
        await self._by_session(session_hash).set_router_state(user_id, session_hash, state_json)

    async def set_consent(self, user_id: str, disclosure_version: str) -> None:
        await self._by_user(user_id).set_consent(user_id, disclosure_version)

    async def get_settings(self, user_id: str) -> UserSettings:
        return await self._by_user(user_id).get_settings(user_id)

    async def set_settings(self, user_id: str, value: UserSettings) -> None:
        await self._by_user(user_id).set_settings(user_id, value)

    async def append_audit(self, user_id: str, event: str, detail_json: str) -> None:
        await self._by_user(user_id).append_audit(user_id, event, detail_json)

    async def list_audit(self, user_id: str) -> list[AuditRecord]:
        return await self._by_user(user_id).list_audit(user_id)

    async def save_assessment(self, user_id: str, record: AssessmentRecord) -> None:
        await self._by_user(user_id).save_assessment(user_id, record)

    async def list_assessments(self, user_id: str) -> list[AssessmentRecord]:
        return await self._by_user(user_id).list_assessments(user_id)

    async def append_signals(self, user_id: str, session_hash: str, features: TurnFeatures) -> None:
        await self._by_session(session_hash).append_signals(user_id, session_hash, features)

    async def list_signals(self, user_id: str) -> list[SignalRecord]:
        return await self._by_user(user_id).list_signals(user_id)

    async def export_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        return await self._by_user(user_id).export_user(user_id)

    async def delete_user(self, user_id: str) -> None:
        await self._by_user(user_id).delete_user(user_id)

    async def idle_users(self, before: datetime.datetime) -> list[str]:
        # Unsaved sessions have their own, shorter expiry (MemoryRepository idle_timeout_s).
        return await self.saved.idle_users(before)

    async def ping(self) -> bool:
        return await self.saved.ping()

    async def close(self) -> None:
        await self.saved.close()
        await self.ephemeral.close()
