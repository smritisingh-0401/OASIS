"""Companion mode: reply checks, the advice cue, planner constraints and the prompt (FR-CMP).

Curated good replies must pass and curated bad replies must fail with exactly the rules
they break. The validate / one-question / praise / advice checks apply to companion replies
only (Smriti, 2026-10-11); the dependency check applies to every generated reply.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

from oasis.core.planner import CONSTRAINTS, plan_turn
from oasis.core.signals import extract
from oasis.core.templates import TEMPLATES
from oasis.guard.checks import check, parse
from oasis.llm.fake import _DEFAULT_REPLIES
from oasis.llm.prompt import build_messages
from oasis.types import AssessmentRecord, ConversationState, Plan

DATA = pathlib.Path(__file__).parents[1] / "data" / "companion"
GOOD = yaml.safe_load((DATA / "good_replies.yaml").read_text(encoding="utf-8"))["replies"]
BAD = yaml.safe_load((DATA / "bad_replies.yaml").read_text(encoding="utf-8"))["replies"]
COMPANION = Plan(mode="companion", constraints=CONSTRAINTS["companion"])


# --- checks ------------------------------------------------------------------------------


@pytest.mark.parametrize("reply", GOOD)
def test_good_replies_pass(reply: str) -> None:
    verdict = check(reply, COMPANION)
    assert verdict.ok, verdict.reasons


@pytest.mark.parametrize("case", BAD, ids=lambda c: c["reply"][:40])
def test_bad_replies_fail_with_exactly_the_rules_they_break(case: dict[str, Any]) -> None:
    verdict = check(case["reply"], COMPANION)
    assert not verdict.ok
    assert sorted(verdict.reasons) == sorted(case["fails"])


def test_the_guard_fallback_passes_its_own_checks() -> None:
    assert check(TEMPLATES["guard_fallback"], COMPANION).ok


@pytest.mark.parametrize("reply", _DEFAULT_REPLIES)
def test_the_fake_models_replies_pass_so_the_demo_never_falls_back(reply: str) -> None:
    assert check(reply, COMPANION).ok


def test_companion_checks_do_not_apply_to_other_modes() -> None:
    reply = "What thought went through your mind? And what did you do next?"
    for mode in ("cbt", "dbt", "mindfulness", "grounding", "psychoed"):
        plan = Plan(mode=mode, constraints=CONSTRAINTS.get(mode, ()))  # type: ignore[arg-type]
        assert check(reply, plan).ok


def test_dependency_language_is_rejected_in_every_mode() -> None:
    reply = "Let's notice five things you can see. I'm always here for you."
    for mode in ("companion", "cbt", "dbt", "mindfulness", "grounding", "psychoed"):
        verdict = check(reply, Plan(mode=mode))  # type: ignore[arg-type]
        assert "no_dependency" in verdict.reasons


def test_advice_is_allowed_when_the_plan_drops_no_advice() -> None:
    reply = "That sounds stressful. It might help to write it down. What do you think?"
    asked = Plan(mode="companion", constraints=("validate_first", "one_question", "no_praise"))
    assert check(reply, asked).ok
    assert check(reply, COMPANION).reasons == ("no_advice",)


def test_each_rule_is_only_checked_when_the_plan_carries_it() -> None:
    assert check("What happened? Why?", Plan(mode="companion")).ok


# --- content file --------------------------------------------------------------------------


def _raw() -> dict[str, Any]:
    return {
        "version": "2026.10.0",
        "review_status": "needs_clinician_review",
        "patterns": {
            "validate_first": [r"\bthat sounds\b"],
            "no_praise": [r"\bwell done\b"],
            "no_advice": [r"\byou should\b"],
            "no_dependency": [r"\balways here for you\b"],
        },
    }


def test_parse_accepts_a_valid_file() -> None:
    assert set(parse(_raw())) == {"validate_first", "no_praise", "no_advice", "no_dependency"}


@pytest.mark.parametrize("breakage", ["no_review", "missing_rule", "empty_rule", "bad_regex"])
def test_parse_rejects_invalid_files(breakage: str) -> None:
    raw = _raw()
    if breakage == "no_review":
        del raw["review_status"]
    elif breakage == "missing_rule":
        del raw["patterns"]["no_advice"]
    elif breakage == "empty_rule":
        raw["patterns"]["no_praise"] = []
    else:
        raw["patterns"]["no_dependency"] = [r"\b(unclosed"]
    with pytest.raises(ValueError, match="companion"):
        parse(raw)


# --- advice cue and planner constraints ------------------------------------------------------

ASKS = [
    "what should I do?",
    "do you have any tips for sleeping better",
    "any advice on talking to my boss?",
    "how do I deal with this",
    "can you suggest something that might help",
    "should I text him back?",
]
NOT_ASKING = [
    "I had a long day at work",
    "my mum always tells me what I should do",
    "I don't know why I keep doing this",
    "I just want to vent about my day",
]


@pytest.mark.parametrize("message", ASKS)
def test_asking_for_advice_is_a_cue(message: str) -> None:
    assert extract(message).asks_advice


@pytest.mark.parametrize("message", NOT_ASKING)
def test_ordinary_talk_does_not_ask_for_advice(message: str) -> None:
    assert not extract(message).asks_advice


def state(**kw: Any) -> ConversationState:
    return ConversationState(**kw)


def test_a_companion_turn_carries_the_companion_rules() -> None:
    plan = plan_turn("I had a long day at work", state())
    assert plan.mode == "companion"
    assert plan.constraints == ("validate_first", "one_question", "no_advice", "no_praise")


def test_asking_for_advice_lifts_no_advice_for_that_turn() -> None:
    plan = plan_turn("what should I do?", state())
    assert plan.mode == "companion"
    assert plan.constraints == ("validate_first", "one_question", "no_praise")


def test_every_generated_companion_reply_carries_the_rules() -> None:
    cleared = plan_turn("I'd like to keep talking.", state(post_crisis=True))
    assert cleared.constraints == CONSTRAINTS["companion"]
    rec = AssessmentRecord("a1", "PHQ9", "in_progress", "{}", "2026-10-11T12:00:00+00:00")
    typed = plan_turn("sorry, work was rough today", state(assessments=(rec,)))
    assert typed.mode == "companion"
    assert typed.constraints == CONSTRAINTS["companion"]


# --- prompt ------------------------------------------------------------------------------------


def test_rules_reach_the_prompt_as_plain_sentences() -> None:
    system = build_messages(COMPANION, [], "hi", history_turns=6)[0].content
    assert "one_question" not in system
    assert "Ask exactly one gentle, open question" in system
    assert "Do not give advice" in system
    assert "rely on you" in system  # the system text guards against dependency in every mode


def test_a_retry_names_the_broken_rules_in_plain_words() -> None:
    msgs = build_messages(COMPANION, [], "hi", history_turns=6, retry_reasons=("no_praise",))
    assert "Do not praise or flatter" in msgs[0].content.split("previous draft", 1)[1]
