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
from oasis.guard.checks import SOFT_RULES, check, opener, parse
from oasis.llm.fake import _DEFAULT_REPLIES
from oasis.llm.prompt import build_messages
from oasis.types import AssessmentRecord, ConversationState, Plan, TurnRecord

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


def test_the_fallbacks_pass_their_own_checks() -> None:
    assert check(TEMPLATES["companion_fallback"], COMPANION).ok


def test_only_style_rules_are_soft() -> None:
    assert {"validate_first", "one_question", "fresh_opener"} == SOFT_RULES


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
    assert plan.constraints == ("validate_first", "no_advice", "one_question", "no_praise")


def test_asking_for_advice_swaps_no_advice_for_offering_ideas() -> None:
    plan = plan_turn("what should I do?", state())
    assert plan.mode == "companion"
    assert plan.constraints == ("validate_first", "offer_ideas", "one_question", "no_praise")
    system = build_messages(plan, [], "what should I do?", history_turns=6)[0].content
    assert "offer one or two gentle, practical suggestions" in system
    assert check("That sounds hard. You could try a rota. Would that fit?", plan).ok


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
    assert "makes sense" not in system  # no stock phrase for the model to copy
    assert "Do not give advice" in system
    assert "rely on you" in system  # the system text guards against dependency in every mode
    # "This traffic is killing me" is a gripe, not a crisis: no inflating or darkening it.
    assert "never make a feeling sound bigger or darker" in system
    assert "reflecting their feeling" not in system  # it made small talk sound like worry


def test_a_retry_names_the_broken_rules_in_plain_words() -> None:
    msgs = build_messages(COMPANION, [], "hi", history_turns=6, retry_reasons=("no_praise",))
    assert "Do not praise or flatter" in msgs[0].content.split("previous draft", 1)[1]


# --- varied openers (a conversation should not start every reply the same way) -------------


def _said(*replies: str, mode: str = "companion") -> tuple[TurnRecord, ...]:
    return tuple(TurnRecord(f"t{i}", i, "assistant", r, mode, "") for i, r in enumerate(replies))  # type: ignore[arg-type]


def test_recent_companion_openers_go_into_the_plan() -> None:
    history = (*_said("It sounds like a long day. What happened?",
                      "That must be tiring. What helped?",
                      "It sounds like a lot. What next?"),
               *_said("Welcome to step one.", mode="grounding"))  # fmt: skip
    plan = plan_turn("work was busy again", state(history=history))
    assert plan.mode == "companion"
    assert plan.avoid_openers == ("it sounds like", "that must be")


def test_only_the_last_three_companion_replies_count() -> None:
    history = _said("No wonder you're tired. Why?", "A. B?", "C d e. F?", "G h i. J?")
    assert "no wonder youre" not in plan_turn("hello", state(history=history)).avoid_openers


def test_the_prompt_names_openers_to_avoid() -> None:
    plan = Plan(mode="companion", avoid_openers=("it sounds like",))
    system = build_messages(plan, [], "hi", history_turns=6)[0].content
    assert 'do not begin with: "it sounds like"' in system


def test_a_draft_repeating_a_recent_opener_breaks_fresh_opener() -> None:
    plan = Plan(mode="companion", constraints=CONSTRAINTS["companion"],
                avoid_openers=("it sounds like",))  # fmt: skip
    assert check("It sounds like a lot. What happened?", plan).reasons == ("fresh_opener",)
    assert check("That sounds like a lot. What happened?", plan).ok
    assert opener("It's  okay, really.") == "its okay really"


# --- listening replies (demo testing, 2026-10-29) -------------------------------------------
# "When I am feeling sad you are asking me how much sad": a reply sometimes just listens.

LISTEN = Plan(mode="companion", constraints=("validate_first", "no_advice", "no_question",
                                             "no_praise"))  # fmt: skip


@pytest.mark.parametrize("message", [
    "When I am feeling sad you are asking me how much sad",
    "please stop asking me questions",
    "can you just listen",
    "I don't want questions right now, I just need to vent",
])  # fmt: skip
def test_asking_for_no_questions_gets_a_listening_reply(message: str) -> None:
    plan = plan_turn(message, state())
    assert "no_question" in plan.constraints
    assert "one_question" not in plan.constraints
    assert "listen.asked" in plan.reason_codes


def test_after_two_questions_in_a_row_the_next_reply_listens() -> None:
    asked = _said("That sounds hard. What happened?", "That must hurt. How are you coping?")
    plan = plan_turn("work again", state(history=asked))
    assert "no_question" in plan.constraints
    assert "listen.two_questions" in plan.reason_codes
    listened = _said("That sounds hard. What happened?", "That must hurt. I'm here.")
    assert "one_question" in plan_turn("work again", state(history=listened)).constraints


def test_a_long_outpouring_gets_a_listening_reply() -> None:
    message = " ".join(["everything at the hostel has been going wrong this term"] * 5)
    plan = plan_turn(message, state())
    assert "no_question" in plan.constraints
    assert "listen.long_message" in plan.reason_codes


def test_asking_for_ideas_still_gets_a_question() -> None:
    asked = _said("That sounds hard. What happened?", "That must hurt. How are you coping?")
    plan = plan_turn("what should I do?", state(history=asked))
    assert "one_question" in plan.constraints


def test_a_listening_reply_asks_nothing() -> None:
    assert check("That sounds really heavy. I'm here and listening.", LISTEN).ok
    assert check("That sounds heavy. What happened?", LISTEN).reasons == ("no_question",)
    assert check(TEMPLATES["listen_fallback"], LISTEN).ok
    assert "?" not in TEMPLATES["listen_fallback"]


def test_the_listening_prompt_says_not_to_ask() -> None:
    system = build_messages(LISTEN, [], "hi", history_turns=6)[0].content
    assert "Do not ask a question" in system
    assert "ask one gentle open question" not in system


def test_why_this_reply_says_why_it_only_listens() -> None:
    import json

    from oasis.explain import builder

    message = "please stop asking me questions"
    bullets = json.loads(builder.build(message, plan_turn(message, state())))["plain_language"]
    assert bullets[-1] == builder.config().reasons["listen.asked"]
    assert "asks one gentle question" not in " ".join(bullets)
