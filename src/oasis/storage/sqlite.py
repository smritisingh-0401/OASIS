"""SQLite backend (WAL) via stdlib sqlite3, hardened per architecture §6.2."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import uuid
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import TypeVar

from oasis.storage.repository import (
    SessionInfo,
    StorageBusy,
    StorageUnavailable,
    utc_now,
)
from oasis.types import Mode, Role, TurnRecord

T = TypeVar("T")


def _migrations() -> list[tuple[int, str]]:
    folder = resources.files("oasis.storage") / "migrations"
    files = sorted((f for f in folder.iterdir() if f.name.endswith(".sql")), key=lambda f: f.name)
    return [(int(f.name.split("_", 1)[0]), f.read_text(encoding="utf-8")) for f in files]


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
        for pragma in (
            "journal_mode=WAL",
            f"busy_timeout={int(busy_timeout_ms)}",
            "foreign_keys=ON",
            "synchronous=NORMAL",
            "secure_delete=ON",
        ):
            self._conn.execute(f"PRAGMA {pragma}")
        self._migrate()

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

    def _call(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            try:
                return fn(self._conn)
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
                "SELECT user_id FROM sessions WHERE session_id_hash = ?", (session_hash,)
            ).fetchone()
            return SessionInfo(row[0]) if row else None

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
                " created_at, trace) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (turn_id, user_id, session_hash, seq, role, content, mode, now, trace_json),
            )
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE session_id_hash = ?",
                (now, session_hash),
            )
            conn.execute("COMMIT")
            return TurnRecord(turn_id, seq, role, content, mode, now)

        return await self._run(op)

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        def op(conn: sqlite3.Connection) -> list[TurnRecord]:
            rows = conn.execute(
                "SELECT turn_id, seq, role, content, mode, created_at FROM turns"
                " WHERE user_id = ? AND session_id_hash = ? ORDER BY seq DESC LIMIT ?",
                (user_id, session_hash, max(limit, 0)),
            ).fetchall()
            return [TurnRecord(*row) for row in reversed(rows)]

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
