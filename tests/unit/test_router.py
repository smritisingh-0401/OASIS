"""Therapy router: weighted scores, margin, hysteresis, acute override, exercise hold (design §7).

The scenario table pins the start weights in content/router/weights.yaml: if a weight change
moves a row, the table must be updated on purpose, with a clinical-review note (CR-11).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from oasis.core.signals import extract
from oasis.router.router import accept, decline, dump_state, load_state, route, stop
from oasis.router.weights import config, features, parse, score_modes
from oasis.types import ROUTER_MODES, RouterState, Signals

CFG = config()
N = CFG.hysteresis_turns


def sig(**kw: Any) -> Signals:
    emotions = {k: kw.pop(k) for k in ("sadness", "anxiety", "anger", "shame", "loneliness")
                if k in kw}  # fmt: skip
    return Signals(emotions=emotions, **kw)


def leader(s: Signals, **extra: float) -> str:
    return score_modes(features(s, extra), CFG)[0].mode


# --- scenario table: signals -> expected leading mode (>= 30 rows) ---------------------

SCENARIOS: list[tuple[str, Signals, dict[str, float], str]] = [
    ("neutral message", sig(), {}, "companion"),
    ("wants to vent", sig(wants_to_talk=0.8), {}, "companion"),
    ("venting with a mild distortion", sig(wants_to_talk=1.0, distortion=0.3), {}, "companion"),
    ("venting beats a strong distortion", sig(wants_to_talk=0.9, distortion=0.9), {}, "companion"),
    ("strong distortion", sig(distortion=0.8), {}, "cbt"),
    ("distortion with shame", sig(distortion=1.0, shame=0.5), {}, "cbt"),
    ("moderate distortion", sig(distortion=0.5), {}, "cbt"),
    ("weak distortion", sig(distortion=0.3), {}, "companion"),
    ("distortion plus moderate PHQ-9", sig(distortion=0.5), {"phq_moderate_plus": 1.0}, "cbt"),
    ("moderate PHQ-9 alone", sig(), {"phq_moderate_plus": 1.0}, "companion"),
    ("strong dysregulation", sig(dysregulation=0.8), {}, "dbt"),
    ("dysregulation with anger", sig(dysregulation=0.6, anger=0.6), {}, "dbt"),
    ("anger alone", sig(anger=0.9), {}, "dbt"),
    ("mild anger", sig(anger=0.4), {}, "companion"),
    ("dysregulation over distortion", sig(dysregulation=0.8, distortion=0.4), {}, "dbt"),
    ("distortion over dysregulation", sig(distortion=0.8, dysregulation=0.4), {}, "cbt"),
    ("moderate overwhelm", sig(overwhelm=0.5), {}, "mindfulness"),
    ("overwhelm just under acute", sig(overwhelm=0.59), {}, "mindfulness"),
    ("anxiety", sig(anxiety=0.8), {}, "mindfulness"),
    ("mild anxiety", sig(anxiety=0.4), {}, "companion"),
    ("overwhelm and anxiety", sig(overwhelm=0.4, anxiety=0.4), {}, "mindfulness"),
    ("anxiety plus moderate GAD-7", sig(anxiety=0.6), {"gad_moderate_plus": 1.0}, "mindfulness"),
    ("overwhelm over distortion", sig(overwhelm=0.5, distortion=0.4), {}, "mindfulness"),
    ("sadness", sig(sadness=0.9), {}, "companion"),
    ("loneliness", sig(loneliness=0.9), {}, "companion"),
    ("shame alone", sig(shame=0.9), {}, "companion"),
    ("very negative valence", sig(valence=-1.0), {}, "companion"),
    ("very positive valence", sig(valence=1.0), {}, "companion"),
    ("sad and negative", sig(sadness=0.9, valence=-0.8), {}, "companion"),
    ("lonely but distorted", sig(loneliness=0.6, distortion=0.9), {}, "cbt"),
    ("everything low", sig(sadness=0.1, anxiety=0.1, distortion=0.1), {}, "companion"),
]


# Natural phrasings from manual testing (2026-10-12). Each one alone must lead its mode by
# the margin, so reworded messages in a row keep building the streak instead of resetting it.
PHRASINGS = {
    "cbt": [
        "I'm such a failure, I always mess everything up",
        "I always do something wrong",
        "I always do everything wrong",
        "It feels like i am carrying a burden of my failure",
        "I feel like a failure",
        "I never do anything right",
        "I can't do anything right",
        "I'm not good enough",
        "nobody likes me",
        "it's all my fault",
    ],
    "dbt": [
        "I'm so angry I want to scream",
        "I can't control my anger",
        "I'm furious and I want to smash something",
        "I lost my temper and yelled at everyone",
        "I can't calm down, I'm so angry",
        "I feel like I'm going to explode",
        "I'm so mad I could punch a wall",
        "I keep snapping at people",
        "my emotions are out of control",
        "i am so mad",
        "i am going to explode",
        "I'm boiling with rage",
        "I lose my temper over tiny things",
        "I keep lashing out at people",
        "I snapped at everyone today",
        "my emotions are all over the place",
    ],
    "mindfulness": [
        "I feel overwhelmed and anxious about everything",
        "I feel anxious about everything",
        "I feel so stressed and anxious",
        "my mind won't stop racing",
        "I can't stop overthinking",
        "I feel tense and on edge all the time",
        "I'm really stressed out",
        "my thoughts are all over the place",
        "I feel restless and worried",
        "I'm so nervous I can't settle",
    ],
}


def test_anger_then_explode_offers_dbt_on_the_second_message() -> None:
    # Manual testing, 2026-10-13: "so mad" alone used to lead companion and reset the streak.
    rs = RouterState()
    for message in ("I'm so angry, I want to scream, I can't control it", "i am so mad"):
        decision = route(extract(message), rs)
        rs = decision.state
    assert decision.offer == "dbt"


@pytest.mark.parametrize(("mode", "message"),
                         [(m, t) for m, ts in PHRASINGS.items() for t in ts])  # fmt: skip
def test_natural_phrasings_lead_their_mode(mode: str, message: str) -> None:
    s = extract(message)
    assert s.overwhelm < CFG.acute_threshold  # an offer, not straight to grounding
    first, second = score_modes(features(s, None), CFG)[:2]
    assert first.mode == mode
    assert first.score - second.score >= CFG.margin


def test_a_mode_leads_for_two_turns_before_an_offer() -> None:
    assert N == 2  # lowered from 3 (Smriti, 2026-10-12)


@pytest.mark.parametrize(("name", "signals", "extra", "expected"), SCENARIOS,
                         ids=[s[0] for s in SCENARIOS])  # fmt: skip
def test_scenario_table(
    name: str, signals: Signals, extra: dict[str, float], expected: str
) -> None:
    assert leader(signals, **extra) == expected


ACUTE = [
    ("acute overwhelm", sig(overwhelm=0.7)),
    ("acute at the threshold", sig(overwhelm=CFG.acute_threshold)),
    ("acute beats a strong distortion", sig(overwhelm=1.0, distortion=1.0)),
    ("acute beats venting", sig(overwhelm=0.9, wants_to_talk=1.0)),
]


@pytest.mark.parametrize(("name", "signals"), ACUTE, ids=[a[0] for a in ACUTE])
def test_acute_overwhelm_goes_straight_to_grounding(name: str, signals: Signals) -> None:
    decision = route(signals, RouterState())
    assert (decision.mode, decision.reason) == ("grounding", "acute_override")


def test_scenario_table_is_big_enough() -> None:
    assert len(SCENARIOS) + len(ACUTE) >= 30


# --- exact contributions (rules T2) ------------------------------------------------------

FEATURE_NAMES = sorted({s for m in CFG.modes.values() for s in m.weights})


@given(st.fixed_dictionaries({name: st.floats(0, 1) for name in FEATURE_NAMES}))
def test_bias_plus_contributions_equals_score(x: dict[str, float]) -> None:
    scores = score_modes(x, CFG)
    assert {s.mode for s in scores} == set(ROUTER_MODES)
    for s in scores:
        assert s.bias + sum(c.value for c in s.contributions) == pytest.approx(s.score)
        magnitudes = [abs(c.value) for c in s.contributions]
        assert magnitudes == sorted(magnitudes, reverse=True)
        assert {c.signal for c in s.contributions} == set(CFG.modes[s.mode].weights)
    ranked = [s.score for s in scores]
    assert ranked == sorted(ranked, reverse=True)


def test_ties_go_to_the_default_mode_first() -> None:
    scores = score_modes(dict.fromkeys(FEATURE_NAMES, 0.0), replace(CFG, modes={
        m: replace(c, bias=0.0) for m, c in CFG.modes.items()}))  # fmt: skip
    assert [s.mode for s in scores] == list(ROUTER_MODES)


def test_features_turn_valence_into_a_negative_part_only() -> None:
    assert features(sig(valence=-0.6))["valence_neg"] == pytest.approx(0.6)
    assert features(sig(valence=0.6))["valence_neg"] == 0.0


# --- margin and hysteresis -------------------------------------------------------------

CBT = sig(distortion=0.9)
DBT = sig(dysregulation=0.9)
VENT = sig(wants_to_talk=1.0)


FRESH = RouterState()


def run(seq: list[Signals], rs: RouterState = FRESH) -> list[Any]:
    out = []
    for s in seq:
        decision = route(s, rs)
        out.append(decision)
        rs = decision.state
    return out


def test_a_challenger_must_lead_for_n_turns_before_an_offer() -> None:
    decisions = run([CBT] * N)
    reasons = [d.reason for d in decisions]
    assert reasons == [f"hysteresis.{k}_of_{N}" for k in range(1, N)] + ["offer_structured_mode"]
    assert all(d.mode == "companion" for d in decisions)
    assert decisions[-1].offer == "cbt"
    assert decisions[-1].state.offered == "cbt"


def test_a_consented_mode_switches_without_asking_again() -> None:
    decisions = run([CBT] * N, RouterState(consented=frozenset({"cbt"})))
    assert (decisions[-1].mode, decisions[-1].reason) == ("cbt", "switch")
    assert decisions[-1].offer is None
    assert decisions[-1].state.current == "cbt"
    assert decisions[-1].state.streak == 0


def test_returning_to_companion_needs_no_consent_but_still_waits_n_turns() -> None:
    decisions = run([VENT] * N, RouterState(current="cbt"))
    assert [d.mode for d in decisions] == ["cbt"] * (N - 1) + ["companion"]
    assert decisions[-1].reason == "switch"


def test_alternating_cues_never_flip_the_mode() -> None:
    decisions = run([CBT, DBT] * 6)
    assert {d.mode for d in decisions} == {"companion"}
    assert all(d.offer is None for d in decisions)
    assert max(d.state.streak for d in decisions) == 1


def test_strong_cues_broken_by_ordinary_talk_never_build_a_streak() -> None:
    decisions = run([CBT, sig(), CBT, sig(), CBT, sig()])
    assert {d.mode for d in decisions} == {"companion"}
    assert all(d.offer is None for d in decisions)


def test_a_narrow_lead_does_not_count() -> None:
    narrow = sig(distortion=0.45)  # leads companion, but by less than the margin
    scores = score_modes(features(narrow), CFG)
    assert scores[0].mode == "cbt"
    assert scores[0].score - scores[1].score < CFG.margin
    decision = route(narrow, RouterState(challenger="cbt", streak=1))
    assert (decision.mode, decision.reason) == ("companion", "margin_not_met")
    assert decision.state.streak == 1


def test_the_incumbent_leading_resets_the_challenger() -> None:
    decision = route(VENT, RouterState(challenger="cbt", streak=2))
    assert decision.reason == "incumbent"
    assert (decision.state.challenger, decision.state.streak) == (None, 0)


def test_every_decision_carries_all_mode_scores() -> None:
    for decision in run([CBT, DBT, VENT, sig(overwhelm=0.9)]):
        assert {s.mode for s in decision.scores} == set(ROUTER_MODES)


# --- acute override ----------------------------------------------------------------------


def test_acute_overwhelm_interrupts_a_building_streak() -> None:
    rs = run([CBT] * (N - 1))[-1].state
    assert rs.streak == N - 1
    decision = route(sig(overwhelm=0.9), rs)
    assert decision.mode == "grounding"
    assert (decision.state.current, decision.state.challenger, decision.state.streak) == (
        "grounding", None, 0)  # fmt: skip


def test_acute_overwhelm_interrupts_another_exercise_but_keeps_consents() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    decision = route(sig(overwhelm=0.9), rs)
    assert decision.reason == "acute_override"
    assert decision.state.exercise is None  # the planner starts the grounding script
    assert decision.state.consented == frozenset({"cbt"})


def test_acute_overwhelm_during_grounding_continues_the_script() -> None:
    rs = RouterState(current="grounding", exercise="senses_54321", step=2)
    decision = route(sig(overwhelm=0.9), rs)
    assert (decision.mode, decision.reason) == ("grounding", "mid_exercise_hold")
    assert decision.state == rs


def test_an_open_offer_is_withdrawn_when_acute_overwhelm_arrives() -> None:
    decision = route(sig(overwhelm=0.9), RouterState(offered="cbt", challenger="cbt", streak=N))
    assert decision.state.offered is None


def test_grounding_ends_with_its_script() -> None:
    decision = route(sig(), RouterState(current="grounding"))
    assert decision.mode == "companion"
    assert decision.state.current == "companion"


# --- exercise hold and opt-out -------------------------------------------------------------


def test_no_switch_mid_exercise() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    for s in [DBT, DBT, DBT, VENT]:
        decision = route(s, rs)
        assert (decision.mode, decision.reason) == ("cbt", "mid_exercise_hold")
        assert decision.state == rs


def test_opting_out_ends_the_exercise_and_routes_normally() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    decision = route(sig(opt_out=True), rs)
    assert decision.state.exercise is None
    assert decision.state.step == 0
    assert decision.reason != "mid_exercise_hold"


def test_opt_out_outside_an_exercise_changes_nothing() -> None:
    assert route(sig(opt_out=True), RouterState()).reason == "incumbent"


# --- consent ------------------------------------------------------------------------------


def test_typing_instead_of_answering_an_offer_counts_as_not_now() -> None:
    decision = route(CBT, RouterState(offered="cbt", challenger="cbt", streak=N))
    assert decision.state.offered is None
    assert decision.state.streak <= 1  # the lead has to build up again
    assert decision.offer is None


def test_accept_switches_and_remembers_consent() -> None:
    rs = accept(RouterState(offered="dbt", challenger="dbt", streak=N))
    assert (rs.current, rs.offered, rs.challenger, rs.streak) == ("dbt", None, None, 0)
    assert rs.consented == frozenset({"dbt"})


def test_decline_clears_the_offer_and_the_lead() -> None:
    rs = decline(RouterState(offered="dbt", challenger="dbt", streak=N))
    assert (rs.current, rs.offered, rs.challenger, rs.streak) == ("companion", None, None, 0)
    assert rs.consented == frozenset()


def test_stop_ends_the_exercise_and_goes_back_to_companion() -> None:
    rs = stop(RouterState(current="cbt", exercise="thought_check", step=2,
                          consented=frozenset({"cbt"})))  # fmt: skip
    assert (rs.current, rs.exercise, rs.step) == ("companion", None, 0)
    assert rs.consented == frozenset({"cbt"})


def test_typing_stop_mid_exercise_goes_back_to_companion() -> None:
    rs = RouterState(current="dbt", exercise="stop_skill", step=1, consented=frozenset({"dbt"}))
    decision = route(sig(opt_out=True), rs)
    assert (decision.state.current, decision.state.exercise) == ("companion", None)


# --- persistence ---------------------------------------------------------------------------


def test_router_state_survives_a_json_round_trip() -> None:
    rs = RouterState(
        current="cbt",
        challenger="dbt",
        streak=2,
        offered="dbt",
        exercise="thought_check",
        step=1,
        consented=frozenset({"cbt", "dbt"}),
    )
    assert load_state(dump_state(rs)) == rs
    assert load_state("{}") == RouterState()


@pytest.mark.parametrize("bad", [
    "not json", "[]", '{"current": "wizard"}', '{"streak": -1}', '{"streak": "2"}',
    '{"consented": ["cbt", "sorcery"]}', '{"exercise": "unknown_script"}',
    '{"offered": "grounding"}', '{"step": 99, "exercise": "thought_check"}',
])  # fmt: skip
def test_corrupt_router_state_falls_back_to_a_fresh_start(bad: str) -> None:
    # A bad row must never break a turn; starting over in companion mode is always safe.
    assert load_state(bad) == RouterState()


def test_accept_without_an_offer_is_a_bug() -> None:
    with pytest.raises(ValueError, match="no structured mode"):
        accept(RouterState())


# --- invalid weights stop startup ----------------------------------------------------------


def _weights(**over: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "version": "1", "review_status": "needs_clinician_review", "margin": 0.15,
        "hysteresis_turns": 3, "acute_overwhelm_threshold": 0.6,
        "modes": {m: {"bias": 0.0, "weights": {"distortion": 1.0}} for m in ROUTER_MODES},
    }  # fmt: skip
    raw.update(over)
    return raw


@pytest.mark.parametrize("bad", [
    {"review_status": "approved"},
    {"version": ""},
    {"modes": {"companion": {"bias": 0.0, "weights": {}}}},
    {"margin": -0.1},
    {"hysteresis_turns": 0},
    {"acute_overwhelm_threshold": 1.5},
])  # fmt: skip
def test_invalid_router_weights_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="router"):
        parse(_weights(**bad))


def test_valid_router_weights_parse() -> None:
    assert parse(_weights()).hysteresis_turns == 3
