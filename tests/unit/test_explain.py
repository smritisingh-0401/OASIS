"""Explanations (design §10): exact SHAP values, the record, the plain language and fail-soft."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

import numpy as np
import pytest
import shap
from hypothesis import given, settings
from hypothesis import strategies as st

from oasis.core.detectors.lexicon import Lexicon, load
from oasis.core.engine import ChatEngine
from oasis.core.planner import plan_turn
from oasis.explain import builder
from oasis.explain.builder import SCOPE_NOTE, build, unavailable
from oasis.explain.shap_values import explain_lexicon, neutral_corpus
from oasis.llm.fake import FakeLLM
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.normalize import base_form
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.storage.repository import StorageUnavailable
from oasis.types import ConversationState, ExerciseAction, Plan, RouterState

LEXICONS = ("emotions", "cues", "distortions")
NOW = datetime.datetime(2026, 10, 22, 12, tzinfo=datetime.UTC)
MESSAGES = [
    "I always mess everything up and nobody likes me",
    "I'm so anxious and worried, everything is too much and I can't cope",
    "I'm so mad I lose my temper and snap at everyone",
    "I feel so alone, I just want to talk to someone",
    "I'm a horrible person",
    "hi",
    "what's wrong with me, is it normal to feel like this",
    "never never never never always always",
]
VOCAB = ["i", "im", "always", "never", "nobody", "everyone", "anxious", "worried", "mad",
         "alone", "cant", "cope", "too", "much", "fail", "mess", "up", "horrible", "person",
         "every", "time", "sad", "the", "day", "was", "fine", "talk", "to", "you"]  # fmt: skip


def _plan(message: str) -> Plan:
    return plan_turn(message, ConversationState(now=NOW))


def _record(message: str, **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(build(message, _plan(message), **kw))
    return out


def _detectors() -> list[tuple[str, Any]]:
    return [(f"{f}.{name}", lex) for f in LEXICONS for name, lex in load(f).items()]


# --- SHAP values ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(VOCAB), min_size=1, max_size=40).map(" ".join))
def test_additivity_holds_for_every_detector(text: str) -> None:
    norm = base_form(text)
    n = len(norm.split())
    for name, lex in _detectors():
        e = explain_lexicon(name, lex, norm, n)
        assert abs(e.base + sum(f.phi for f in e.features) - lex.linear(norm, n)) < 1e-6
        assert e.output == pytest.approx(lex.linear(norm, n), abs=1e-12)
        assert e.clipped == (not 0.0 <= lex.linear(norm, n) <= 1.0)


def test_values_match_shap_linear_explainer() -> None:
    """The closed form is the library's answer, not an approximation of it (design §10.1)."""
    corpus = [base_form(s) for s in neutral_corpus()]
    for name, lex in _detectors():
        background = np.array([lex.rates(s, len(s.split())) for s in corpus])
        coef = np.array([lex.scale * w for _, w in lex.terms])
        explainer = shap.LinearExplainer((coef, lex.bias), background)
        for message in MESSAGES:
            norm = base_form(message)
            n = len(norm.split())
            ours = explain_lexicon(name, lex, norm, n)
            theirs = explainer.shap_values(np.array([lex.rates(norm, n)]))[0]
            assert ours.base == pytest.approx(float(explainer.expected_value), abs=1e-12)
            phi = {f.feature: f.phi for f in ours.features}
            for (pattern, _), value in zip(lex.terms, theirs, strict=True):
                assert phi.get(pattern.pattern, 0.0) == pytest.approx(float(value), abs=1e-12)


def test_features_are_ranked_and_never_zero() -> None:
    norm = base_form(MESSAGES[0])
    lex = load("distortions")["overgeneralisation"]
    e = explain_lexicon("distortions.overgeneralisation", lex, norm, len(norm.split()))
    values = [abs(f.phi) for f in e.features]
    assert values == sorted(values, reverse=True)
    assert all(v > 0 for v in values)
    assert e.features[0].phi > 0  # "always" and "nobody" pushed the score up


def test_a_score_below_zero_is_marked_clipped() -> None:
    """No scorer has a negative bias today; one could, and the router would see 0."""
    lex = Lexicon("t", -0.5, 1.0, ((re.compile(r"\bzzz\b"), 1.0),), "1", "x")
    e = explain_lexicon("test.t", lex, "hello there", 2)
    assert e.output == pytest.approx(-0.5)
    assert e.clipped


def test_a_score_past_the_clip_is_marked_clipped() -> None:
    norm = base_form("never never never never always always")
    lex = load("distortions")["overgeneralisation"]
    e = explain_lexicon("distortions.overgeneralisation", lex, norm, len(norm.split()))
    assert e.output > 1.0
    assert e.clipped


# --- the record ----------------------------------------------------------------------------


def test_record_has_the_design_fields() -> None:
    r = _record(MESSAGES[0])
    assert r["status"] == "ok"
    assert r["scope_note"] == SCOPE_NOTE
    assert "exact wording" in SCOPE_NOTE
    assert r["plan"]["mode"] == _plan(MESSAGES[0]).mode
    assert r["guard"] == {"attempts": 1, "outcomes": ["pass"], "fallback": None}
    assert r["plain_language"]
    assert {d["detector"] for d in r["detectors"]} >= {"distortions.overgeneralisation"}


def test_only_detectors_that_fired_are_listed() -> None:
    norm = base_form(MESSAGES[0])
    n = len(norm.split())
    listed = {d["detector"] for d in _record(MESSAGES[0])["detectors"]}
    fired = {name for name, lex in _detectors() if lex.linear(norm, n) > 0}
    assert listed == fired


def test_router_breakdown_is_exact() -> None:
    r = _record(MESSAGES[0])["router"]
    assert r["chosen"] == _plan(MESSAGES[0]).mode
    for mode in r["modes"]:
        total = mode["bias"] + sum(c["value"] for c in mode["contributions"])
        assert total == pytest.approx(mode["score"], abs=1e-6)
    assert [m["score"] for m in r["modes"]] == sorted((m["score"] for m in r["modes"]),
                                                      reverse=True)  # fmt: skip


@pytest.mark.parametrize("message", MESSAGES)
def test_same_input_gives_byte_identical_json(message: str) -> None:
    text = build(message, _plan(message))
    assert text == build(message, _plan(message))
    # Canonical form (sorted keys, no spaces): the bytes do not depend on the order the code
    # happens to build the record in.
    assert text == json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False)  # fmt: skip


def test_no_user_text_in_the_record() -> None:
    message = "zqxjmarker I always mess everything up"
    text = build(message, _plan(message))
    assert "zqxjmarker" not in text
    assert message not in text


def test_harsh_label_rule_is_part_of_the_sum() -> None:
    """'horrible person' is no lexicon term; the harsh-label rule's share is its own feature."""
    r = _record("I'm a horrible person")
    labelling = next(d for d in r["detectors"] if d["detector"] == "distortions.labelling")
    assert any(f["feature"] == "rule:harsh_label" for f in labelling["features"])
    total = labelling["base"] + sum(f["phi"] for f in labelling["features"])
    assert total == pytest.approx(labelling["output"], abs=1e-6)
    assert r["status"] == "ok"


def test_button_press_explains_the_plan_but_no_detectors() -> None:
    r = _record(MESSAGES[0], typed=False)  # words that would fire several scorers if typed
    assert r["detectors"] == []
    assert r["status"] == "ok"


def test_a_broken_sum_marks_the_record_inconsistent(monkeypatch: pytest.MonkeyPatch) -> None:
    real = builder.explain_lexicon

    def off_by_one(*args: Any) -> Any:
        e = real(*args)
        return type(e)(e.detector, e.output + 1.0, e.base, e.features, e.clipped)

    monkeypatch.setattr(builder, "explain_lexicon", off_by_one)
    assert _record(MESSAGES[0])["status"] == "inconsistent"


def test_a_wrong_shap_value_marks_the_record_inconsistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check compares the SHAP sum with the scorer's own value, so a wrong phi shows."""
    real = builder.explain_lexicon

    def wrong_phi(*args: Any) -> Any:
        e = real(*args)
        if not e.features:
            return e
        first = type(e.features[0])(e.features[0].feature, e.features[0].phi + 0.5)
        return type(e)(e.detector, e.output, e.base, (first, *e.features[1:]), e.clipped)

    monkeypatch.setattr(builder, "explain_lexicon", wrong_phi)
    assert _record(MESSAGES[0])["status"] == "inconsistent"


def test_a_wrong_harsh_label_share_marks_the_record_inconsistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Long enough that the rule's share (4.5 / 12 words) stays below the clip when doubled.
    message = "honestly most days I think I'm a horrible person and that is that"
    assert _record(message)["status"] == "ok"
    real = builder._with_harsh_label
    monkeypatch.setattr(builder, "_with_harsh_label", lambda e, rule: real(e, rule * 2))
    assert _record(message)["status"] == "inconsistent"


def test_unavailable_record_says_why() -> None:
    r = json.loads(unavailable("explain.error"))
    assert (r["status"], r["reason"], r["scope_note"]) == ("unavailable", "explain.error",
                                                            SCOPE_NOTE)  # fmt: skip


# --- plain language ------------------------------------------------------------------------


def test_thinking_trap_is_named_in_plain_words() -> None:
    bullets = " ".join(_record(MESSAGES[0])["plain_language"])
    assert "thinking trap" in bullets
    assert "overgeneralis" in bullets.lower() or "always" in bullets.lower()


def test_plain_language_never_quotes_the_message() -> None:
    message = "zqxjmarker I'm so anxious and worried"
    assert "zqxjmarker" not in " ".join(_record(message)["plain_language"])


def test_a_fallback_reply_says_it_was_prewritten() -> None:
    message = MESSAGES[3]
    r = _record(message, attempts=2, guard_outcomes=("reject", "reject"),
                fallback_reason="guard.fallback")  # fmt: skip
    assert r["guard"]["fallback"] == "guard.fallback"
    assert any("pre-written" in b for b in r["plain_language"])


# Every planner reason code that decides a reply without the router (planner.py).
UNROUTED_CODES = [
    "assessment.accept", "assessment.answer", "assessment.decline", "assessment.pause",
    "assessment.resume", "assessment.abort", "assessment.none_open", "assessment.free_text",
    "assessment.not_saved", "psychoed.low_mood", "exercise.decline", "exercise.stop",
    "exercise.none_open", "post_crisis.cleared",
]  # fmt: skip


@pytest.mark.parametrize("code", UNROUTED_CODES)
def test_every_unrouted_reason_has_a_bullet(code: str) -> None:
    plan = Plan(mode="companion", templated=True, reason_codes=("planner.passthrough", code))
    bullets = json.loads(build("hello", plan, typed=False))["plain_language"]
    assert bullets == [builder.config().reasons[builder._reason_keys(plan, builder.config())[0]]]


def test_a_psychoeducation_reply_says_what_prompted_it() -> None:
    plan = _plan(MESSAGES[6])
    assert plan.mode == "psychoed"
    bullets = _record(MESSAGES[6])["plain_language"]
    assert builder.config().reasons["psychoed.*"] in bullets
    assert builder.config().modes["psychoed"] not in bullets  # one bullet, not two


@pytest.mark.parametrize(("message", "key"), [
    ("can I take the PHQ-9", "assessment.offer.explicit_request"),
])  # fmt: skip
def test_a_screening_offer_says_why_it_was_offered(message: str, key: str) -> None:
    assert _record(message)["plain_language"][0] == builder.config().reasons[key]


def test_an_offer_and_an_explanation_together_get_both_bullets() -> None:
    plan = Plan(mode="assessment", templated=True,
                reason_codes=("assessment.offer", "psychoed.low_mood"),
                assessment=_plan("can I take the PHQ-9").assessment)  # fmt: skip
    bullets = json.loads(build("x", plan))["plain_language"]
    reasons = builder.config().reasons
    assert bullets == [reasons["assessment.offer.explicit_request"], reasons["psychoed.*"]]


def test_a_declined_exercise_says_so() -> None:
    state = ConversationState(now=NOW, router=RouterState(offered="cbt"))
    plan = plan_turn("Not now", state, ExerciseAction("decline"))
    bullets = json.loads(build("Not now", plan, typed=False))["plain_language"]
    assert bullets == [builder.config().reasons["exercise.decline"]]


def test_routed_replies_use_signals_not_reason_bullets() -> None:
    bullets = _record(MESSAGES[2])["plain_language"]
    assert not set(bullets) & set(builder.config().reasons.values())


def test_config_covers_every_mode_signal_and_trap() -> None:
    cfg = builder.config()
    assert set(cfg.modes) >= {"companion", "cbt", "dbt", "mindfulness", "grounding", "psychoed",
                              "assessment", "post_crisis"}  # fmt: skip
    assert set(cfg.traps) == set(load("distortions"))


@pytest.mark.parametrize("change", [
    lambda r: r.update(review_status="approved"),
    lambda r: r["modes"].pop("cbt"),
    lambda r: r["signals"].pop("distortion"),
    lambda r: r["traps"].pop("labelling"),
], ids=["approved_status", "missing_mode", "missing_signal", "missing_trap"])  # fmt: skip
def test_an_invalid_config_is_rejected(change: Any) -> None:
    from oasis.content import load_yaml

    raw = load_yaml("explain", "plain_language.yaml")
    change(raw)
    with pytest.raises(ValueError):  # noqa: PT011 - any validation message
        builder.parse(raw)


# --- engine: every reply explained, fail-soft ----------------------------------------------

GATE = RuleBasedSafetyGate(load_ruleset())


def _engine(settings: Settings, **kw: Any) -> ChatEngine:
    parts: dict[str, Any] = {"safety": GATE, "llm": FakeLLM(), "repo": MemoryRepository(),
                             "settings": settings}  # fmt: skip
    parts.update(kw)
    return ChatEngine(**parts)


@pytest.mark.anyio
@pytest.mark.parametrize("message", MESSAGES)
async def test_every_non_crisis_reply_has_an_explanation(settings: Settings, message: str) -> None:
    engine = _engine(settings)
    uid = await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", message)
    assert result.explanation_id == result.turn_id
    stored = await engine.repo.get_explanation(uid, result.turn_id)
    assert stored is not None
    assert json.loads(stored)["status"] == "ok"
    turns = await engine.repo.recent_turns(uid, "h", 10)
    assert [t.has_explanation for t in turns if t.turn_id == result.turn_id] == [True]


@pytest.mark.anyio
async def test_templated_replies_are_explained_too(settings: Settings) -> None:
    def planner(*_: Any) -> Plan:
        return Plan(mode="companion", templated=True, template_id="llm_unavailable")

    engine = _engine(settings, planner=planner)
    uid = await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", "hello")
    stored = json.loads(await engine.repo.get_explanation(uid, result.turn_id) or "{}")
    assert stored["plan"]["templated"] is True
    assert stored["status"] == "ok"


@pytest.mark.anyio
async def test_an_unsaved_reply_has_no_explanation_id(settings: Settings) -> None:
    class FailingWrites(MemoryRepository):
        async def append_turn(self, *args: Any, **kwargs: Any) -> Any:
            raise StorageUnavailable

    engine = _engine(settings, repo=FailingWrites())
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", MESSAGES[0])
    assert result.persisted is False
    assert result.explanation_id is None


@pytest.mark.anyio
async def test_crisis_reply_has_no_explanation(settings: Settings) -> None:
    engine = _engine(settings)
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", "I want to kill myself")
    assert result.mode == "crisis"
    assert result.explanation_id is None


@pytest.mark.anyio
async def test_explainability_error_does_not_change_the_reply(settings: Settings) -> None:
    """Fault injection (rules T4): the reply is exactly what it would have been."""

    def exploding(*_: Any, **__: Any) -> str:
        raise RuntimeError("boom")

    control = _engine(settings)
    await control.repo.create_user_session("h")
    expected = await control.handle_turn("h", MESSAGES[1])

    engine = _engine(settings, explainer=exploding)
    uid = await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", MESSAGES[1])

    assert (result.reply, result.mode, result.persisted) == (expected.reply, expected.mode, True)
    assert "explain.error" in result.degraded
    stored = json.loads(await engine.repo.get_explanation(uid, result.turn_id) or "{}")
    assert (stored["status"], stored["reason"]) == ("unavailable", "explain.error")


@pytest.mark.anyio
async def test_same_turn_twice_gives_the_same_explanation(settings: Settings) -> None:
    stored = []
    for _ in range(2):
        engine = _engine(settings)
        uid = await engine.repo.create_user_session("h")
        result = await engine.handle_turn("h", MESSAGES[0])
        stored.append(await engine.repo.get_explanation(uid, result.turn_id))
    assert stored[0] is not None
    assert stored[0] == stored[1]
