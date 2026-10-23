"""Privacy and autonomy (Phase 10): consent gate, ephemeral storage, disclosure content."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from oasis.storage.split import SplitRepository

from oasis.api.pages import load_disclosure, parse_disclosure, render_onboarding
from oasis.core.engine import ChatEngine, ConsentRequired
from oasis.llm.fake import FakeLLM
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import StorageUnavailable
from oasis.storage.sqlite import SQLiteRepository

GATE = RuleBasedSafetyGate(load_ruleset())
VERSION = "7"


def _engine(settings: Settings, repo: Any = None) -> ChatEngine:
    return ChatEngine(safety=GATE, llm=FakeLLM(), repo=repo or MemoryRepository(),
                      settings=settings, consent_version=VERSION)  # fmt: skip


# --- consent gate (FR-PRV-1, architecture §3.3) --------------------------------------------


@pytest.mark.anyio
async def test_no_reply_before_consent(settings: Settings) -> None:
    engine = _engine(settings)
    uid = await engine.repo.create_user_session("h")
    with pytest.raises(ConsentRequired):
        await engine.handle_turn("h", "hello")
    assert await engine.repo.recent_turns(uid, "h", 10) == []  # nothing stored either


@pytest.mark.anyio
async def test_a_crisis_is_answered_before_consent(settings: Settings) -> None:
    engine = _engine(settings)
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", "I want to kill myself")
    assert (result.mode, result.reply) == ("crisis", HANDOFF_REPLY)


@pytest.mark.anyio
async def test_consent_to_the_current_notice_opens_the_chat(settings: Settings) -> None:
    engine = _engine(settings)
    uid = await engine.repo.create_user_session("h")
    await engine.repo.set_consent(uid, VERSION)
    result = await engine.handle_turn("h", "hello")
    assert result.mode == "companion"


@pytest.mark.anyio
async def test_consent_to_an_older_notice_is_not_enough(settings: Settings) -> None:
    engine = _engine(settings)
    uid = await engine.repo.create_user_session("h")
    await engine.repo.set_consent(uid, "6")
    with pytest.raises(ConsentRequired):
        await engine.handle_turn("h", "hello")


class DownAfterConsent(MemoryRepository):
    down = False

    async def get_session(self, session_hash: str) -> Any:
        if self.down:
            raise StorageUnavailable
        return await super().get_session(session_hash)


@pytest.mark.anyio
async def test_remembered_consent_survives_a_storage_outage(settings: Settings) -> None:
    repo = DownAfterConsent()
    engine = _engine(settings, repo)
    uid = await repo.create_user_session("h")
    await repo.set_consent(uid, VERSION)
    engine.remember_consent("h")
    repo.down = True
    result = await engine.handle_turn("h", "hello")
    assert "storage.down" in result.degraded
    assert result.reply


@pytest.mark.anyio
async def test_unknown_consent_during_an_outage_is_refused(settings: Settings) -> None:
    repo = DownAfterConsent()
    engine = _engine(settings, repo)
    await repo.create_user_session("h")
    repo.down = True
    with pytest.raises(ConsentRequired):
        await engine.handle_turn("h", "hello")
    assert (await engine.handle_turn("h", "I want to kill myself")).mode == "crisis"


@pytest.mark.anyio
async def test_forget_drops_the_remembered_consent(settings: Settings) -> None:
    """After an account is deleted nothing about its session stays in memory either."""
    repo = DownAfterConsent()
    engine = _engine(settings, repo)
    await repo.create_user_session("h")
    engine.remember_consent("h")
    engine.forget("h")
    repo.down = True
    with pytest.raises(ConsentRequired):
        await engine.handle_turn("h", "hello")


# --- ephemeral storage (FR-PRV-4, design §11.1) --------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.anyio
async def test_idle_ephemeral_sessions_expire() -> None:
    clock = Clock()
    repo = MemoryRepository(idle_timeout_s=7200, clock=clock)
    old = await repo.create_user_session("old")
    await repo.append_turn(old, "old", turn_id="t", role="user", content="x", mode=None,
                           trace_json=None)  # fmt: skip
    clock.t += 3600
    await repo.create_user_session("new")
    await repo.get_session("new")
    clock.t += 3601  # "old" idle for 2 h + 1 s; "new" only 1 h
    assert await repo.get_session("new") is not None
    assert await repo.get_session("old") is None
    assert all(rows == [] for rows in (await repo.export_user(old)).values())


@pytest.mark.anyio
async def test_activity_keeps_an_ephemeral_session_alive() -> None:
    clock = Clock()
    repo = MemoryRepository(idle_timeout_s=7200, clock=clock)
    uid = await repo.create_user_session("h")
    for _ in range(3):
        clock.t += 7000
        assert await repo.get_session("h") is not None
        await repo.append_turn(uid, "h", turn_id=f"t{clock.t}", role="user", content="x",
                               mode=None, trace_json=None)  # fmt: skip


@pytest.mark.anyio
async def test_memory_storage_never_expires_by_default() -> None:
    clock = Clock()
    repo = MemoryRepository(clock=clock)
    await repo.create_user_session("h")
    clock.t += 10 * 24 * 3600
    assert await repo.get_session("h") is not None


@pytest.mark.anyio
async def test_split_storage_keeps_ephemeral_sessions_off_disk(tmp_path: Path) -> None:
    saved = SQLiteRepository(tmp_path / "s.db")
    split = SplitRepository(saved, MemoryRepository())
    kept = await split.create_user_session("kept")
    temp = await split.create_user_session("temp", ephemeral=True)
    for uid, session in ((kept, "kept"), (temp, "temp")):
        await split.set_consent(uid, "1")
        await split.append_turn(uid, session, turn_id=session, role="user", content=session,
                                mode=None, trace_json=None)  # fmt: skip
    assert (split.is_ephemeral("kept"), split.is_ephemeral("temp")) == (False, True)
    assert await saved.get_session("temp") is None  # never reached SQLite
    assert [t.content for t in await split.recent_turns(temp, "temp", 5)] == ["temp"]
    assert [t.content for t in await saved.recent_turns(kept, "kept", 5)] == ["kept"]
    assert (await split.get_session("temp")).consent_version == "1"  # type: ignore[union-attr]
    await split.delete_user(temp)
    assert await split.get_session("temp") is None
    assert await split.get_session("kept") is not None
    await split.close()


@pytest.mark.anyio
async def test_ephemeral_sessions_work_while_the_database_is_down(tmp_path: Path) -> None:
    class Dead(MemoryRepository):
        async def get_session(self, session_hash: str) -> Any:
            raise StorageUnavailable

    split = SplitRepository(Dead(), MemoryRepository())
    await split.create_user_session("temp", ephemeral=True)
    assert await split.get_session("temp") is not None


# --- disclosure (FR-PRV-1, PRD L5) ---------------------------------------------------------


def test_disclosure_covers_what_the_policy_must_say() -> None:
    d = load_disclosure()
    assert d.version
    text = " ".join(" ".join(s.paragraphs) for s in d.sections).lower()
    for must in ("not a diagnosis", "emergency", "crisis", "export", "delete",
                 "without saving", "this computer", "no one else"):  # fmt: skip
        assert must in text, must
    assert "http" not in text  # no external links (rules F1)


@pytest.mark.parametrize("change", [
    lambda r: r.pop("version"),
    lambda r: r.update(review_status="approved"),
    lambda r: r.update(sections=[]),
    lambda r: r["sections"][0].update(paragraphs=[]),
], ids=["no_version", "approved_status", "no_sections", "empty_section"])  # fmt: skip
def test_an_invalid_disclosure_is_rejected(change: Any) -> None:
    from oasis.content import load_yaml

    raw = load_yaml("privacy", "disclosure.yaml")
    change(raw)
    with pytest.raises(ValueError):  # noqa: PT011 - any validation message
        parse_disclosure(raw)


def test_onboarding_is_rendered_escaped_with_its_version() -> None:
    raw = {"version": "9", "review_status": "needs_clinician_review", "title": "Before <you> start",
           "sections": [{"heading": "A & B", "paragraphs": ["<script>x</script>"]}]}  # fmt: skip
    html = render_onboarding(parse_disclosure(raw))
    assert 'data-version="9"' in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html
