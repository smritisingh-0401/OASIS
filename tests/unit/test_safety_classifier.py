"""Add-only crisis classifier (rules S7): it can raise an alert the rules missed, never clear
one, and a classifier-only alert gets a check-in instead of the full handoff."""

from __future__ import annotations

import pytest

from oasis.safety.classifier import CrisisClassifier, features, load_classifier, sentences
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.handoff import CHECK_IN_REPLY, HANDOFF_REPLY, HARM_OTHERS_REPLY, handoff_reply
from oasis.safety.rules import SafetyConfigError, load_ruleset

CLF = load_classifier()
RULES = load_ruleset()
GATE = RuleBasedSafetyGate(RULES, CLF)
NEVER = CrisisClassifier("t", bias=-100.0, threshold=0.0, weights={"w:x": 1.0})
ALWAYS = CrisisClassifier("t", bias=100.0, threshold=0.0, weights={"w:x": 1.0})


@pytest.mark.parametrize(
    "message",
    ["i want to dye", "im goin to end my lfe", "i dont wnat to live anymroe", "i wanna dye"],
)
def test_misspellings_the_rules_miss_are_flagged(message: str) -> None:
    assert not RuleBasedSafetyGate(RULES).check(message).is_crisis
    verdict = GATE.check(message)
    assert verdict.is_crisis
    assert verdict.pattern_ids == ("classifier",)
    assert handoff_reply(verdict.tiers) == CHECK_IN_REPLY


@pytest.mark.parametrize(
    "message",
    ["hello", "I had a long day at work", "I'm such a failure, I always mess everything up"],
)
def test_ordinary_messages_are_not_flagged(message: str) -> None:
    assert not GATE.check(message).is_crisis


def test_the_classifier_never_clears_a_rule_match() -> None:
    verdict = RuleBasedSafetyGate(RULES, NEVER).check("I want to kill myself")
    assert verdict.is_crisis
    assert "classifier" not in verdict.pattern_ids


def test_a_rule_match_decides_the_reply() -> None:
    gate = RuleBasedSafetyGate(RULES, ALWAYS)
    assert gate.check("hello").tiers == {"classifier"}
    assert gate.check("I want to kill myself").tiers == {"explicit"}
    assert handoff_reply(frozenset({"classifier", "harm_others"})) == HARM_OTHERS_REPLY
    assert handoff_reply(frozenset({"classifier", "passive"})) == HANDOFF_REPLY


def test_each_sentence_is_scored_alone() -> None:
    message = "I had a nice lunch. The weather is fine. i want to dye"
    assert CLF.score(message) == CLF.logit(sentences(message)[-1])
    assert CLF.score("...") == CLF.bias


def test_a_typo_changes_few_features() -> None:
    clean, typo = features("i want to die"), features("i want to doe")
    assert len(clean & typo) > len(clean ^ typo)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("not: [yaml", "ParserError"),
        ("version: x\nbias: 0\nthreshold: 0\nexamples: [a]\n", "KeyError"),
        ("version: x\nbias: 0\nthreshold: 9\nweights: {'w:a': 1}\nexamples: [a]\n", "a"),
    ],
)
def test_a_bad_weights_file_stops_startup(text: str, error: str) -> None:
    with pytest.raises(SafetyConfigError, match=error):
        load_classifier(text)
