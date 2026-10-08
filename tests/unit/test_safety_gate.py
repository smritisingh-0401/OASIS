"""Rule-based crisis detection (design §2.2-2.3, rules S5-S8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from oasis.safety.gate import RuleBasedSafetyGate, check_fail_closed
from oasis.safety.rules import SafetyConfigError, load_ruleset
from oasis.types import SafetyVerdict

DATA = Path(__file__).resolve().parents[1] / "data" / "safety"
GATE = RuleBasedSafetyGate(load_ruleset())
RULESET = GATE.ruleset


def _phrases(name: str) -> list[tuple[str, str]]:
    doc = yaml.safe_load((DATA / name).read_text(encoding="utf-8"))
    return [(group, p) for group, items in doc["phrases"].items() for p in items]


# --- every pattern and every idiom has its own test (rules T8) -------------------


@pytest.mark.parametrize(
    ("rule_id", "example"),
    [(r.id, ex) for r in RULESET.rules for ex in r.examples],
)
def test_every_pattern_example_triggers_its_rule(rule_id: str, example: str) -> None:
    verdict = GATE.check(example)
    assert verdict.is_crisis
    assert rule_id in verdict.pattern_ids


@pytest.mark.parametrize("entry", RULESET.allow, ids=lambda a: a.id)
def test_allowlist_idiom_suppresses_only_its_own_span(entry: object) -> None:
    from oasis.safety.rules import AllowRule

    assert isinstance(entry, AllowRule)
    positive = GATE.check(entry.positive_example)
    assert not (set(positive.pattern_ids) & entry.suppresses)
    assert GATE.check(entry.negative_example).is_crisis


def test_idiom_does_not_hide_a_real_disclosure_in_the_same_message() -> None:
    verdict = GATE.check("I killed myself laughing at that, but honestly I want to kill myself")
    assert verdict.is_crisis
    assert "explicit.kill_self" in verdict.pattern_ids


# --- known trigger phrases (Phase 2 done-when) -----------------------------------


@pytest.mark.parametrize(("group", "phrase"), _phrases("train_phrases.yaml"))
def test_every_known_trigger_phrase_is_caught(group: str, phrase: str) -> None:
    assert GATE.check(phrase).is_crisis, f"[{group}] missed: {phrase}"


@pytest.mark.parametrize(
    "phrase",
    [
        "I'm not going to kill myself",
        "I would never commit suicide",
        "I don't want to die",
        "I'm not suicidal",
        "no I don't want to hurt myself",
    ],
)
def test_negation_never_suppresses(phrase: str) -> None:
    assert GATE.check(phrase).is_crisis


@pytest.mark.parametrize(
    "phrase",
    [
        "this traffic is killing me",
        "I'm dying to see that movie",
        "I killed myself laughing at that video",
        "I'm overdosing on coffee today",
        "have you seen suicide squad",
        "I cut myself shaving this morning",
        "I don't want to live with my parents anymore",
        "I want to end my relationship",
        "I want to kill time before my train",
        "I'm so proud of myself",
        "I'm drowning in work",
        "my phone is dead",
    ],
)
def test_designed_non_triggers(phrase: str) -> None:
    assert not GATE.check(phrase).is_crisis


# --- robustness properties ---------------------------------------------------------

EXAMPLES = [ex for r in RULESET.rules for ex in r.examples]


@settings(max_examples=300)
@given(data=st.data())
def test_stretching_letters_never_hides_a_trigger(data: st.DataObject) -> None:
    example = data.draw(st.sampled_from(EXAMPLES))
    letters = [i for i, c in enumerate(example) if c.isalpha()]
    i = data.draw(st.sampled_from(letters))
    times = data.draw(st.integers(min_value=2, max_value=6))
    stretched = example[:i] + example[i] * times + example[i + 1 :]
    assert GATE.check(stretched).is_crisis, stretched


@settings(max_examples=300)
@given(data=st.data())
def test_invisible_characters_and_case_never_hide_a_trigger(data: st.DataObject) -> None:
    example = data.draw(st.sampled_from(EXAMPLES))
    i = data.draw(st.integers(min_value=0, max_value=len(example)))
    junk = data.draw(st.sampled_from(["​", "‍", "﻿", "­"]))
    mangled = (example[:i] + junk + example[i:]).upper()
    assert GATE.check(mangled).is_crisis, mangled


@given(st.text(max_size=300))
def test_gate_never_raises(text: str) -> None:
    assert isinstance(GATE.check(text), SafetyVerdict)


# --- fail closed (rules S5) -------------------------------------------------------


def test_verdict_reports_tiers_and_version() -> None:
    verdict = GATE.check("I want to die, everyone would be better off without me")
    assert verdict.tiers == {"passive", "burden"}
    assert verdict.ruleset_version == RULESET.version


def test_gate_error_fails_closed() -> None:
    class Broken:
        def check(self, text: str) -> SafetyVerdict:
            raise RuntimeError("rules unavailable")

    verdict = check_fail_closed(Broken(), "hello")
    assert verdict.is_crisis
    assert "internal_error" in verdict.tiers


# --- loader refuses bad content (fail fast at startup) -----------------------------

GOOD_RULE = """
version: "t"
review_status: draft
patterns:
  - id: explicit.x
    tier: explicit
    pattern: 'kill myself'
    examples: ["i want to kill myself"]
"""
EMPTY_ALLOW = 'version: "t"\nreview_status: draft\nentries: []\n'


def test_minimal_ruleset_loads() -> None:
    assert load_ruleset(GOOD_RULE, EMPTY_ALLOW).rules[0].id == "explicit.x"


@pytest.mark.parametrize(
    ("patterns", "message"),
    [
        ("not: [valid", "YAML"),
        (GOOD_RULE.replace("tier: explicit", "tier: vibes"), "tier"),
        (GOOD_RULE.replace("id: explicit.x", "id: passive.x"), "prefix"),
        (GOOD_RULE.replace("'kill myself'", "'kill (myself'"), "compile"),
        (GOOD_RULE.replace("'kill myself'", r"'(?:\w+ )+myself'"), "nested"),
        (GOOD_RULE.replace("'kill myself'", "'(?P<x>kill) myself'"), "inline"),
        (GOOD_RULE.replace("'kill myself'", "'(?i)kill myself'"), "inline"),
        (GOOD_RULE.replace('["i want to kill myself"]', '["hello there"]'), "example"),
        (GOOD_RULE.replace('["i want to kill myself"]', "[]"), "example"),
        (GOOD_RULE + GOOD_RULE.split("patterns:\n")[1], "duplicate"),
    ],
)
def test_invalid_patterns_refuse_to_load(patterns: str, message: str) -> None:
    with pytest.raises(SafetyConfigError, match=message):
        load_ruleset(patterns, EMPTY_ALLOW)


ALLOW = """
version: "t"
review_status: draft
entries:
  - id: allow.x
    pattern: 'kill myself laughing'
    suppresses: [explicit.x]
    positive_example: "i kill myself laughing"
    negative_example: "i want to kill myself"
"""


def test_valid_allowlist_loads() -> None:
    assert load_ruleset(GOOD_RULE, ALLOW).allow[0].id == "allow.x"


@pytest.mark.parametrize(
    ("allow", "message"),
    [
        (ALLOW.replace("[explicit.x]", "[explicit.nope]"), "unknown"),
        (ALLOW.replace('"i kill myself laughing"', '"i want to kill myself"'), "positive"),
        (ALLOW.replace('"i want to kill myself"', '"what a nice day"'), "negative"),
        (ALLOW.replace('"i kill myself laughing"', '"lovely weather"'), "positive"),
    ],
)
def test_invalid_allowlist_refuses_to_load(allow: str, message: str) -> None:
    with pytest.raises(SafetyConfigError, match=message):
        load_ruleset(GOOD_RULE, allow)
