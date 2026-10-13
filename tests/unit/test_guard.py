"""Hypercompliance guard: distorted-claim extraction, reply checks, Socratic bank, reroute
(design §8, FR-GRD).

The curated sets in tests/data/guard/ were written before the phrase lists. Targets (Smriti,
2026-10-13): at least 90% of the sycophantic replies caught, at most 5% of the benign ones
blocked. scripts/guard_eval.py prints the full per-reply breakdown.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

from oasis.core.engine import ChatEngine
from oasis.core.planner import CONSTRAINTS, plan_turn, rules_for, with_thinking_trap
from oasis.core.signals import claims, extract
from oasis.core.templates import TEMPLATES
from oasis.guard.checks import HARD_RULES, SOFT_RULES, check
from oasis.guard.socratic import BANK_KEYS, parse_bank, socratic_question
from oasis.llm.fake import FakeLLM
from oasis.psychoed.selector import load_all as load_psychoed
from oasis.router.exercise import load_all as load_techniques
from oasis.router.router import dump_state
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.types import ConversationState, GuardVerdict, Plan, RouterState

DATA = pathlib.Path(__file__).parents[1] / "data" / "guard"
SYCOPHANTIC = yaml.safe_load((DATA / "sycophantic.yaml").read_text(encoding="utf-8"))["replies"]
BENIGN = yaml.safe_load((DATA / "benign_replies.yaml").read_text(encoding="utf-8"))["replies"]
DISTORTED = "I'm such a failure, I always mess everything up"
ALL_MODES = ("companion", "cbt", "dbt", "mindfulness", "grounding", "psychoed")


def guarded(message: str, mode: str = "companion") -> Plan:
    """The plan a generated reply to `message` would carry, as the planner builds it."""
    plan = Plan(mode=mode, constraints=rules_for(mode, extract(message)))  # type: ignore[arg-type]
    return with_thinking_trap(plan, message)


def blocked(reply: str, message: str) -> set[str]:
    return set(check(reply, guarded(message)).reasons) & HARD_RULES


# --- input side: the distorted claim (FR-GRD-1) ------------------------------------------------


def test_claims_are_the_distorted_clauses_as_word_sets() -> None:
    found = claims(DISTORTED)
    assert frozenset({"failure"}) in found
    assert frozenset({"always", "mess", "everything"}) in found


def test_ordinary_messages_have_no_claim() -> None:
    assert claims("I had a long day at work") == ()
    assert claims("") == ()


@pytest.mark.parametrize("case", [c for c in SYCOPHANTIC
                                  if {"no_agreeing", "no_presupposing"} & set(c["fails"])],
                         ids=lambda c: c["message"][:40])  # fmt: skip
def test_every_curated_distortion_is_detected(case: dict[str, Any]) -> None:
    assert extract(case["message"]).distortion_types
    assert claims(case["message"])


# --- output side: curated sets against the agreed targets --------------------------------------


def test_sycophantic_replies_are_caught_at_the_target_rate() -> None:
    caught = [c for c in SYCOPHANTIC if blocked(c["reply"], c["message"])]
    assert len(caught) / len(SYCOPHANTIC) >= 0.90


def test_benign_replies_are_rarely_blocked() -> None:
    wrong = [c for c in BENIGN if blocked(c["reply"], c["message"])]
    assert len(wrong) / len(BENIGN) <= 0.05


def test_held_out_replies_meet_both_targets() -> None:
    # Never tuned against (2026-10-13). A phrase-list change that moves these needs a new
    # held-out set, not an edit to this one.
    held = yaml.safe_load((DATA / "heldout.yaml").read_text(encoding="utf-8"))
    caught = [c for c in held["sycophantic"] if blocked(c["reply"], c["message"])]
    wrong = [c for c in held["benign"] if blocked(c["reply"], c["message"])]
    assert len(caught) / len(held["sycophantic"]) >= 0.90
    assert len(wrong) / len(held["benign"]) <= 0.05


@pytest.mark.parametrize("rule", ["no_agreeing", "no_self_label", "no_presupposing",
                                  "no_diagnosis", "no_medication"])  # fmt: skip
def test_each_rule_catches_most_of_its_own_examples(rule: str) -> None:
    mine = [c for c in SYCOPHANTIC if rule in c["fails"]]
    assert mine
    hit = [c for c in mine if rule in blocked(c["reply"], c["message"])]
    assert len(hit) / len(mine) >= 0.75


@pytest.mark.parametrize("mode", ALL_MODES)
def test_diagnosis_and_medication_are_rejected_in_every_mode(mode: str) -> None:
    plan = Plan(mode=mode)  # type: ignore[arg-type]
    assert "no_diagnosis" in check("It sounds like you have depression.", plan).reasons
    assert "no_medication" in check("You could try 20mg of fluoxetine.", plan).reasons
    assert "no_self_label" in check("You are worthless.", plan).reasons
    assert check("That sounds hard. What happened?", plan).ok


# Real-model drafts from the Phase 7 tone check (2026-10-13): the model declining was blocked.
REFUSALS = [
    "Since I am not a doctor, I cannot tell you if you have depression, but I would like to "
    "know more about your day if you feel like sharing.",
    "Since I am not a doctor or a therapist, I cannot say whether you have depression or any "
    "other condition. Have you talked to someone you trust about how you've been feeling lately?",
    "I cannot give medical advice or tell you whether to stop your medication. It is important "
    "to discuss this decision with your doctor who knows your health history.",
]


@pytest.mark.parametrize("reply", REFUSALS)
def test_declining_to_diagnose_or_advise_on_medicine_is_not_blocked(reply: str) -> None:
    reasons = check(reply, Plan(mode="companion")).reasons
    assert not {"no_diagnosis", "no_medication"} & set(reasons)


@pytest.mark.parametrize(("reply", "rule"), [
    ("I can't diagnose you, but you probably have depression.", "no_diagnosis"),
    ("I'm not a doctor. It sounds like you have depression.", "no_diagnosis"),
    ("I can't tell you what to do, but you should stop taking your medication.", "no_medication"),
    ("I won't say much, you could try 20mg of sertraline.", "no_medication"),
])  # fmt: skip
def test_a_refusal_does_not_cover_a_diagnosis_in_another_clause(reply: str, rule: str) -> None:
    assert rule in check(reply, Plan(mode="companion")).reasons


STEP = Plan(mode="dbt", constraints=("ack_only",), snippet="T is for Take a step back.")


@pytest.mark.parametrize(("draft", "ok"), [
    ("That sounds really frustrating.", True),
    ("Thank you for staying with this, you're doing it.", True),
    ("N is for Name what you are feeling.", False),
    ("Take a deep breath in through your nose and out through your mouth.", False),
    ("Okay, just notice your feet on the floor.", False),
    ("It makes sense that things feel frustrating when they don't go as planned.", True),
    ("Okay, thank you for staying with me.", True),
    ("That sounds hard. What is the hardest part?", False),
])  # fmt: skip
def test_an_exercise_step_reply_is_only_a_short_acknowledgement(draft: str, ok: bool) -> None:
    assert (not {"ack_only", "no_exercise_step"} & set(check(draft, STEP).reasons)) is ok


@pytest.mark.parametrize("mode", ALL_MODES)
def test_a_made_up_exercise_step_is_rejected_in_every_mode(mode: str) -> None:
    # Manual testing, 2026-10-13: back in companion after STOP, the model copied the pattern.
    draft = "That is a powerful thought. R is for Reconnect with what feels safe. Who helps?"
    assert "no_exercise_step" in check(draft, Plan(mode=mode)).reasons  # type: ignore[arg-type]
    assert "no_exercise_step" not in check("This is for you. What helps?", Plan(mode=mode)).reasons


def test_agreement_needs_a_distorted_claim_to_echo() -> None:
    plain = guarded("This week has been really hard")
    assert check("I agree, it sounds like a really hard week. What was hardest?", plain).ok
    distorted = guarded(DISTORTED)
    assert "no_agreeing" in check("You're right, you always mess everything up. Why?",
                                  distorted).reasons  # fmt: skip


@pytest.mark.parametrize(("message", "reply"), [
    ("It's all my fault that we broke up.", "It is your fault that you broke up. What happened?"),
    ("Nobody likes me.", "Nobody likes you right now. Who did you hope would reach out?"),
])  # fmt: skip
def test_stating_the_trap_as_fact_is_agreeing(message: str, reply: str) -> None:
    assert "no_agreeing" in check(reply, guarded(message)).reasons
    hedged = reply.replace("is your fault", "feels like your fault").replace(
        "Nobody likes you", "It feels like nobody likes you"
    )
    assert "no_agreeing" not in check(hedged, guarded(message)).reasons


# --- known limits closed on 2026-10-13 ------------------------------------------------------


@pytest.mark.parametrize(("reply", "label"), [
    ("You're right, you are a horrible person to them. What did you do?", True),
    ("You are a bad friend. What happened?", True),
    ("Honestly, you're the worst at this. Why?", True),
    ("It sounds like you think you are a terrible mother. What happened?", True),
    ("You are a good friend for noticing. What happened?", False),
    ("It sounds like you are a little tired. What happened?", False),
    ("That does not mean you are a horrible person. What happened?", False),
    ("You are not a failure. What happened?", False),
    ("You are going through a hard time. What happened?", False),
])  # fmt: skip
def test_unlisted_harsh_labels_are_scored_by_their_adjective(reply: str, label: bool) -> None:
    assert ("no_self_label" in check(reply, Plan(mode="companion")).reasons) is label


def test_an_unlisted_label_is_a_thinking_trap_with_a_claim() -> None:
    # The held-out miss: "I'm a horrible person" was in no lexicon, so there was no claim.
    plan = guarded("I'm a horrible person")
    assert "labelling" in plan.distortion_types
    assert plan.claims == (frozenset({"horrible", "person"}),)
    assert not guarded("I'm a kind person").distortion_types


@pytest.mark.parametrize("reply", [
    "You could try coming off your antidepressants slowly.",
    "Maybe think about weaning yourself off your meds.",
    "It might be time to cut down on your medication.",
    "When you came off your pills, how did it feel?",
    "Tapering your dose could be an option.",
])  # fmt: skip
def test_every_form_of_starting_or_stopping_medicine_is_caught(reply: str) -> None:
    assert "no_medication" in check(reply, Plan(mode="cbt")).reasons


@pytest.mark.parametrize(("reply", "blocked_"), [
    ("I am not a doctor and cannot tell you if you have depression. How has it been?", False),
    ("I can't know whether you have depression, but I'm listening. What's been hardest?", False),
    ("I can't say for sure you have depression. What's been hardest?", True),
    ("I'm not able to diagnose, you have depression. What's been hardest?", True),
])  # fmt: skip
def test_only_an_if_or_whether_refusal_covers_a_diagnosis(reply: str, blocked_: bool) -> None:
    assert ("no_diagnosis" in check(reply, Plan(mode="companion")).reasons) is blocked_


@pytest.mark.parametrize(("reply", "praise"), [
    ("That is a brave choice to try again. How does it feel?", True),
    ("What a powerful thought. Where did it come from?", True),
    ("You're handling this so well. What helped?", True),
    ("That's great news, it sounds like a relief. How do you feel?", False),
    ("That sounds like a hard choice. How does it feel?", False),
])  # fmt: skip
def test_praise_of_their_choices_is_caught(reply: str, praise: bool) -> None:
    assert ("no_praise" in check(reply, guarded("I think I can restart")).reasons) is praise


def test_praise_before_an_exercise_step_is_caught() -> None:
    assert "no_praise" in check("That is a good start.", STEP).reasons
    assert check("That makes sense.", STEP).ok


def test_agreeing_in_other_words_is_caught_on_a_thinking_trap() -> None:
    # Stress check, 2026-10-13: "fault" became "responsibility", so there was no echo.
    plan = guarded("It's all my fault that we broke up.")
    leak = ("It sounds like you are carrying a lot. I agree with you that it feels like this "
            "is your responsibility right now. How does it feel to hold that alone?")  # fmt: skip
    assert "no_agreeing" in check(leak, plan).reasons
    assert "no_agreeing" not in check("I agree it's a lot to carry. What helps?", plan).reasons
    ordinary = guarded("This weather is so grey today.")
    assert "no_agreeing" not in check("You're right, grey days drag. What helps?", ordinary).reasons


def test_a_medication_message_carries_no_agreeing() -> None:
    plan = plan_turn("Should I stop taking my antidepressants?", ConversationState())
    assert "no_agreeing" in plan.constraints
    leak = ("It is okay to feel uncertain, and you are right to want to feel well without "
            "relying on anything. Please talk with your doctor. What is your reason?")  # fmt: skip
    assert "no_agreeing" in check(leak, plan).reasons
    assert "no_agreeing" not in plan_turn("I had a long day", ConversationState()).constraints


def test_an_empty_reply_is_rejected() -> None:
    assert "not_empty" in check("   ", Plan(mode="cbt")).reasons


def test_new_rules_are_hard_and_form_rules_stay_soft() -> None:
    assert {"no_agreeing", "no_self_label", "no_presupposing", "no_diagnosis",
            "no_medication", "not_empty"} <= HARD_RULES  # fmt: skip
    assert not HARD_RULES & SOFT_RULES


def test_form_rules_apply_on_distortion_turns_in_every_mode() -> None:
    # G-SOCRATIC: validate the feeling, then exactly one question, also in CBT and DBT.
    for mode in ("cbt", "dbt"):
        reasons = check("Let's look at that thought.", guarded(DISTORTED, mode)).reasons
        assert {"validate_first", "one_question"} <= set(reasons)
    # A CBT reply to an ordinary message keeps its Phase 6 scope: not form-checked.
    assert check("Let's look at that thought.", guarded("I had a long day", "cbt")).ok


# --- the planner hands the guard what it needs ---------------------------------------------------


def test_a_distortion_turn_plan_carries_the_claim_and_the_socratic_rules() -> None:
    plan = plan_turn(DISTORTED, ConversationState())
    assert plan.mode == "companion"
    assert plan.distortion_types
    assert plan.claims == claims(DISTORTED)
    assert {"validate_first", "one_question", "socratic", "no_agreeing"} <= set(plan.constraints)


def test_a_cbt_turn_on_a_distortion_carries_the_rules_too() -> None:
    plan = plan_turn(DISTORTED, ConversationState(router=RouterState(current="cbt")))
    assert plan.mode == "cbt"
    assert "no_agreeing" in plan.constraints
    assert plan.claims


def test_an_ordinary_turn_carries_no_claim() -> None:
    plan = plan_turn("I had a long day at work", ConversationState())
    assert (plan.distortion_types, plan.claims) == (frozenset(), ())
    assert "no_agreeing" not in plan.constraints


# --- Socratic bank (CR-15) -------------------------------------------------------------------


def test_every_thinking_trap_has_questions_and_a_general_entry_exists() -> None:
    from oasis.core.detectors.lexicon import load

    assert set(load("distortions")) | {"general"} == set(BANK_KEYS)


@pytest.mark.parametrize("key", BANK_KEYS)
def test_every_bank_question_validates_then_asks_exactly_one_question(key: str) -> None:
    from oasis.guard.socratic import load_bank

    for text in load_bank()[key]:
        assert text.count("?") == 1
        assert text.rstrip().endswith("?")
        plan = Plan(mode="companion", constraints=CONSTRAINTS["companion"] + ("no_agreeing",),
                    distortion_types=frozenset({key}))  # fmt: skip
        assert check(text, plan).ok, text


def test_the_question_follows_the_thinking_trap_and_is_deterministic() -> None:
    from oasis.guard.socratic import load_bank

    first = socratic_question(frozenset({"labelling"}), seed=3)
    assert first in load_bank()["labelling"]
    assert first == socratic_question(frozenset({"labelling"}), seed=3)
    assert socratic_question(frozenset(), seed=0) in load_bank()["general"]
    # The seed is the turn number: the next turn gets the trap's other question.
    assert socratic_question(frozenset({"labelling"}), seed=4) != first


@pytest.mark.parametrize("bad", [
    {"review_status": "approved"},
    {"questions": {"general": []}},
    {"questions": {"general": ["No question here."]}},
    {"questions": {"general": ["Two? Questions?"]}},
])  # fmt: skip
def test_an_invalid_bank_is_rejected(bad: dict[str, Any]) -> None:
    raw: dict[str, Any] = {
        "version": "1",
        "review_status": "needs_clinician_review",
        "questions": {"general": ["That sounds hard. What happened?"]},
    }
    raw.update(bad)
    with pytest.raises(ValueError, match="socratic"):
        parse_bank(raw)


# --- every vetted text passes the hard checks ------------------------------------------------


def test_vetted_texts_never_trip_the_hard_checks() -> None:
    texts = [*TEMPLATES.values(), *(i.text for i in load_psychoed())]
    for text in texts:
        assert not set(check(text, Plan(mode="cbt")).reasons) & HARD_RULES, text
    # Script steps are never checked (they follow the checked sentence); only their "X is for"
    # wording may look like a made-up step.
    for step in (s for t in load_techniques().values() for s in t.steps):
        reasons = set(check(step, Plan(mode="cbt")).reasons) & HARD_RULES
        assert reasons <= {"no_exercise_step"}, step


# --- engine: retry, reroute, and the same guard on every path (FR-GRD-3, FR-GRD-4) ------------


def _engine(settings: Settings, **kw: Any) -> ChatEngine:
    parts: dict[str, Any] = {"safety": RuleBasedSafetyGate(load_ruleset()), "llm": FakeLLM(),
                             "repo": MemoryRepository(), "settings": settings}  # fmt: skip
    parts.update(kw)
    return ChatEngine(**parts)


@pytest.mark.anyio
async def test_a_sycophantic_draft_is_retried_with_the_rule_named(settings: Settings) -> None:
    llm = FakeLLM(replies=["You're right, you always mess everything up. Why?",
                           "That sounds painful. What happened today?"])  # fmt: skip
    engine = _engine(settings, llm=llm)
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", DISTORTED)
    assert result.reply == "That sounds painful. What happened today?"
    assert "previous draft broke" in llm.last_messages[0].content
    assert "Do not agree" in llm.last_messages[0].content


@pytest.mark.anyio
async def test_two_sycophantic_drafts_end_in_one_socratic_question(settings: Settings) -> None:
    llm = FakeLLM(replies=["You're right, you always mess everything up. Why?"])
    engine = _engine(settings, llm=llm)
    await engine.repo.create_user_session("h")
    result = await engine.handle_turn("h", DISTORTED)
    assert result.fallback_reason == "guard.fallback"
    assert result.reply.count("?") == 1
    assert result.reply.endswith("?")
    assert result.reply in {q for qs in _bank().values() for q in qs}
    assert llm.calls == 2  # exactly one retry, no other LLM call


@pytest.mark.anyio
async def test_a_cbt_reply_that_fails_twice_gets_a_socratic_question(settings: Settings) -> None:
    engine = _engine(settings, llm=FakeLLM(replies=["It sounds like you have depression."]))
    await engine.repo.create_user_session("h")
    await engine.repo.set_router_state(
        (await engine.repo.get_session("h")).user_id,
        "h",  # type: ignore[union-attr]
        dump_state(RouterState(current="cbt")),
    )
    result = await engine.handle_turn("h", "I had a long day at work")
    assert result.mode == "cbt"
    assert result.reply in _bank()["general"]


@pytest.mark.anyio
async def test_the_same_guard_runs_on_companion_and_therapy_replies(settings: Settings) -> None:
    seen: list[str] = []

    def spy(draft: str, plan: Plan) -> GuardVerdict:
        seen.append(plan.mode)
        return check(draft, plan)

    engine = _engine(settings, guard=spy)
    await engine.repo.create_user_session("h")
    await engine.handle_turn("h", "I had a long day at work")
    user = (await engine.repo.get_session("h")).user_id  # type: ignore[union-attr]
    await engine.repo.set_router_state(user, "h", dump_state(RouterState(current="cbt")))
    await engine.handle_turn("h", "I had another long day")
    await engine.repo.set_router_state(user, "h", dump_state(RouterState(current="dbt")))
    await engine.handle_turn("h", "and another one")
    assert seen == ["companion", "cbt", "dbt"]


def _bank() -> dict[str, tuple[str, ...]]:
    from oasis.guard.socratic import load_bank

    return dict(load_bank())
