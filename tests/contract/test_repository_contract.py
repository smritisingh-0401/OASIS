"""One contract, every backend (rules T3).

A new backend is added to BACKENDS and must pass unchanged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import Repository, StorageError
from oasis.storage.sqlite import SQLiteRepository
from oasis.types import AssessmentRecord, TurnFeatures

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
async def test_router_state_round_trip(repo: Repository) -> None:
    uid = await repo.create_user_session("h")
    info = await repo.get_session("h")
    assert info is not None
    assert info.router_state == "{}"
    await repo.set_router_state(uid, "h", '{"current": "cbt"}')
    info = await repo.get_session("h")
    assert info is not None
    assert info.router_state == '{"current": "cbt"}'


@pytest.mark.anyio
async def test_router_state_is_scoped_to_the_user(repo: Repository) -> None:
    await repo.create_user_session("h1")
    other = await repo.create_user_session("h2")
    with pytest.raises(StorageError):
        await repo.set_router_state(other, "h1", '{"current": "cbt"}')
    info = await repo.get_session("h1")
    assert info is not None
    assert info.router_state == "{}"


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


# --- language features (Phase 8) ------------------------------------------------------------


def _features(**kw: Any) -> TurnFeatures:
    base = TurnFeatures(valence=0.1, sadness=0.0, anxiety=0.2, anger=0.0, shame=0.0,
                        loneliness=0.0, fp_pronoun_rate=0.25, absolutist_rate=0.0,
                        msg_length=4, reply_latency_s=None, hour_of_day=10)  # fmt: skip
    return replace(base, **kw)


@pytest.mark.anyio
async def test_signals_round_trip_in_order_and_per_user(repo: Repository) -> None:
    a = await repo.create_user_session("a")
    b = await repo.create_user_session("b")
    first, second = _features(valence=-0.4), _features(valence=0.3, reply_latency_s=12.5)
    await repo.append_signals(a, "a", first)
    await repo.append_signals(a, "a", second)
    await repo.append_signals(b, "b", _features())
    records = await repo.list_signals(a)
    assert [r.features for r in records] == [first, second]
    assert {r.session_hash for r in records} == {"a"}
    assert records[0].created_at <= records[1].created_at
    assert len(await repo.list_signals(b)) == 1


@pytest.mark.anyio
async def test_signals_for_another_users_session_are_rejected(repo: Repository) -> None:
    a = await repo.create_user_session("a")
    await repo.create_user_session("b")
    with pytest.raises(StorageError):
        await repo.append_signals(a, "b", _features())
    assert await repo.list_signals(a) == []


# --- explanations (Phase 9) -----------------------------------------------------------------


@pytest.mark.anyio
async def test_explanation_round_trip_and_scoping(repo: Repository) -> None:
    a = await repo.create_user_session("a")
    b = await repo.create_user_session("b")
    body = '{"status":"ok"}'
    await repo.append_turn(a, "a", turn_id="u1", role="user", content="hi", mode=None,
                           trace_json=None)  # fmt: skip
    await repo.append_turn(a, "a", turn_id="r1", role="assistant", content="hello",
                           mode="companion", trace_json=None, explanation_json=body)  # fmt: skip
    assert await repo.get_explanation(a, "r1") == body
    assert await repo.get_explanation(b, "r1") is None
    assert await repo.get_explanation(a, "u1") is None
    assert await repo.get_explanation(a, "missing") is None
    turns = await repo.recent_turns(a, "a", 10)
    assert [t.has_explanation for t in turns] == [False, True]


@pytest.mark.anyio
async def test_explanation_must_be_json(repo: Repository) -> None:
    a = await repo.create_user_session("a")
    with pytest.raises(StorageError):
        await repo.append_turn(a, "a", turn_id="r1", role="assistant", content="hello",
                               mode="companion", trace_json=None,
                               explanation_json="not json")  # fmt: skip
    assert await repo.recent_turns(a, "a", 10) == []


# --- consent, export and delete (Phase 10) --------------------------------------------------

MARKER = "zqx-marker lantern"


async def _full_user(repo: Repository, session: str = "a") -> str:
    """A user with a row in every kind of record OASIS stores."""
    uid = await repo.create_user_session(session)
    await repo.set_consent(uid, "1")
    await _append(repo, uid, session, f"{session}1", MARKER)
    await repo.append_turn(uid, session, turn_id=f"{session}2", role="assistant", content="reply",
                           mode="companion", trace_json='{"x":1}',
                           explanation_json='{"status":"ok"}')  # fmt: skip
    await repo.set_router_state(uid, session, '{"current":"cbt"}')
    await repo.set_post_crisis(uid, session, True)
    await repo.append_audit(uid, "crisis_handoff", '{"tiers":["passive"]}')
    await repo.save_assessment(uid, _assessment("a-" + session, answers=(1, 2)))
    await repo.append_signals(uid, session, _features(valence=-0.5))
    return uid


@pytest.mark.anyio
async def test_consent_round_trip_and_replace(repo: Repository) -> None:
    a = await repo.create_user_session("a")
    b = await repo.create_user_session("b")
    assert (await repo.get_session("a")).consent_version is None  # type: ignore[union-attr]
    await repo.set_consent(a, "1")
    await repo.set_consent(a, "2")  # a newer notice replaces the older consent
    assert (await repo.get_session("a")).consent_version == "2"  # type: ignore[union-attr]
    assert (await repo.get_session("b")).consent_version is None  # type: ignore[union-attr]
    assert b != a


EXPECTED_TABLES = {"users", "sessions", "turns", "audit_log", "assessments",
                   "assessment_answers", "turn_signals", "consent"}  # fmt: skip


@pytest.mark.anyio
async def test_export_holds_every_record_of_the_user_and_nothing_else(repo: Repository) -> None:
    uid = await _full_user(repo, "a")
    await _full_user(repo, "b")
    tables = await repo.export_user(uid)
    assert set(tables) == EXPECTED_TABLES
    assert all(r["user_id"] == uid for rows in tables.values() for r in rows)
    assert [(t["turn_id"], t["role"], t["content"]) for t in tables["turns"]] == [
        ("a1", "user", MARKER), ("a2", "assistant", "reply")]  # fmt: skip
    assert tables["turns"][1]["explanation"] == '{"status":"ok"}'
    assert tables["turns"][1]["trace"] == '{"x":1}'
    session = tables["sessions"][0]
    assert (session["post_crisis"], session["router_state"]) == (1, '{"current":"cbt"}')
    assert [a["detail"] for a in tables["audit_log"]] == ['{"tiers":["passive"]}']
    assert [a["value"] for a in tables["assessment_answers"]] == [1, 2]
    assert json.loads(tables["turn_signals"][0]["features"])["valence"] == -0.5
    assert [c["disclosure_version"] for c in tables["consent"]] == ["1"]
    json.dumps(tables)  # plain JSON, ready to download


@pytest.mark.anyio
async def test_both_backends_export_the_same_shape(tmp_path: Path) -> None:
    shapes = []
    for make in BACKENDS.values():
        r = make(tmp_path)
        uid = await _full_user(r)
        tables = await r.export_user(uid)
        shapes.append({t: (len(rows), sorted(rows[0])) for t, rows in tables.items()})
        await r.close()
    assert shapes[0] == shapes[1]


@pytest.mark.anyio
async def test_delete_removes_every_record_of_the_user_only(repo: Repository) -> None:
    uid = await _full_user(repo, "a")
    other = await _full_user(repo, "b")
    await repo.delete_user(uid)
    assert await repo.get_session("a") is None
    assert all(rows == [] for rows in (await repo.export_user(uid)).values())
    assert await repo.recent_turns(uid, "a", 10) == []
    assert await repo.get_explanation(uid, "a2") is None
    kept = await repo.export_user(other)
    assert len(kept["turns"]) == 2
    assert (await repo.get_session("b")) is not None


@pytest.mark.anyio
async def test_deleting_an_unknown_user_is_a_no_op(repo: Repository) -> None:
    await repo.create_user_session("a")
    await repo.delete_user("nobody")
    assert await repo.get_session("a") is not None
