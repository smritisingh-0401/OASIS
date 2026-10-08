"""Chat engine: stage ordering, shortcut paths and every fallback (architecture §3)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import pytest

from oasis.core.engine import CRISIS_PLACEHOLDER, ChatEngine, InvalidSession
from oasis.core.templates import TEMPLATES
from oasis.llm.client import LLMFailure
from oasis.llm.fake import FakeLLM
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import StorageBusy, StorageUnavailable
from oasis.types import (
    ChatMessage,
    ConversationState,
    GuardVerdict,
    Plan,
    SafetyVerdict,
    TurnRecord,
)


class RecordingGate:
    def __init__(self, events: list[str], crisis: bool = False) -> None:
        self.events = events
        self.crisis = crisis

    def check(self, text: str) -> SafetyVerdict:
        self.events.append("safety")
        return SafetyVerdict(
            is_crisis=self.crisis, tiers=frozenset({"explicit"}) if self.crisis else frozenset()
        )


class ExplodingGate:
    def check(self, text: str) -> SafetyVerdict:
        raise RuntimeError("boom")


class RecordingRepo(MemoryRepository):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    async def get_session(self, session_hash: str) -> Any:
        self.events.append("storage")
        return await super().get_session(session_hash)


class UntouchableRepo(MemoryRepository):
    """Fails the test if the engine touches storage."""

    async def get_session(self, session_hash: str) -> Any:
        raise AssertionError("storage touched")

    async def recent_turns(self, user_id: str, session_hash: str, limit: int) -> list[TurnRecord]:
        raise AssertionError("storage touched")

    async def append_turn(self, *args: Any, **kwargs: Any) -> TurnRecord:
        raise AssertionError("storage touched")


class UntouchableLLM(FakeLLM):
    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        raise AssertionError("LLM called")


class BrokenRepo(MemoryRepository):
    def __init__(self, fail_on: str, exc: type[Exception] = StorageUnavailable) -> None:
        super().__init__()
        self.fail_on = fail_on
        self.exc = exc

    async def get_session(self, session_hash: str) -> Any:
        if self.fail_on == "load":
            raise self.exc()
        return await super().get_session(session_hash)

    async def append_turn(self, *args: Any, **kwargs: Any) -> TurnRecord:
        if self.fail_on == "record":
            raise self.exc()
        return await super().append_turn(*args, **kwargs)


GATE = RuleBasedSafetyGate(load_ruleset())


def _engine(settings: Settings, **overrides: Any) -> ChatEngine:
    parts: dict[str, Any] = {
        "safety": GATE,
        "llm": FakeLLM(),
        "repo": MemoryRepository(),
        "settings": settings,
    }
    parts.update(overrides)
    return ChatEngine(**parts)


async def _session(engine: ChatEngine, session_hash: str = "h") -> str:
    return await engine.repo.create_user_session(session_hash)


# --- normal path -----------------------------------------------------------------


@pytest.mark.anyio
async def test_normal_turn_is_generated_and_recorded(settings: Settings) -> None:
    llm = FakeLLM(replies=["How are you feeling about it?"])
    engine = _engine(settings, llm=llm)
    uid = await _session(engine)

    result = await engine.handle_turn("h", "I had a long day")

    assert result.reply == "How are you feeling about it?"
    assert (result.mode, result.templated, result.persisted) == ("companion", False, True)
    turns = await engine.repo.recent_turns(uid, "h", limit=10)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "I had a long day"),
        ("assistant", "How are you feeling about it?"),
    ]
    assert turns[1].turn_id == result.turn_id


@pytest.mark.anyio
async def test_history_reaches_the_prompt(settings: Settings) -> None:
    llm = FakeLLM()
    engine = _engine(settings, llm=llm)
    await _session(engine)
    await engine.handle_turn("h", "first message")
    await engine.handle_turn("h", "second message")
    contents = [m.content for m in llm.last_messages]
    assert "first message" in contents
    assert contents[-1] == "second message"


@pytest.mark.anyio
async def test_unknown_session_is_rejected(settings: Settings) -> None:
    with pytest.raises(InvalidSession):
        await _engine(settings).handle_turn("never-created", "hello")


# --- safety ordering (rules S1-S5) ------------------------------------------------


@pytest.mark.anyio
async def test_safety_runs_before_any_storage_access(settings: Settings) -> None:
    events: list[str] = []
    engine = _engine(settings, safety=RecordingGate(events), repo=RecordingRepo(events))
    await _session(engine)
    await engine.handle_turn("h", "hello")
    assert events[0] == "safety"
    assert "storage" in events


@pytest.mark.anyio
async def test_crisis_makes_zero_llm_and_zero_storage_calls(settings: Settings) -> None:
    engine = _engine(
        settings,
        safety=RecordingGate([], crisis=True),
        llm=UntouchableLLM(),
        repo=UntouchableRepo(),
    )
    result = await engine.handle_turn("any-or-unknown-session", "text")
    assert result.reply == HANDOFF_REPLY
    assert (result.mode, result.templated, result.persisted) == ("crisis", True, False)


@pytest.mark.anyio
async def test_safety_error_fails_closed_into_handoff(settings: Settings) -> None:
    engine = _engine(settings, safety=ExplodingGate(), llm=UntouchableLLM(), repo=UntouchableRepo())
    result = await engine.handle_turn("h", "text")
    assert result.mode == "crisis"
    assert result.reply == HANDOFF_REPLY


# --- LLM failures (architecture shortcut P3) ---------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("reason", "template"),
    [
        ("down", "llm_unavailable"),
        ("timeout", "llm_unavailable"),
        ("http_error", "llm_unavailable"),
        ("bad_response", "llm_unavailable"),
        ("busy", "busy"),
    ],
)
async def test_llm_failure_returns_template(settings: Settings, reason: str, template: str) -> None:
    engine = _engine(settings, llm=FakeLLM(fail=reason))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert result.templated is True
    assert result.reply == TEMPLATES[template]
    assert result.fallback_reason == f"llm.{reason}"
    assert result.persisted is True


@pytest.mark.anyio
async def test_reasoning_only_output_never_reaches_user(settings: Settings) -> None:
    engine = _engine(settings, llm=FakeLLM(replies=["<think>SECRET plan</think>"]))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert "SECRET" not in result.reply
    assert result.fallback_reason == "llm.empty"


@pytest.mark.anyio
async def test_unexpected_llm_exception_is_not_swallowed_by_engine(settings: Settings) -> None:
    class Weird(FakeLLM):
        async def generate(
            self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
        ) -> str:
            raise ValueError("not an LLMFailure")

    engine = _engine(settings, llm=Weird())
    await _session(engine)
    # The API layer turns unexpected errors into a templated reply (tested there).
    with pytest.raises(ValueError, match="not an LLMFailure"):
        await engine.handle_turn("h", "hello")


@pytest.mark.anyio
async def test_slow_llm_is_cut_off_by_the_deadline(settings: Settings) -> None:
    fast = settings.model_copy(update={"request_timeout_s": 0.5, "llm_generate_timeout_s": 10})
    engine = _engine(fast, llm=FakeLLM(delay_s=10))
    await _session(engine)
    start = time.monotonic()
    result = await engine.handle_turn("h", "hello")
    assert time.monotonic() - start < 1.0
    assert result.fallback_reason == "llm.timeout"
    assert result.templated is True


# --- guard flow (architecture shortcut P4) ----------------------------------------


def _guard_rejecting(times: int) -> Any:
    state = {"n": 0}

    def guard(draft: str, plan: Plan) -> GuardVerdict:
        state["n"] += 1
        return GuardVerdict(ok=state["n"] > times, reasons=("G-AGREE",))

    return guard


@pytest.mark.anyio
async def test_guard_rejection_then_retry_succeeds(settings: Settings) -> None:
    llm = FakeLLM(replies=["bad draft", "good draft"])
    engine = _engine(settings, llm=llm, guard=_guard_rejecting(1))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert result.reply == "good draft"
    assert llm.calls == 2
    assert "G-AGREE" in llm.last_messages[0].content


@pytest.mark.anyio
async def test_guard_rejecting_twice_uses_socratic_fallback(settings: Settings) -> None:
    llm = FakeLLM()
    engine = _engine(settings, llm=llm, guard=_guard_rejecting(99))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert llm.calls == 2
    assert result.reply == TEMPLATES["guard_fallback"]
    assert result.fallback_reason == "guard.fallback"


@pytest.mark.anyio
async def test_guard_retry_skipped_when_budget_is_short(settings: Settings) -> None:
    tight = settings.model_copy(update={"guard_retry_min_budget_s": 1000})
    llm = FakeLLM()
    engine = _engine(tight, llm=llm, guard=_guard_rejecting(99))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert llm.calls == 1
    assert result.fallback_reason == "guard.no_budget"


# --- planner hook -----------------------------------------------------------------


@pytest.mark.anyio
async def test_templated_plan_skips_the_llm(settings: Settings) -> None:
    def planner(message: str, state: ConversationState) -> Plan:
        return Plan(mode="assessment", templated=True, template_id="llm_unavailable")

    engine = _engine(settings, llm=UntouchableLLM(), planner=planner)
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert (result.mode, result.templated) == ("assessment", True)


@pytest.mark.anyio
async def test_planner_error_falls_back_to_template(settings: Settings) -> None:
    def planner(message: str, state: ConversationState) -> Plan:
        raise RuntimeError("planner bug")

    engine = _engine(settings, llm=UntouchableLLM(), planner=planner)
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert result.templated is True
    assert "planner.error" in result.degraded


# --- storage failures -------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exc", "code"), [(StorageUnavailable, "storage.down"), (StorageBusy, "storage.busy")]
)
async def test_storage_failure_on_load_still_replies(
    settings: Settings, exc: type[Exception], code: str
) -> None:
    engine = _engine(settings, repo=BrokenRepo("load", exc))
    result = await engine.handle_turn("h", "hello")
    assert result.reply
    assert result.persisted is False
    assert code in result.degraded


@pytest.mark.anyio
async def test_storage_failure_on_record_still_replies(settings: Settings) -> None:
    engine = _engine(settings, repo=BrokenRepo("record"))
    await _session(engine)
    result = await engine.handle_turn("h", "hello")
    assert result.reply
    assert result.persisted is False
    assert "storage.down" in result.degraded


def test_llm_failure_carries_reason() -> None:
    assert LLMFailure("down").reason == "down"


# --- post-crisis mode and the crisis audit (rules S2, S10) ---------------------------


@pytest.mark.anyio
async def test_after_a_crisis_the_bot_stays_in_minimal_supportive_mode(settings: Settings) -> None:
    llm = FakeLLM()
    engine = _engine(settings, llm=llm)
    await _session(engine)

    crisis = await engine.handle_turn("h", "I want to kill myself")
    assert crisis.mode == "crisis"
    later = await engine.handle_turn("h", "ok")
    assert (later.mode, later.reply) == ("post_crisis", TEMPLATES["post_crisis"])
    assert llm.calls == 0


@pytest.mark.anyio
async def test_every_post_crisis_message_still_passes_the_safety_gate(settings: Settings) -> None:
    engine = _engine(settings)
    await _session(engine)
    await engine.handle_turn("h", "I want to die")
    again = await engine.handle_turn("h", "I still want to die")
    assert again.mode == "crisis"


@pytest.mark.anyio
async def test_user_can_choose_to_continue_after_a_crisis(settings: Settings) -> None:
    llm = FakeLLM(replies=["I'm glad you're still here. What's on your mind?"])
    engine = _engine(settings, llm=llm)
    uid = await _session(engine)
    crisis = await engine.handle_turn("h", "I want to die")
    await engine.record_crisis("h", crisis.verdict)

    resumed = await engine.handle_turn("h", "I'd like to keep talking.")
    assert resumed.mode == "companion"
    assert llm.calls == 1
    assert (await engine.repo.get_session("h")).post_crisis is False  # type: ignore[union-attr]
    normal = await engine.handle_turn("h", "work was hard today")
    assert normal.mode == "companion"
    assert uid


@pytest.mark.anyio
async def test_post_crisis_mode_survives_storage_failure(settings: Settings) -> None:
    repo = BrokenRepo("none")
    engine = _engine(settings, repo=repo)
    await _session(engine)
    await engine.handle_turn("h", "I want to die")
    repo.fail_on = "load"
    later = await engine.handle_turn("h", "hello")
    assert later.mode == "post_crisis"


@pytest.mark.anyio
async def test_record_crisis_writes_audit_flag_and_placeholder_without_text(
    settings: Settings,
) -> None:
    engine = _engine(settings)
    uid = await _session(engine)
    crisis = await engine.handle_turn("h", "MARKER-551 I want to kill myself")
    await engine.record_crisis("h", crisis.verdict)

    session = await engine.repo.get_session("h")
    assert session is not None
    assert session.post_crisis is True
    audits = await engine.repo.list_audit(uid)
    assert [a.event for a in audits] == ["crisis_handoff"]
    assert "explicit.kill_self" in audits[0].detail
    assert "MARKER-551" not in audits[0].detail
    turns = await engine.repo.recent_turns(uid, "h", limit=10)
    assert [(t.role, t.content) for t in turns] == [("placeholder", CRISIS_PLACEHOLDER)]


@pytest.mark.anyio
async def test_record_crisis_swallows_storage_errors(settings: Settings) -> None:
    engine = _engine(settings, repo=BrokenRepo("load"))
    verdict = SafetyVerdict(is_crisis=True, tiers=frozenset({"explicit"}))
    await engine.record_crisis("h", verdict)  # must not raise


@pytest.mark.anyio
async def test_record_crisis_ignores_unknown_sessions(settings: Settings) -> None:
    engine = _engine(settings)
    await engine.record_crisis("nobody", SafetyVerdict(is_crisis=True))
