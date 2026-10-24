"""Style profile (Phase 11): framing only, never routing, triggers or safety (FR-CUL-1..3)."""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
from collections.abc import Sequence
from pathlib import Path
from typing import Any, get_args

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from oasis.core.engine import ChatEngine
from oasis.explain.builder import build as build_explanation
from oasis.guard.checks import check as check_reply
from oasis.llm.fake import FakeLLM
from oasis.llm.prompt import build_messages
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import UserSettings
from oasis.style.framing import STYLE_MARK, framing, parse_framing
from oasis.style.suggest import hedged, suggest
from oasis.types import ChatMessage, Directness, Formality, GuardVerdict, Plan, StyleProfile

STYLES = [StyleProfile(d, f) for d, f in itertools.product(get_args(Directness),
                                                         get_args(Formality))]  # fmt: skip
PLAN = Plan(mode="companion", constraints=("one_question",))


def _system(style: StyleProfile, plan: Plan = PLAN) -> str:
    return build_messages(dataclasses.replace(plan, style=style), [], "hi", history_turns=6)[
        0
    ].content


# --- framing --------------------------------------------------------------------------------


def test_every_style_gives_a_different_prompt() -> None:
    prompts = {s: _system(s) for s in STYLES}
    assert len(set(prompts.values())) == len(STYLES) == 9


def test_the_default_style_leaves_the_prompt_as_it_was() -> None:
    """A user who never opens Settings gets the prompt every earlier phase was tested with."""
    assert STYLE_MARK not in _system(StyleProfile())
    assert framing(StyleProfile()) == ""


def test_framing_sits_before_the_plan_and_changes_nothing_else() -> None:
    base = _system(StyleProfile())
    for style in STYLES[1:] if STYLES[0] == StyleProfile() else STYLES:
        text = _system(style)
        lines = text.split("\n")
        styled = [ln for ln in lines if ln.startswith(STYLE_MARK)]
        assert len(styled) <= 1
        assert lines.index("PLAN:") > (lines.index(styled[0]) if styled else -1)
        assert "\n".join(ln for ln in lines if not ln.startswith(STYLE_MARK)) == base


@pytest.mark.parametrize("mode", ["companion", "cbt", "dbt", "psychoed"])
def test_indirect_and_formal_reach_every_generated_mode(mode: str) -> None:
    plan = Plan(mode=mode, snippet="An item." if mode == "psychoed" else None)  # type: ignore[arg-type]
    text = _system(StyleProfile("indirect", "formal"), plan)
    assert framing(StyleProfile("indirect", "formal")) in text


def test_an_exercise_step_keeps_the_style_too() -> None:
    plan = Plan(mode="grounding", constraints=("ack_only",), snippet="Name five things.",
                style=StyleProfile("direct", "casual"))  # fmt: skip
    system = build_messages(plan, [], "ok", history_turns=6)[0].content
    assert framing(plan.style) in system
    assert "Name five things." not in system


def test_the_framing_file_needs_every_value_and_a_review_flag() -> None:
    good: dict[str, Any] = {
        "version": "1",
        "review_status": "needs_clinician_review",
        "directness": {"direct": "a", "balanced": "", "indirect": "b"},
        "formality": {"casual": "c", "neutral": "", "formal": "d"},
        "suggest": {"window": 3, "min_hedged": 2, "hedges": ["maybe"]},
    }
    parse_framing(good)
    for broken in (
        {**good, "review_status": "ok"},
        {**good, "directness": {"direct": "a", "balanced": ""}},
        {**good, "formality": {**good["formality"], "neutral": "x"}},  # the default adds text
        {**good, "suggest": {**good["suggest"], "min_hedged": 4}},  # more than the window
        {**good, "suggest": {**good["suggest"], "hedges": []}},
    ):
        with pytest.raises(ValueError, match=r"style|framing"):
            parse_framing(broken)


# --- the indirect-phrasing suggestion (FR-CUL-2) --------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "maybe it's nothing",
        "I guess I'm a bit tired",
        "it's sort of hard to say",
        "I\u2019m not sure it matters",  # a curly apostrophe
        "Perhaps I overreacted",
    ],
)
def test_hedged_phrasing_is_noticed(message: str) -> None:
    assert hedged(message)


@pytest.mark.parametrize("message", ["I am tired.", "My boss yelled at me", "hi", "May I ask?",
                                     "I guessed the answer"])  # fmt: skip
def test_plain_phrasing_is_not(message: str) -> None:
    assert not hedged(message)


def test_one_hedge_is_not_enough_to_suggest() -> None:
    assert not suggest("maybe it's nothing", [], StyleProfile())
    assert not suggest("maybe it's nothing", ["I am tired", "work was long"], StyleProfile())


def test_two_hedged_messages_out_of_three_suggest_the_indirect_style() -> None:
    earlier = ["I guess work was long", "fine"]
    assert suggest("maybe it's nothing", earlier, StyleProfile())
    assert suggest("maybe it's nothing", earlier, StyleProfile("direct", "formal"))
    # Only the latest messages count, and this one must be hedged itself.
    assert not suggest("maybe it's nothing", ["I guess so", "fine", "ok", "sure"], StyleProfile())
    assert not suggest("I am tired", ["I guess so", "maybe"], StyleProfile())


def test_no_suggestion_when_the_style_is_already_indirect() -> None:
    assert not suggest("maybe it's nothing", ["I guess so"], StyleProfile("indirect"))


# --- engine: style is read, never written, and changes framing only -------------------------

GATE = RuleBasedSafetyGate(load_ruleset())


class RecordingLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[list[ChatMessage]] = []

    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        self.prompts.append(list(messages))
        return await super().generate(messages, max_tokens=max_tokens, timeout_s=timeout_s)


class NoWritesRepo(MemoryRepository):
    async def set_settings(self, user_id: str, value: UserSettings) -> None:
        raise AssertionError("the engine must never change the settings")


def _engine(
    settings: Settings, llm: FakeLLM, repo: MemoryRepository, seen: list[Any]
) -> ChatEngine:
    def guard(text: str, plan: Plan) -> GuardVerdict:
        seen.append(dataclasses.replace(plan, style=StyleProfile()))
        return check_reply(text, plan)

    def explainer(*args: Any, **kwargs: Any) -> str:
        out = build_explanation(*args, **kwargs)
        seen.append(out)
        return out

    return ChatEngine(safety=GATE, llm=llm, repo=repo, settings=settings, guard=guard,
                      explainer=explainer)  # fmt: skip


@pytest.mark.anyio
async def test_the_engine_reads_the_users_style_into_the_prompt(settings: Settings) -> None:
    llm, repo = RecordingLLM(), MemoryRepository()
    engine = _engine(settings, llm, repo, [])
    uid = await repo.create_user_session("h")
    await repo.set_settings(uid, UserSettings(StyleProfile("indirect", "casual"), "IN"))
    await engine.handle_turn("h", "work was long today")
    system = llm.prompts[-1][0].content
    assert framing(StyleProfile("indirect", "casual")) in system
    # The country is for the help card only.
    assert "India" not in system
    assert "IN" not in system.split()


@pytest.mark.anyio
async def test_a_suggestion_never_changes_the_profile(settings: Settings) -> None:
    repo = NoWritesRepo()
    engine = _engine(settings, FakeLLM(), repo, [])
    uid = await repo.create_user_session("h")
    results = [await engine.handle_turn("h", m) for m in
               ("I guess work was long", "maybe it's nothing", "sort of, I suppose")]  # fmt: skip
    assert [r.style_suggestion for r in results] == [False, True, True]
    assert await repo.get_settings(uid) == UserSettings()


@pytest.mark.anyio
async def test_no_suggestion_on_a_button_press(settings: Settings) -> None:
    from oasis.types import ExerciseAction

    # A button label is not their own words, even when the reply to it is generated.
    engine = _engine(settings, FakeLLM(), MemoryRepository(), [])
    engine.planner = lambda message, state, action: Plan(mode="companion")
    await engine.repo.create_user_session("h")
    await engine.handle_turn("h", "I guess work was long")
    pressed = await engine.handle_turn("h", "maybe", ExerciseAction("stop"))
    typed = await engine.handle_turn("h", "maybe")
    assert (pressed.templated, pressed.style_suggestion) == (False, False)
    assert typed.style_suggestion is True


@pytest.mark.anyio
async def test_storage_down_means_the_default_style(settings: Settings) -> None:
    class SettingsDown(MemoryRepository):
        async def get_settings(self, user_id: str) -> UserSettings:
            from oasis.storage.repository import StorageUnavailable

            raise StorageUnavailable

    llm = RecordingLLM()
    engine = _engine(settings, llm, SettingsDown(), [])
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", "work was long today")
    assert STYLE_MARK not in llm.prompts[-1][0].content
    assert "storage.down" in result.degraded
    assert not result.templated


# Messages that exercise every decision: crisis, screening trigger, psychoeducation, thinking
# traps, anger, acute overwhelm, the continue phrase, hedging and small talk.
POOL = [
    "I want to kill myself",
    "I don't want to be here anymore",
    "I've been feeling down and hopeless for weeks",
    "nothing feels enjoyable and I can't sleep",
    "is it normal to feel this way? what's wrong with me",
    "I always mess everything up, I'm a complete failure",
    "I'm so angry I can't control it, I'm going to explode",
    "I can't breathe, everything is too much, I'm panicking",
    "I'd like to keep talking.",
    "maybe it's nothing, I guess",
    "hi",
    "work was long today",
    "I keep worrying about everything",
]


async def _run(messages: Sequence[str], style: StyleProfile, settings: Settings) -> list[Any]:
    llm, repo, seen = RecordingLLM(), MemoryRepository(), []
    engine = _engine(settings, llm, repo, seen)
    uid = await repo.create_user_session("h")
    await repo.set_settings(uid, UserSettings(style))
    out: list[Any] = []
    for m in messages:
        r = await engine.handle_turn("h", m)
        out.append((r.reply, r.mode, r.templated, r.verdict, r.card, r.exercise_card, r.preface,
                    r.persisted, r.degraded, r.fallback_reason))  # fmt: skip
    # The prompts may differ in the style line only.
    for prompt in llm.prompts:
        system = "\n".join(ln for ln in prompt[0].content.split("\n")
                           if not ln.startswith(STYLE_MARK))  # fmt: skip
        out.append([system, *[(m.role, m.content) for m in prompt[1:]]])
    return out + seen


@hyp_settings(max_examples=25, deadline=None, derandomize=True)
@given(st.lists(st.sampled_from(POOL), min_size=1, max_size=6))
def test_decisions_are_identical_under_every_style(messages: list[str]) -> None:
    """Crisis verdicts, modes, screening offers, exercise offers, plans, replies and
    explanations are the same for all nine styles (PRD L3b, FR-CUL-3)."""
    cfg = Settings(_env_file=None, llm_backend="fake", storage_backend="memory",
                   db_path=Path("unused.db"), request_timeout_s=5.0,
                   llm_generate_timeout_s=2.0, guard_retry_min_budget_s=0.0)  # fmt: skip
    runs = [asyncio.run(_run(messages, s, cfg)) for s in STYLES]
    assert all(run == runs[0] for run in runs[1:])


# --- no demographic inference (PRD L3c) -----------------------------------------------------

DEMOGRAPHIC = ("ethnic", "nationality", "race", "religion", "gender", "dialect", "accent")


def test_no_type_holds_a_demographic_field() -> None:
    for cls in (StyleProfile, UserSettings, Plan):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not {n for n in names if any(d in n.lower() for d in DEMOGRAPHIC)}
    assert {f.name for f in dataclasses.fields(StyleProfile)} == {"directness", "formality"}


def test_the_settings_table_has_only_the_chosen_values() -> None:
    import oasis

    sql = (Path(oasis.__file__).parent / "storage" / "migrations" / "0007_settings.sql").read_text(
        encoding="utf-8"
    )
    body = sql[sql.index("CREATE TABLE settings") :].lower()
    assert not any(d in body for d in DEMOGRAPHIC)
    for column in ("directness", "formality", "country", "updated_at"):
        assert column in body


def test_style_is_never_set_from_anything_but_the_user() -> None:
    """Only the settings endpoint writes settings; nothing in the decision plane or engine."""
    import oasis

    root = Path(oasis.__file__).parent
    writers = [p.relative_to(root).as_posix() for p in root.rglob("*.py")
               if "set_settings(" in p.read_text(encoding="utf-8")]  # fmt: skip
    assert sorted(writers) == ["api/routes.py", "storage/memory.py", "storage/repository.py",
                               "storage/split.py", "storage/sqlite.py"]  # fmt: skip
