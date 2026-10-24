"""SQLite backend (WAL) via stdlib sqlite3, hardened per architecture §6.2."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar

from oasis.storage.repository import (
    AuditRecord,
    ErasureIncomplete,
    SessionInfo,
    StorageBusy,
    StorageUnavailable,
    utc_now,
)
from oasis.types import AssessmentRecord, Mode, Role, SignalRecord, TurnFeatures, TurnRecord

T = TypeVar("T")


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("oasis.storage") / "migrations"
    files = sorted((f for f in folder.iterdir() if f.name.endswith(".sql")), key=lambda f: f.name)
    return [(int(f.name.split("_", 1)[0]), f.read_text(encoding="utf-8")) for f in files]


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY rowid")]  # fmt: skip
    return [n for n in names
            if "user_id" in {c[1] for c in conn.execute(f"PRAGMA table_info({n})")}]  # fmt: skip


class SQLiteRepository:
    """One connection, one writer at a time.

    The app makes a few small writes per turn while each LLM reply takes seconds, so a
    single serialised connection is not the bottleneck; calls run in a worker thread so
    the event loop never blocks on disk.
    """

    def __init__(self, path: Path, *, busy_timeout_ms: int = 2000) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, with explicit BEGIN where atomicity matters.
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.Lock()
        self._busy_timeout_ms = int(busy_timeout_ms)
        # Set when another program blocked a delete's overwrite (FR-PRV-3); retried after
        # every later call. The first attempt is at startup, below, in case OASIS stopped
        # before an earlier delete could finish.
        self._erasure_pending = False
        for pragma in (
            "journal_mode=WAL",
            f"busy_timeout={int(busy_timeout_ms)}",
            "foreign_keys=ON",
            "synchronous=NORMAL",
            "secure_delete=ON",
        ):
            self._conn.execute(f"PRAGMA {pragma}")
        self._migrate()
        self._finish_erasure(self._conn)

    def _migrate(self) -> None:
        conn = self._conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL) STRICT"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in _migrations():
            if version in applied:
                continue
            # executescript commits any open transaction first, so BEGIN goes inside the
            # script; the version row joins the same transaction before COMMIT.
            conn.executescript("BEGIN;\n" + sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )
            conn.execute("COMMIT")

    def _finish_erasure(self, conn: sqlite3.Connection) -> bool:
        """Copy every page into the main file and empty the WAL. Never waits for another
        program: with a zero busy timeout a blocked attempt just reports busy."""
        conn.execute("PRAGMA busy_timeout=0")
        try:
            (busy, _, _) = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        finally:
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        self._erasure_pending = bool(busy)
        return not busy

    def _call(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            try:
                result = fn(self._conn)
                if self._erasure_pending:
                    self._finish_erasure(self._conn)
                return result
            except sqlite3.OperationalError as exc:
                if self._in_transaction():
                    self._conn.execute("ROLLBACK")
                if "locked" in str(exc) or "busy" in str(exc):
                    raise StorageBusy from None
                raise StorageUnavailable from None
            except sqlite3.Error:
                if self._in_transaction():
                    self._conn.execute("ROLLBACK")
                raise StorageUnavailable from None

    def _in_transaction(self) -> bool:
        try:
            return self._conn.in_transaction
        except sqlite3.ProgrammingError:  # closed connection
            return False

    async def _run(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(self._call, fn)

    async def create_user_session(self, session_hash: str) -> str:
        user_id = uuid.uuid4().hex
        now = utc_now()

        def op(conn: sqlite3.Connection) -> str:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO users (user_id, created_at) VALUES (?, ?)", (user_id, now))
            conn.execute(
                "INSERT INTO sessions (session_id_hash, user_id, created_at, last_seen_at) "
                "VALUES (?, ?, ?, ?)",
                (session_hash, user_id, now, now),
            )
            conn.execute("COMMIT")
            return user_id

        return await self._run(op)

    async def get_session(self, session_hash: str) -> SessionInfo | None:
        def op(conn: sqlite3.Connection) -> SessionInfo | None:
            row = conn.execute(
                "SELECT s.user_id, s.post_crisis, s.router_state, c.disclosure_version"
                " FROM sessions s LEFT JOIN consent c ON c.user_id = s.user_id"
                " WHERE s.session_id_hash = ?",
                (session_hash,),
            ).fetchone()
            return SessionInfo(row[0], bool(row[1]), row[2], row[3]) if row else None

        return await self._run(op)

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
        now = utc_now()

        def op(conn: sqlite3.Connection) -> TurnRecord:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute(
                "SELECT user_id FROM sessions WHERE session_id_hash = ?", (session_hash,)
            ).fetchone()
            if owner is None or owner[0] != user_id:
                raise sqlite3.IntegrityError("session not found for user")
            (seq,) = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM turns WHERE session_id_hash = ?",
                (session_hash,),
            ).fetchone()
            conn.execute(
                "INSERT INTO turns (turn_id, user_id, session_id_hash, seq, role, content, mode,"
                " created_at, trace, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (turn_id, user_id, session_hash, seq, role, content, mode, now, trace_json,
                 explanation_json),
            )  # fmt: skip
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE session_id_hash = ?",
                (now, session_hash),
            )
            conn.execute("COMMIT")
            return TurnRecord(turn_id, seq, role, content, mode, now, explanation_json is not None)

        return await self._run(op)

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        def op(conn: sqlite3.Connection) -> list[TurnRecord]:
            rows = conn.execute(
                "SELECT turn_id, seq, role, content, mode, created_at, explanation IS NOT NULL"
                " FROM turns WHERE user_id = ? AND session_id_hash = ? ORDER BY seq DESC LIMIT ?",
                (user_id, session_hash, max(limit, 0)),
            ).fetchall()
            return [
                TurnRecord(t, s, r, c, m, at, bool(e)) for t, s, r, c, m, at, e in reversed(rows)
            ]

        return await self._run(op)

    async def get_explanation(self, user_id: str, turn_id: str) -> str | None:
        def op(conn: sqlite3.Connection) -> str | None:
            row = conn.execute(
                "SELECT explanation FROM turns WHERE user_id = ? AND turn_id = ?",
                (user_id, turn_id),
            ).fetchone()
            return row[0] if row else None

        return await self._run(op)

    async def set_post_crisis(self, user_id: str, session_hash: str, value: bool) -> None:
        def op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE sessions SET post_crisis = ? WHERE session_id_hash = ? AND user_id = ?",
                (int(value), session_hash, user_id),
            )
            if cur.rowcount != 1:
                raise sqlite3.IntegrityError("session not found for user")

        await self._run(op)

    async def set_router_state(self, user_id: str, session_hash: str, state_json: str) -> None:
        def op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE sessions SET router_state = ? WHERE session_id_hash = ? AND user_id = ?",
                (state_json, session_hash, user_id),
            )
            if cur.rowcount != 1:
                raise sqlite3.IntegrityError("session not found for user")

        await self._run(op)

    async def set_consent(self, user_id: str, disclosure_version: str) -> None:
        def op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO consent (user_id, disclosure_version, given_at) VALUES (?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE SET disclosure_version ="
                " excluded.disclosure_version, given_at = excluded.given_at",
                (user_id, disclosure_version, utc_now()),
            )

        await self._run(op)

    async def export_user(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """Every table with a user_id column, found from the schema, so a table added by a
        later migration is exported without changing this code (rules P9)."""

        def op(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
            out = {}
            for table in _user_tables(conn):
                cur = conn.execute(
                    # Table names come from sqlite_master, never from input (rules CD9).
                    f"SELECT * FROM {table} WHERE user_id = ? ORDER BY rowid",  # noqa: S608  # nosec B608
                    (user_id,),
                )
                names = [d[0] for d in cur.description]
                out[table] = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
            return out

        return await self._run(op)

    async def delete_user(self, user_id: str) -> None:
        """One DELETE cascades to every table (design §11). secure_delete zeroes the freed
        pages; the checkpoint then copies them into the main file and truncates the WAL, so
        the old text is left in neither (FR-PRV-3)."""

        def op(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            # A checkpoint blocked by another program's open read does not raise; it reports
            # busy and leaves the old text on disk, so the result is checked.
            if not self._finish_erasure(conn):
                raise ErasureIncomplete

        await self._run(op)

    async def append_audit(self, user_id: str, event: str, detail_json: str) -> None:
        def op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO audit_log (audit_id, user_id, event, detail, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, user_id, event, detail_json, utc_now()),
            )

        await self._run(op)

    async def list_audit(self, user_id: str) -> list[AuditRecord]:
        def op(conn: sqlite3.Connection) -> list[AuditRecord]:
            rows = conn.execute(
                "SELECT event, detail, created_at FROM audit_log WHERE user_id = ?"
                " ORDER BY created_at, rowid",
                (user_id,),
            ).fetchall()
            return [AuditRecord(*row) for row in rows]

        return await self._run(op)

    async def save_assessment(self, user_id: str, record: AssessmentRecord) -> None:
        r = record
        now = utc_now()

        def op(conn: sqlite3.Connection) -> None:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute(
                "SELECT user_id FROM assessments WHERE assessment_id = ?", (r.assessment_id,)
            ).fetchone()
            if owner is not None and owner[0] != user_id:
                raise sqlite3.IntegrityError("assessment belongs to another user")
            conn.execute(
                "INSERT INTO assessments (assessment_id, user_id, instrument, status, offer_reason,"
                " total, band, functional, created_at, completed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (assessment_id) DO UPDATE SET status = excluded.status,"
                " offer_reason = excluded.offer_reason, total = excluded.total,"
                " band = excluded.band, functional = excluded.functional,"
                " completed_at = excluded.completed_at",
                (r.assessment_id, user_id, r.instrument, r.status, r.offer_reason, r.total,
                 r.band, r.functional, r.created_at, r.completed_at),
            )  # fmt: skip
            conn.execute(
                "DELETE FROM assessment_answers WHERE assessment_id = ?", (r.assessment_id,)
            )
            conn.executemany(
                "INSERT INTO assessment_answers (assessment_id, user_id, item_index, value,"
                " answered_at) VALUES (?, ?, ?, ?, ?)",
                [(r.assessment_id, user_id, i, v, now) for i, v in enumerate(r.answers, start=1)],
            )
            conn.execute("COMMIT")

        await self._run(op)

    async def append_signals(self, user_id: str, session_hash: str, features: TurnFeatures) -> None:
        now = utc_now()

        def op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "INSERT INTO turn_signals (user_id, session_id_hash, created_at, features)"
                " SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM sessions"
                " WHERE session_id_hash = ? AND user_id = ?)",
                (user_id, session_hash, now, json.dumps(asdict(features)), session_hash, user_id),
            )
            if cur.rowcount != 1:
                raise sqlite3.IntegrityError("session not found for user")

        await self._run(op)

    async def list_signals(self, user_id: str) -> list[SignalRecord]:
        def op(conn: sqlite3.Connection) -> list[SignalRecord]:
            rows = conn.execute(
                "SELECT session_id_hash, created_at, features FROM turn_signals"
                " WHERE user_id = ? ORDER BY created_at, signal_id",
                (user_id,),
            ).fetchall()
            return [SignalRecord(s, at, TurnFeatures(**json.loads(f))) for s, at, f in rows]

        return await self._run(op)

    async def list_assessments(self, user_id: str) -> list[AssessmentRecord]:
        def op(conn: sqlite3.Connection) -> list[AssessmentRecord]:
            rows = conn.execute(
                "SELECT assessment_id, instrument, status, offer_reason, created_at, functional,"
                " total, band, completed_at FROM assessments WHERE user_id = ?"
                " ORDER BY created_at, rowid",
                (user_id,),
            ).fetchall()
            answers: dict[str, list[int]] = {}
            for aid, value in conn.execute(
                "SELECT assessment_id, value FROM assessment_answers WHERE user_id = ?"
                " ORDER BY assessment_id, item_index",
                (user_id,),
            ):
                answers.setdefault(aid, []).append(value)
            return [
                AssessmentRecord(aid, inst, status, reason, created, tuple(answers.get(aid, ())),
                                 functional, total, band, completed)
                for aid, inst, status, reason, created, functional, total, band, completed in rows
            ]  # fmt: skip

        return await self._run(op)

    async def pragma(self, name: str) -> object:
        """Read a connection PRAGMA (diagnostics and hardening tests)."""
        allowed = {"journal_mode", "foreign_keys", "secure_delete", "busy_timeout"}
        if name not in allowed:
            raise ValueError(name)
        return await self._run(lambda conn: conn.execute(f"PRAGMA {name}").fetchone()[0])

    async def ping(self) -> bool:
        try:
            await self._run(lambda conn: conn.execute("SELECT 1").fetchone())
        except StorageUnavailable:
            return False
        return True

    async def close(self) -> None:
        with self._lock:
            self._conn.close()
