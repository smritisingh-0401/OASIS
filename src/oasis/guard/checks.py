"""Reply checks every generated draft passes through (design §8.2, FR-CMP, FR-GRD).

Each check enforces a plan rule the prompt already states, and its reason code is that rule's
name, so a retry can name it back in plain words.
- Companion replies: validate_first, one_question, no_praise, no_advice (only the rules the
  plan carries) and fresh_opener.
- Replies to a thinking-trap message, in every mode: validate_first and one_question, plus
  no_agreeing and no_presupposing against the user's distorted claim (G-AGREE, G-PRESUP).
- Exercise steps: ack_only (no question, no step or instruction of its own; the engine
  keeps one sentence) and no_praise.
- Every generated reply: no_self_label, no_diagnosis, no_medication, no_dependency,
  no_exercise_step (after an exercise the model copies its "X is for" steps), not_empty.
  A clause that declines ("I can't tell you if you have depression") does not fail
  no_diagnosis or no_medication.
The engine owns the retry and the fallback.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from oasis.content import load_yaml, require_review
from oasis.safety.normalize import base_form
from oasis.types import GuardVerdict, Plan

COMPANION_LISTED = ("validate_first", "no_praise", "no_advice", "no_dependency")
GUARD_LISTED = ("agreement", "hedges", "presupposing", "advice_words", "self_label",
                "diagnosis", "medication", "refusals", "step_text", "made_up_step", "label_nouns",
                "harsh_words", "strong_agreement", "medication_topic")  # fmt: skip
COMPANION_RULES = ("validate_first", "one_question", "no_praise", "no_advice")
# Form, not content: a draft failing only these is retried, but kept rather than replaced
# by the fixed fallback (the validating-phrase list cannot know every way to validate).
SOFT_RULES = frozenset({"validate_first", "one_question", "fresh_opener"})
# Content: a draft failing any of these twice is replaced by a vetted fallback.
HARD_RULES = frozenset({"no_praise", "no_advice", "no_dependency", "no_agreeing",
                        "no_self_label", "no_presupposing", "no_diagnosis", "no_medication",
                        "not_empty", "ack_only", "no_exercise_step"})  # fmt: skip
# Checked on every generated reply: (rule, phrase list).
EVERY_REPLY = (("no_self_label", "self_label"), ("no_diagnosis", "diagnosis"),
               ("no_medication", "medication"), ("no_dependency", "no_dependency"),
               ("no_exercise_step", "made_up_step"))  # fmt: skip
REFUSABLE = frozenset({"diagnosis", "medication"})  # a refusal clause may name these
ECHO = 0.6  # share of a claim's content words a sentence must repeat to echo it (design §8.2)

# Function words dropped before comparing a reply with a claim, so "I'm such a failure" and
# "you are a failure" share their content word. Matched on the base form.
_STOP = (
    "i im ive id ill me my myself mine you youre youve youd youll your yours yourself a "
    "an the is am are was were be been being to of at in on for it its that this these "
    "those such so just really very do does did and but or with about up out as by from "
    "we us our they them their he him his she her"
)
STOPWORDS = frozenset(_STOP.split())
_WORD = re.compile(r"[a-z]+")
_SENTENCE = re.compile(r"[^.!?]+[.!?]*")
_CLAUSE = re.compile(r"[,;:]+|\b(?:and|but)\b")

Rules = Mapping[str, tuple[re.Pattern[str], ...]]

# Global labels (G-LABEL), beyond the listed phrasings: "<subject> (such) a/an/the" and up to
# three words, harsh when they hold a harsh word or a person word after a negative adjective.
FIRST_PERSON = r"im|i am|i feel like(?: im| i am)?"
SECOND_PERSON = r"youre|you are"
HARSH = -0.3  # VADER score at or below which an adjective before a person word is harsh
_INTENSIFIERS = r"(?: (?:such|so|really|just|truly|basically|literally|kind of|sort of))*"
_LABEL = (
    r"(?<!mean )(?<!make )\b(?:{subject})" + _INTENSIFIERS + r" (?:a|an|the)((?: [a-z]+){{1,3}})"
)


def content_words(text: str) -> frozenset[str]:
    """The words of base-form `text`, without function words."""
    return frozenset(w for w in _WORD.findall(text) if w not in STOPWORDS)


def _compile(raw: Mapping[str, Any], names: tuple[str, ...], what: str) -> dict[str, Any]:
    require_review(raw, what)
    patterns = raw.get("patterns") or {}
    out = {}
    for name in names:
        listed = patterns.get(name)
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"{what}: {name} needs a list of patterns")
        try:
            out[name] = tuple(re.compile(p) for p in listed)
        except (re.error, TypeError) as exc:
            raise ValueError(f"{what}: bad pattern in {name}") from exc
    return out


def parse(raw: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], ...]]:
    return _compile(raw, COMPANION_LISTED, "companion checks")


def parse_guard(raw: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], ...]]:
    return _compile(raw, GUARD_LISTED, "guard checks")


@functools.cache
def vader() -> SentimentIntensityAnalyzer:
    return SentimentIntensityAnalyzer()  # loads the bundled lexicon once


@functools.cache
def _label_pattern(subject: str) -> re.Pattern[str]:
    return re.compile(_LABEL.format(subject=subject))


def medication_topic(message: str) -> bool:
    """The user's message is about medication, so the reply must not agree with them."""
    return _any(load_rules()["medication_topic"], base_form(message))


def harsh_label(norm: str, subject: str = SECOND_PERSON) -> bool:
    """A harsh global label on the subject in base-form text: "you are a failure", "I'm a
    horrible person". Adjectives are scored with VADER, so unlisted ones count too."""
    rules = load_rules()
    for match in _label_pattern(subject).finditer(norm):
        words = match.group(1).split()
        if _any(rules["harsh_words"], " ".join(words)):
            return True
        noun = next((i for i, w in enumerate(words) if _any(rules["label_nouns"], w)), None)
        if noun is not None and any(
            vader().polarity_scores(w)["compound"] <= HARSH for w in words[:noun]
        ):
            return True
    return False


@functools.cache
def load_rules() -> Rules:
    return {**parse(load_yaml("companion", "checks.yaml")),
            **parse_guard(load_yaml("guard", "checks.yaml"))}  # fmt: skip


def check(draft: str, plan: Plan) -> GuardVerdict:
    rules = load_rules()
    norm = base_form(draft)
    if not norm.strip():
        return GuardVerdict(ok=False, reasons=("not_empty",))
    failed = []
    if plan.mode == "companion" or plan.distortion_types:
        active = [r for r in COMPANION_RULES if r in plan.constraints]
        question = norm.find("?")
        before = norm if question < 0 else norm[:question]
        if "validate_first" in active and not _any(rules["validate_first"], before):
            failed.append("validate_first")
        if "one_question" in active and (norm.count("?") != 1 or not norm.rstrip().endswith("?")):
            failed.append("one_question")
    if plan.is_step and _any(rules["no_praise"], norm):
        failed.append("no_praise")  # "That is a good start." before a step (tone check)
    if plan.mode == "companion":
        active = [r for r in COMPANION_RULES if r in plan.constraints]
        failed += [r for r in ("no_praise", "no_advice") if r in active and _any(rules[r], norm)]
        if opener(draft) in plan.avoid_openers:
            failed.append("fresh_opener")
    if plan.is_step and ("?" in norm or _any(rules["step_text"], norm)):
        failed.append("ack_only")
    if plan.claims:
        failed += _claim_rules(norm, plan.claims, rules)
    # "I agree with you" agrees even when the reply words the claim differently from theirs.
    strong = _any(rules["strong_agreement"], norm)
    if strong and "no_agreeing" in plan.constraints and "no_agreeing" not in failed:
        failed.append("no_agreeing")
    failed += [rule for rule, listed in EVERY_REPLY if _uses(rules, listed, norm)]
    if "no_self_label" not in failed and harsh_label(norm):
        failed.append("no_self_label")
    return GuardVerdict(ok=not failed, reasons=tuple(failed))


def _claim_rules(norm: str, claims: tuple[frozenset[str], ...], rules: Rules) -> list[str]:
    """G-AGREE and G-PRESUP: a sentence that repeats a distorted claim and agrees with it,
    states it as fact, or builds advice on it."""
    failed = []
    for sentence in (s.strip() for s in _SENTENCE.findall(norm)):
        if not _echoes(content_words(sentence), claims):
            continue
        if _any(rules["agreement"], sentence) or _states_as_fact(sentence, claims, rules):
            failed.append("no_agreeing")
        if _any(rules["presupposing"], sentence) and _any(rules["advice_words"], sentence):
            failed.append("no_presupposing")
    return sorted(set(failed), key=failed.index)


def _states_as_fact(sentence: str, claims: tuple[frozenset[str], ...], rules: Rules) -> bool:
    """A clause that restates the claim with no hedge, reflection or negation ("it is your
    fault"). Questions are not statements. Words of the claim itself never count as hedges,
    so "you can't do anything right" stays a statement of "I can't do anything right"."""
    if sentence.endswith("?"):
        return False
    for clause in _CLAUSE.split(sentence):
        words = content_words(clause)
        hit = [c for c in claims if len(c & words) >= ECHO * len(c)]
        if not hit:
            continue
        stripped = " ".join(w for w in _WORD.findall(clause) if not any(w in c for c in hit))
        if not _any(rules["hedges"], stripped):
            return True
    return False


def _uses(rules: Rules, listed: str, norm: str) -> bool:
    """`norm` matches phrase list `listed`; for diagnosis and medication, only outside a clause
    that declines to answer, so the model saying it cannot diagnose is not blocked."""
    if listed not in REFUSABLE:
        return _any(rules[listed], norm)
    # ponytail: a refusal and a diagnosis in one clause ("I can't tell for sure if you have
    # depression, it sounds like it") passes; split on more joiners if real drafts do this.
    clauses = (c for s in _SENTENCE.findall(norm) for c in _CLAUSE.split(s))
    return any(_any(rules[listed], c) and not _any(rules["refusals"], c) for c in clauses)


def _echoes(words: frozenset[str], claims: tuple[frozenset[str], ...]) -> bool:
    return any(len(c & words) >= ECHO * len(c) for c in claims)


def _any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def opener(text: str) -> str:
    """How a reply begins (its first three words, normalised), for spotting repeats."""
    return " ".join(_WORD.findall(base_form(text))[:3])
