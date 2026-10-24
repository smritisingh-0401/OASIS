"""In-memory backend: the ephemeral twin of SQLite. Writes nothing to disk.

It keeps the same fields SQLite does, so an export has the same tables and columns from either
backend (contract test). Used for ephemeral sessions, it forgets a user whose session has been
idle for `idle_timeout_s` (design §11.1) and everything on restart.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, get_args

from oasis.storage.repository import (
    AUDIT_EVENTS,
    AuditRecord,
    SessionInfo,
    StorageUnavailable,
    UserSettings,
    utc_now,
)
from oasis.types import (
    AssessmentRecord,
    Directness,
    Formality,
    Mode,
    Role,
    SignalRecord,
    TurnFeatures,
    TurnRecord,
)

_MAX_TOTAL = {"PHQ9": 27, "GAD7": 21}


class MemoryRepository:
    # No lock: every method body runs without awaiting, so on one event loop it is atomic.

    def __init__(
        self,
        *,
        idle_timeout_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._idle_timeout_s = idle_timeout_s
        self._clock = clock
        self._users: dict[str, str] = {}  # user_id -> created_at
        self._sessions: dict[str, str] = {}  # session_hash -> user_id
        self._session_times: dict[str, list[str]] = {}  # session_hash -> [created, last seen]
        self._idle_since: dict[str, float] = {}  # session_hash -> clock() at last use
        self._turns: dict[str, list[TurnRecord]] = {}  # session_hash -> turns
        self._traces: dict[str, str] = {}  # turn_id -> trace JSON
        self._post_crisis: set[str] = set()  # session hashes
        self._router: dict[str, str] = {}  # session_hash -> router state JSON
        self._audit: dict[str, list[tuple[str, AuditRecord]]] = {}  # user_id -> (id, record)
        self._assessments: dict[str, list[AssessmentRecord]] = {}  # user_id -> records
        self._answered_at: dict[str, str] = {}  # assessment_id -> when its answers were saved
        self._signals: dict[str, list[tuple[int, SignalRecord]]] = {}  # user_id -> (id, record)
        self._signal_ids = 0
        self._explanations: dict[tuple[str, str], str] = {}  # (user_id, turn_id) -> JSON
        self._consent: dict[str, tuple[str, str]] = {}  # user_id -> (version, given_at)
        self._settings: dict[str, tuple[UserSettings, str]] = {}  # user_id -> (value, updated)

    # SplitRepository asks these on every request, saved or not, so an idle unsaved session
    # is cleared out by the next request of any kind, not only by another unsaved one.
    def has_session(self, session_hash: str) -> bool:
        self._expire()
        return session_hash in self._sessions

    def has_user(self, user_id: str) -> bool:
        self._expire()
        return user_id in self._users

    def _touch(self, session_hash: str) -> None:
        self._idle_since[session_hash] = self._clock()
        self._session_times[session_hash][1] = utc_now()

    def _expire(self) -> None:
        if self._idle_timeout_s is None:
            return
        cutoff = self._clock() - self._idle_timeout_s
        for session_hash, since in list(self._idle_since.items()):
            if since < cutoff and session_hash in self._sessions:
                self._forget_user(self._sessions[session_hash])

    def _owns(self, user_id: str, session_hash: str) -> None:
        if self._sessions.get(session_hash) != user_id:
            raise StorageUnavailable("session not found for user")

    async def create_user_session(self, session_hash: str) -> str:
        self._expire()
        user_id = uuid.uuid4().hex
        now = utc_now()
        self._users[user_id] = now
        self._sessions[session_hash] = user_id
        self._session_times[session_hash] = [now, now]
        self._idle_since[session_hash] = self._clock()
        self._turns[session_hash] = []
        return user_id

    async def get_session(self, session_hash: str) -> SessionInfo | None:
        self._expire()
        user_id = self._sessions.get(session_hash)
        if not user_id:
            return None
        self._touch(session_hash)
        consent = self._consent.get(user_id)
        return SessionInfo(
            user_id,
            session_hash in self._post_crisis,
            self._router.get(session_hash, "{}"),
            consent[0] if consent else None,
        )

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
        self._owns(user_id, session_hash)
        if explanation_json is not None:
            try:  # mirrors the SQLite json_valid CHECK
                json.loads(explanation_json)
            except ValueError:
                raise StorageUnavailable("invalid explanation") from None
            self._explanations[(user_id, turn_id)] = explanation_json
        if trace_json is not None:
            self._traces[turn_id] = trace_json
        turns = self._turns[session_hash]
        record = TurnRecord(turn_id, len(turns) + 1, role, content, mode, utc_now(),
                            explanation_json is not None)  # fmt: skip
        turns.append(record)
        self._touch(session_hash)
        return record

    async def get_explanation(self, user_id: str, turn_id: str) -> str | None:
        return self._explanations.get((user_id, turn_id))

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        if self._sessions.get(session_hash) != user_id or limit <= 0:
            return []
        return list(self._turns[session_hash][-limit:])

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None:
        self._owns(user_id, session_hash)
        if value:
            self._post_crisis.add(session_hash)
        else:
            self._post_crisis.discard(session_hash)

    async def set_router_state(self, user_id: str, session_hash: str, state_json: str) -> None:
        self._owns(user_id, session_hash)
        self._router[session_hash] = state_json

    async def set_consent(self, user_id: str, disclosure_version: str) -> None:
        if user_id not in self._users:
            raise StorageUnavailable("unknown user")
        self._consent[user_id] = (disclosure_version, utc_now())

    async def get_settings(self, user_id: str) -> UserSettings:
        return self._settings.get(user_id, (UserSettings(), ""))[0]

    async def set_settings(self, user_id: str, value: UserSettings) -> None:
        # Mirrors the SQLite CHECK constraints so both backends reject the same values.
        style = value.style
        if (
            user_id not in self._users
            or style.directness not in get_args(Directness)
            or style.formality not in get_args(Formality)
        ):
            raise StorageUnavailable("invalid settings")
        self._settings[user_id] = (value, utc_now())

    async def append_audit(self, user_id: str, event: str, detail_json: str) -> None:
        if event not in AUDIT_EVENTS or user_id not in self._users:
            raise StorageUnavailable("invalid audit entry")
        entry = (uuid.uuid4().hex, AuditRecord(event, detail_json, utc_now()))
        self._audit.setdefault(user_id, []).append(entry)

    async def list_audit(self, user_id: str) -> list[AuditRecord]:
        return [record for _, record in self._audit.get(user_id, [])]

    async def save_assessment(self, user_id: str, record: AssessmentRecord) -> None:
        # Mirrors the SQLite CHECK constraints so both backends reject the same records.
        valid = (
            user_id in self._users
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
        self._answered_at[record.assessment_id] = utc_now()

    async def list_assessments(self, user_id: str) -> list[AssessmentRecord]:
        return list(self._assessments.get(user_id, []))

    async def append_signals(self, user_id: str, session_hash: str, features: TurnFeatures) -> None:
        self._owns(user_id, session_hash)
        self._signal_ids += 1
        record = SignalRecord(session_hash, utc_now(), features)
        self._signals.setdefault(user_id, []).append((self._signal_ids, record))

    async def list_signals(self, user_id: str) -> list[SignalRecord]:
        return [record for _, record in self._signals.get(user_id, [])]

    async def export_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """The same tables and columns as the SQLite export (contract test)."""
        sessions = [h for h, uid in self._sessions.items() if uid == user_id]
        consent = self._consent.get(user_id)
        records = self._assessments.get(user_id, [])
        return {
            "users": [{"user_id": user_id, "created_at": self._users[user_id]}]
            if user_id in self._users
            else [],
            "sessions": [
                {
                    "session_id_hash": h,
                    "user_id": user_id,
                    "created_at": self._session_times[h][0],
                    "last_seen_at": self._session_times[h][1],
                    "post_crisis": int(h in self._post_crisis),
                    "router_state": self._router.get(h, "{}"),
                }
                for h in sessions
            ],
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "user_id": user_id,
                    "session_id_hash": h,
                    "seq": t.seq,
                    "role": t.role,
                    "content": t.content,
                    "mode": t.mode,
                    "created_at": t.created_at,
                    "trace": self._traces.get(t.turn_id),
                    "explanation": self._explanations.get((user_id, t.turn_id)),
                }
                for h in sessions
                for t in self._turns[h]
            ],
            "audit_log": [
                {"audit_id": aid, "user_id": user_id, **asdict(record)}
                for aid, record in self._audit.get(user_id, [])
            ],
            "assessments": [
                {
                    "assessment_id": r.assessment_id,
                    "user_id": user_id,
                    "instrument": r.instrument,
                    "status": r.status,
                    "offer_reason": r.offer_reason,
                    "total": r.total,
                    "band": r.band,
                    "functional": r.functional,
                    "created_at": r.created_at,
                    "completed_at": r.completed_at,
                }
                for r in records
            ],
            "assessment_answers": [
                {
                    "assessment_id": r.assessment_id,
                    "user_id": user_id,
                    "item_index": i,
                    "value": v,
                    "answered_at": self._answered_at[r.assessment_id],
                }
                for r in records
                for i, v in enumerate(r.answers, start=1)
            ],
            "turn_signals": [
                {
                    "signal_id": sid,
                    "user_id": user_id,
                    "session_id_hash": s.session_hash,
                    "created_at": s.created_at,
                    "features": json.dumps(asdict(s.features)),
                }
                for sid, s in self._signals.get(user_id, [])
            ],
            "consent": [
                {"user_id": user_id, "disclosure_version": consent[0], "given_at": consent[1]}
            ]
            if consent
            else [],
            "settings": [
                {
                    "user_id": user_id,
                    "directness": v.style.directness,
                    "formality": v.style.formality,
                    "country": v.country,
                    "updated_at": updated,
                }
                for v, updated in [self._settings[user_id]]
            ]
            if user_id in self._settings
            else [],
        }

    async def delete_user(self, user_id: str) -> None:
        self._forget_user(user_id)

    def _forget_user(self, user_id: str) -> None:
        for session_hash in [h for h, uid in self._sessions.items() if uid == user_id]:
            for turn in self._turns.pop(session_hash, []):
                self._traces.pop(turn.turn_id, None)
                self._explanations.pop((user_id, turn.turn_id), None)
            for table in (self._sessions, self._session_times, self._idle_since, self._router):
                table.pop(session_hash, None)
            self._post_crisis.discard(session_hash)
        for record in self._assessments.pop(user_id, []):
            self._answered_at.pop(record.assessment_id, None)
        for by_user in (self._users, self._audit, self._signals, self._consent, self._settings):
            by_user.pop(user_id, None)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
