"""Signal detectors: lexicon scorers, VADER valence and the opt-out cue (design §5).

Golden messages pin what each cue picks up; the neutral set pins what it must ignore.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from oasis.core.detectors.lexicon import ContentError, load, parse, segments
from oasis.core.signals import EMOTIONS, extract, valence
from oasis.router.weights import config

BURNS = {
    "all_or_nothing", "overgeneralisation", "mental_filter", "disqualifying_positive",
    "mind_reading", "fortune_telling", "magnification", "emotional_reasoning",
    "should_statements", "labelling", "personalisation",
}  # fmt: skip


def test_venting_is_a_companion_cue() -> None:
    s = extract("I just want to vent about my day")
    assert s.wants_to_talk >= 0.5
    assert s.distortion == 0.0
    assert s.dysregulation == 0.0


def test_self_labelling_and_overgeneralising_are_distortions() -> None:
    s = extract("I'm such a failure, I always mess everything up")
    assert s.distortion >= 0.5
    assert {"labelling", "overgeneralisation"} <= s.distortion_types


@pytest.mark.parametrize(("message", "category"), [
    ("Everyone thinks I'm stupid", "mind_reading"),
    ("It's going to be a total disaster, I know it", "fortune_telling"),
    ("It's all my fault that they argued", "personalisation"),
    ("I should be able to handle this on my own", "should_statements"),
    ("It doesn't count, anyone could have done it", "disqualifying_positive"),
    ("If I'm not perfect I'm a complete failure", "all_or_nothing"),
    ("This is the worst thing that could ever happen", "magnification"),
    ("I feel like a fraud so I must be one", "emotional_reasoning"),
    ("One mistake ruined the whole day, that's all I can think about", "mental_filter"),
])  # fmt: skip
def test_each_burns_category_has_a_working_example(message: str, category: str) -> None:
    assert category in extract(message).distortion_types


def test_acute_overwhelm_reaches_the_router_threshold() -> None:
    s = extract("I can't breathe, everything is too much, I'm falling apart")
    assert s.overwhelm >= config().acute_threshold


def test_mild_overwhelm_stays_below_the_acute_threshold() -> None:
    s = extract("Work has been a bit overwhelming this week but I'm managing it okay")
    assert 0.0 < s.overwhelm < config().acute_threshold


def test_losing_control_is_dysregulation() -> None:
    s = extract("I'm so angry I want to smash something, I can't control it")
    assert s.dysregulation >= 0.5
    assert s.emotions["anger"] > 0.0


@pytest.mark.parametrize(("message", "emotion"), [
    ("I feel so sad and empty today", "sadness"),
    ("I'm anxious and worried about tomorrow", "anxiety"),
    ("I'm furious with my brother", "anger"),
    ("I'm so ashamed of what I did", "shame"),
    ("I feel so lonely, nobody cares about me", "loneliness"),
])  # fmt: skip
def test_each_emotion_lexicon_fires(message: str, emotion: str) -> None:
    assert extract(message).emotions[emotion] > 0.0


@pytest.mark.parametrize("message", [
    "I had pasta for lunch and watched a film",
    "The train was on time this morning",
    "Can you tell me more about how this works?",
    "We went for a walk in the park",
])  # fmt: skip
def test_ordinary_talk_raises_no_cue(message: str) -> None:
    s = extract(message)
    assert (s.distortion, s.dysregulation, s.overwhelm, s.wants_to_talk) == (0.0, 0.0, 0.0, 0.0)
    assert set(s.emotions.values()) == {0.0}
    assert not s.opt_out


def test_every_emotion_is_always_present() -> None:
    assert set(extract("hello").emotions) == set(EMOTIONS)


def test_valence_follows_the_vader_baseline() -> None:
    assert valence("I feel hopeless and alone") < -0.3
    assert valence("That was a lovely day") > 0.3
    assert extract("I feel hopeless and alone").valence == valence("I feel hopeless and alone")


@pytest.mark.parametrize("message", [
    # Demo testers' messages that plain VADER scored as positive (2026-10-29).
    "Even sleep feels horrible for me , because i get dreams like someone haunting me and "
    "saying I am not getting any job and I can't get any job and life is no horrible",
    "Eating less feels like keeping my self hungry for hours and moving more feels like over "
    "enthusiastic",
    "Would you sponsor me the knife or rope to hand",
    "I taught of cutting rope with the knife not to die for that also i need to meet doctor",
])  # fmt: skip
def test_negative_messages_are_never_scored_positive(message: str) -> None:
    assert valence(message) <= 0


def test_valence_fixes_keep_ordinary_uses() -> None:
    """ "like" as a verb still counts, and a negated good word still turns negative."""
    assert valence("I like this song") > 0
    assert valence("I am not happy") < 0
    assert valence("I am so happy today") > 0
    assert valence("Getting a job will make me comfortable") > 0
    assert valence("Getting a job will make me comfortabale") == 0  # a typo is unknown


@pytest.mark.parametrize(("message", "expected"), [
    ("Can we stop the exercise?", True),
    ("I don't want to do this anymore", True),
    ("Let's stop here please", True),
    ("I stopped at the shop on the way home", False),
    ("My friend wants to stop smoking", False),
])  # fmt: skip
def test_opt_out_cue(message: str, expected: bool) -> None:
    assert extract(message).opt_out is expected


def test_obfuscated_spelling_is_normalised_first() -> None:
    assert extract("I'M SOOOO OVERWHELMED").overwhelm > 0.0


def test_a_cue_counts_for_less_in_a_longer_message() -> None:
    short = extract("I'm so overwhelmed")
    long = extract("I'm so overwhelmed, " + "and then we talked about the weather " * 3)
    assert 0.0 < long.overwhelm < short.overwhelm


@given(st.text(max_size=300))
def test_every_score_stays_in_range(text: str) -> None:
    s = extract(text)
    for value in (s.distortion, s.dysregulation, s.overwhelm, s.wants_to_talk,
                  *s.emotions.values()):  # fmt: skip
        assert 0.0 <= value <= 1.0
    assert -1.0 <= s.valence <= 1.0
    assert s.distortion_types <= BURNS


# --- content files ------------------------------------------------------------------------


def test_distortion_lexicon_has_exactly_the_burns_categories() -> None:
    assert set(load("distortions")) == BURNS


@pytest.mark.parametrize("name", ["emotions", "cues", "distortions"])
def test_lexicons_are_versioned_and_flagged_for_review(name: str) -> None:
    for lexicon in load(name).values():
        assert lexicon.review_status == "needs_clinician_review"
        assert lexicon.version
        assert lexicon.terms


def _raw(**over: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": "oasis.content/v1", "kind": "lexicon", "version": "1",
        "review_status": "needs_clinician_review",
        "scorers": {"x": {"bias": 0.0, "scale": 3.0, "terms": {r"\bsad\b": 1.0}}},
    }  # fmt: skip
    raw.update(over)
    return raw


@pytest.mark.parametrize("bad", [
    {"review_status": None},
    {"version": ""},
    {"scorers": {}},
    {"scorers": {"x": {"bias": 0.0, "scale": 3.0, "terms": {r"\bsad(": 1.0}}}},
    {"scorers": {"x": {"bias": 0.0, "scale": 3.0, "terms": {r"\bsad\b": "high"}}}},
    {"scorers": {"x": {"bias": 0.0, "scale": -1.0, "terms": {r"\bsad\b": 1.0}}}},
    {"scorers": {"x": {"bias": 0.0, "scale": 3.0, "terms": {}}}},
])  # fmt: skip
def test_invalid_lexicon_content_is_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ContentError):
        parse(_raw(**bad))


def test_valid_lexicon_content_parses() -> None:
    assert set(parse(_raw())) == {"x"}


# --- per-sentence scoring (Phase 12 bias evaluation) -----------------------------------


def test_sentences_dashes_and_a_leading_identity_clause_are_scored_apart() -> None:
    assert segments("im so angry. i live in leeds") == ("im so angry", " i live in leeds")
    assert segments("im so angry - aisha") == ("im so angry", "aisha")
    assert segments("as a muslim woman, im so angry") == ("as a muslim woman,", " im so angry")
    assert segments("at 68, work is hard") == ("at 68,", " work is hard")
    # Any other comma stays inside its sentence, so a single sentence scores as before.
    assert segments("im so angry, i cant control it") == ("im so angry, i cant control it",)
    assert segments("...") == ("...",)


@pytest.mark.parametrize(
    "extra",
    [". My husband and I live in Leeds.", " - Aisha", ". It's Diwali this week."],
)
def test_who_someone_is_does_not_water_down_how_they_feel(extra: str) -> None:
    plain = extract("I'm so angry I can't control it")
    for framed in (extract("I'm so angry I can't control it" + extra),
                   extract("As a Muslim woman, I'm so angry I can't control it")):  # fmt: skip
        assert framed.emotions == plain.emotions
        assert framed.dysregulation == plain.dysregulation
        assert framed.overwhelm == plain.overwhelm


def test_a_single_sentence_scores_exactly_as_before() -> None:
    lex = load("emotions")["anger"]
    norm = "im so angry and furious, i cant control it"
    assert lex.score(norm) == min(1.0, max(0.0, lex.linear(norm, len(norm.split()))))


def test_the_highest_sentence_counts() -> None:
    lex = load("emotions")["anger"]
    assert lex.score("i had lunch. im so angry") == lex.score("im so angry")
