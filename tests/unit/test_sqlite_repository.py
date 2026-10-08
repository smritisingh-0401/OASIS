"""SQLite-specific hardening (architecture §6.2)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import oasis.storage
from oasis.storage.repository import StorageBusy, StorageUnavailable
from oasis.storage.sqlite import SQLiteRepository


@pytest.mark.anyio
async def test_connection_pragmas(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "p.db")
    assert await repo.pragma("journal_mode") == "wal"
    assert await repo.pragma("foreign_keys") == 1
    assert await repo.pragma("secure_delete") == 1
    await repo.close()


@pytest.mark.anyio
async def test_data_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "r.db"
    repo = SQLiteRepository(path)
    uid = await repo.create_user_session("h")
    await repo.append_turn(
        uid, "h", turn_id="t1", role="user", content="kept", mode=None, trace_json=None
    )
    await repo.close()

    reopened = SQLiteRepository(path)
    assert [t.content for t in await reopened.recent_turns(uid, "h", limit=5)] == ["kept"]
    await reopened.close()


@pytest.mark.anyio
async def test_migrations_are_recorded_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    await SQLiteRepository(path).close()
    await SQLiteRepository(path).close()
    with closing(sqlite3.connect(path)) as conn:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    shipped = sorted(
        int(f.name.split("_")[0])
        for f in (Path(oasis.storage.__file__).parent / "migrations").glob("*.sql")
    )
    assert versions == shipped
    assert shipped == list(range(1, len(shipped) + 1))  # numbered without gaps


@pytest.mark.anyio
async def test_schema_constraints_are_enforced(tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    await SQLiteRepository(path).close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("INSERT INTO users VALUES ('u', '2026-01-01T00:00:00.000Z')")
    conn.execute(
        "INSERT INTO sessions (session_id_hash, user_id, created_at, last_seen_at) "
        "VALUES ('h', 'u', 'x', 'x')"
    )
    bad_rows = [
        # role outside the CHECK list
        "INSERT INTO turns VALUES ('t1','u','h',1,'system','x',NULL,'x',NULL)",
        # STRICT: seq must be an integer
        "INSERT INTO turns VALUES ('t2','u','h','one','user','x',NULL,'x',NULL)",
        # foreign key: unknown user
        "INSERT INTO turns VALUES ('t3','ghost','h',1,'user','x',NULL,'x',NULL)",
    ]
    for sql in bad_rows:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    conn.close()


@pytest.mark.anyio
async def test_locked_database_raises_storage_busy(tmp_path: Path) -> None:
    path = tmp_path / "l.db"
    repo = SQLiteRepository(path, busy_timeout_ms=50)
    uid = await repo.create_user_session("h")
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(StorageBusy):
            await repo.append_turn(
                uid, "h", turn_id="t", role="user", content="x", mode=None, trace_json=None
            )
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    await repo.close()


@pytest.mark.anyio
async def test_closed_database_raises_storage_unavailable(tmp_path: Path) -> None:
    repo = SQLiteRepository(tmp_path / "x.db")
    await repo.close()
    with pytest.raises(StorageUnavailable):
        await repo.get_session("h")
    assert await repo.ping() is False
