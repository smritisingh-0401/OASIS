"""One contract, every backend (rules T3).

A new backend is added to BACKENDS and must pass unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import Repository, StorageError
from oasis.storage.sqlite import SQLiteRepository
from oasis.types import AssessmentRecord

BACKENDS: dict[str, Callable[[Path], Repository]] = {
    "memory": lambda tmp: MemoryRepository(),
    "sqlite": lambda tmp: SQLiteRepository(tmp / "contract.db"),
}


@pytest.fixture(params=sorted(BACKENDS))
async def repo(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Repository]:
    r = BACKENDS[request.param](tmp_path)
    yield r
    await r.close()


async def _append(repo: Repository, user_id: str, session: str, turn_id: str, content: str) -> None:
    await repo.append_turn(
        user_id, session, turn_id=turn_id, role="user", content=content, mode=None, trace_json=None
    )


@pytest.mark.anyio
async def test_session_round_trip(repo: Repository) -> None:
    user_id = await repo.create_user_session("hash-a")
    info = await repo.get_session("hash-a")
    assert info is not None
    assert info.user_id == user_id
    assert await repo.get_session("unknown") is None


@pytest.mark.anyio
async def test_each_session_gets_a_distinct_user(repo: Repository) -> None:
    assert await repo.create_user_session("h1") != await repo.create_user_session("h2")


@pytest.mark.anyio
async def test_turns_come_back_oldest_first_with_increasing_seq(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    for i in range(5):
        await _append(repo, uid, "h", f"t{i}", f"m{i}")
    turns = await repo.recent_turns(uid, "h", limit=3)
    assert [t.content for t in turns] == ["m2", "m3", "m4"]
    assert [t.seq for t in turns] == [3, 4, 5]
    assert all(t.created_at.endswith("Z") for t in turns)


@pytest.mark.anyio
async def test_append_returns_the_stored_record(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    rec = await repo.append_turn(
        uid, "h", turn_id="t1", role="assistant", content="hi", mode="companion", trace_json="{}"
    )
    assert (rec.turn_id, rec.seq, rec.role, rec.content, rec.mode) == (
        "t1",
        1,
        "assistant",
        "hi",
        "companion",
    )
    assert await repo.recent_turns(uid, "h", limit=10) == [rec]


@pytest.mark.anyio
async def test_queries_are_scoped_to_the_user(repo: Repository) -> None:
    alice = await repo.create_user_session("ha")
    bob = await repo.create_user_session("hb")
    await _append(repo, alice, "ha", "t1", "alice secret")
    assert await repo.recent_turns(bob, "ha", limit=10) == []
    with pytest.raises(StorageError):
        await _append(repo, bob, "ha", "t2", "bob writing into alice's session")


@pytest.mark.anyio
async def test_append_to_unknown_session_fails(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    with pytest.raises(StorageError):
        await _append(repo, uid, "nope", "t1", "x")


@pytest.mark.anyio
async def test_zero_limit_returns_nothing(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    await _append(repo, uid, "h", "t1", "x")
    assert await repo.recent_turns(uid, "h", limit=0) == []


@pytest.mark.anyio
async def test_ping(repo: Repository) -> None:
    assert await repo.ping() is True


@pytest.mark.anyio
async def test_post_crisis_flag_round_trip(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    info = await repo.get_session("h")
    assert info is not None
    assert info.post_crisis is False
    await repo.set_post_crisis(uid, "h", True)
    info = await repo.get_session("h")
    assert info is not None
    assert info.post_crisis is True
    await repo.set_post_crisis(uid, "h", False)
    info = await repo.get_session("h")
    assert info is not None
    assert info.post_crisis is False


@pytest.mark.anyio
async def test_post_crisis_flag_is_scoped_to_the_user(repo: Repository) -> None:
    await repo.create_user_session("ha")
    bob = await repo.create_user_session("hb")
    with pytest.raises(StorageError):
        await repo.set_post_crisis(bob, "ha", True)


@pytest.mark.anyio
async def test_audit_log_is_append_only_and_scoped(repo: Repository) -> None:
    alice = await repo.create_user_session("ha")
    bob = await repo.create_user_session("hb")
    await repo.append_audit(alice, "crisis_handoff", '{"tiers": ["explicit"]}')
    await repo.append_audit(alice, "crisis_handoff", '{"tiers": ["passive"]}')
    audits = await repo.list_audit(alice)
    assert [a.detail for a in audits] == ['{"tiers": ["explicit"]}', '{"tiers": ["passive"]}']
    assert all(a.created_at.endswith("Z") for a in audits)
    assert await repo.list_audit(bob) == []


@pytest.mark.anyio
async def test_unknown_audit_event_is_rejected(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    with pytest.raises(StorageError):
        await repo.append_audit(uid, "made_up_event", "{}")


def _assessment(aid: str = "a1", **changes: Any) -> AssessmentRecord:
    rec = AssessmentRecord(
        aid, "PHQ9", "in_progress", '{"reason": "explicit_request"}', "2026-10-08T12:00:00.000Z"
    )
    return replace(rec, **changes)


@pytest.mark.anyio
async def test_assessment_round_trip_and_update(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    await repo.save_assessment(uid, _assessment(answers=(1, 2)))
    assert await repo.list_assessments(uid) == [_assessment(answers=(1, 2))]
    done = _assessment(
        answers=(1, 2, 0, 0, 0, 0, 0, 0, 0),
        functional=1,
        status="scored",
        total=3,
        band="minimal",
        completed_at="2026-10-08T12:05:00.000Z",
    )
    await repo.save_assessment(uid, done)
    assert await repo.list_assessments(uid) == [done]


@pytest.mark.anyio
async def test_aborting_discards_stored_answers(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    await repo.save_assessment(uid, _assessment(answers=(3, 3, 3)))
    await repo.save_assessment(uid, _assessment(status="aborted", answers=()))
    [rec] = await repo.list_assessments(uid)
    assert (rec.status, rec.answers) == ("aborted", ())


@pytest.mark.anyio
async def test_assessments_are_scoped_to_the_user(repo: Repository) -> None:
    alice = await repo.create_user_session("ha")
    bob = await repo.create_user_session("hb")
    await repo.save_assessment(alice, _assessment())
    assert await repo.list_assessments(bob) == []
    with pytest.raises(StorageError):
        await repo.save_assessment(bob, _assessment(status="aborted"))
    assert [r.status for r in await repo.list_assessments(alice)] == ["in_progress"]


@pytest.mark.anyio
async def test_assessments_come_back_oldest_first(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    await repo.save_assessment(uid, _assessment("b", created_at="2026-10-08T13:00:00.000Z"))
    await repo.save_assessment(uid, _assessment("a", created_at="2026-10-08T12:00:00.000Z"))
    assert [r.assessment_id for r in await repo.list_assessments(uid)] == ["a", "b"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        {"answers": (1, 4)},
        {"answers": (0,) * 10},
        {"status": "scored", "total": None, "band": None},
        {"instrument": "GAD7", "status": "scored", "total": 22, "band": "severe"},
    ],
)
async def test_invalid_assessments_are_rejected(repo: Repository, bad: dict[str, Any]) -> None:
    uid = await repo.create_user_session("h")
    with pytest.raises((StorageError, ValueError)):
        await repo.save_assessment(uid, _assessment(**bad))
    assert await repo.list_assessments(uid) == []
