"""SQLite-specific hardening (architecture §6.2)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import oasis.storage
from oasis.storage.repository import StorageBusy, StorageUnavailable
from oasis.storage.sqlite import SQLiteRepository
from oasis.types import TurnFeatures


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
        "INSERT INTO turns VALUES ('t1','u','h',1,'system','x',NULL,'x',NULL,NULL)",
        # STRICT: seq must be an integer
        "INSERT INTO turns VALUES ('t2','u','h','one','user','x',NULL,'x',NULL,NULL)",
        # foreign key: unknown user
        "INSERT INTO turns VALUES ('t3','ghost','h',1,'user','x',NULL,'x',NULL,NULL)",
        # an explanation must be JSON
        "INSERT INTO turns VALUES ('t4','u','h',1,'assistant','x',NULL,'x',NULL,'not json')",
        # assessment answers are 0-3 at the database level, not only in code
        "INSERT INTO assessment_answers VALUES ('a','u',1,4,'x')",
        "INSERT INTO assessment_answers VALUES ('a','u',10,1,'x')",
        # a scored assessment must carry its total and band; GAD-7 totals stop at 21
        "INSERT INTO assessments (assessment_id, user_id, instrument, status, offer_reason,"
        " created_at) VALUES ('b','u','PHQ9','scored','{}','x')",
        "INSERT INTO assessments (assessment_id, user_id, instrument, status, offer_reason,"
        " total, band, created_at) VALUES ('c','u','GAD7','scored','{}',22,'severe','x')",
    ]
    conn.execute(
        "INSERT INTO assessments (assessment_id, user_id, instrument, status, offer_reason,"
        " created_at) VALUES ('a','u','PHQ9','in_progress','{}','x')"
    )
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


@pytest.mark.anyio
async def test_signals_are_deleted_with_their_user(tmp_path: Path) -> None:
    path = tmp_path / "s.db"
    repo = SQLiteRepository(path)
    uid = await repo.create_user_session("h")
    await repo.append_signals(uid, "h", TurnFeatures(0.1, 0, 0, 0, 0, 0, 0.2, 0.0, 5, None, 9))
    await repo.close()
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM turn_signals").fetchone() == (0,)


# --- verifiable erasure (Phase 10, rules P9) --------------------------------------------------

MARKER = "zqx-erasure-marker lantern"


async def _user_with_marker(repo: SQLiteRepository, session: str) -> str:
    uid = await repo.create_user_session(session)
    await repo.set_consent(uid, "1")
    for i in range(20):  # enough rows to spread over several pages
        await repo.append_turn(uid, session, turn_id=f"{session}{i}", role="user",
                               content=f"{MARKER} {i}", mode=None, trace_json=None)  # fmt: skip
    await repo.append_audit(uid, "crisis_handoff", '{"tiers":["passive"]}')
    await repo.append_signals(uid, session, TurnFeatures(0.1, 0, 0, 0, 0, 0, 0.2, 0.0, 5, None, 9))
    return uid


def _user_tables(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        columns = {n: {c[1] for c in conn.execute(f"PRAGMA table_info({n})")} for n in names}
        return [n for n in names if "user_id" in columns[n]]


@pytest.mark.anyio
async def test_delete_leaves_zero_rows_in_every_table(tmp_path: Path) -> None:
    """Schema crawl: every table with a user_id column, found from the schema itself."""
    path = tmp_path / "d.db"
    repo = SQLiteRepository(path)
    uid = await _user_with_marker(repo, "h")
    await repo.delete_user(uid)
    await repo.close()
    tables = _user_tables(path)
    assert len(tables) >= 8  # the crawl found the schema, not nothing
    with closing(sqlite3.connect(path)) as conn:
        for table in tables:
            (n,) = conn.execute(
                # Table names come from the schema itself, not from input.
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?",  # noqa: S608
                (uid,),
            ).fetchone()
            assert n == 0, table


@pytest.mark.anyio
async def test_deleted_text_is_gone_from_the_database_and_wal_files(tmp_path: Path) -> None:
    path = tmp_path / "m.db"
    repo = SQLiteRepository(path)
    keep = await _user_with_marker(repo, "keep")  # another user's rows stay
    gone = await _user_with_marker(repo, "gone")
    files = [path, path.with_name(path.name + "-wal")]
    assert any(MARKER.encode() in f.read_bytes() for f in files if f.exists())  # sanity

    await repo.delete_user(gone)
    for f in files:  # while the connection is still open
        if f.exists():
            assert f.read_bytes().count(MARKER.encode()) <= 20, f.name  # only "keep" remains
    assert len(await repo.recent_turns(keep, "keep", 50)) == 20
    await repo.delete_user(keep)
    for f in files:
        if f.exists():
            assert MARKER.encode() not in f.read_bytes(), f.name
    await repo.close()
    for f in files:
        if f.exists():
            assert MARKER.encode() not in f.read_bytes(), f.name


@pytest.mark.anyio
async def test_delete_truncates_the_wal(tmp_path: Path) -> None:
    path = tmp_path / "w.db"
    repo = SQLiteRepository(path)
    uid = await _user_with_marker(repo, "h")
    await repo.delete_user(uid)
    wal = path.with_name(path.name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    await repo.close()
