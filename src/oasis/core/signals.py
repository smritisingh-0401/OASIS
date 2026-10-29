"""One message in, one frozen Signals record out (design §5). Pure and LLM-free."""

from __future__ import annotations

import functools
import re
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from oasis.core.detectors.lexicon import load
from oasis.guard.checks import FIRST_PERSON, content_words, harsh_label
from oasis.safety.normalize import base_form
from oasis.types import Signals

EMOTIONS = ("sadness", "anxiety", "anger", "shame", "loneliness")
LABEL_TERM = 3.0 * 1.5  # labelling scorer scale x a labelling term's weight (distortions.yaml)

_CLAUSE = re.compile(r"[,.;:!?]+|\b(?:and|but)\b")


# "like" is a positive verb only after one of these ("I like", "would like", "don't like").
_LIKE_SUBJECTS = frozenset(
    [
        "i",
        "you",
        "we",
        "they",
        "he",
        "she",
        "people",
        "everyone",
        "really",
        "would",
        "do",
        "does",
        "did",
        "dont",
        "doesnt",
        "didnt",
        "don't",
        "doesn't",
        "didn't",
        "to",
        "also",
        "still",
        "actually",
        "i'd",
        "id",
        "we'd",
        "you'd",
    ]
)


class _MoodVader(SentimentIntensityAnalyzer):
    """VADER with the fixes from demo testing (2026-10-29, CR-21): "like" as a comparison
    ("feels like") and "hand" score nothing, a negated bad word ("not to die", "no horrible")
    and a good word after "over" or "too" are neutral instead of positive."""

    def sentiment_valence(
        self, valence: float, sentitext: Any, item: str, i: int, sentiments: list[float]
    ) -> list[float]:
        words = [w.lower() for w in sentitext.words_and_emoticons]
        word = item.lower()
        comparison = word in ("like", "likes") and (i == 0 or words[i - 1] not in _LIKE_SUBJECTS)
        if comparison or word in ("hand", "hands"):
            sentiments.append(0.0)
            return sentiments
        sentiments = super().sentiment_valence(valence, sentitext, item, i, sentiments)
        own = self.lexicon.get(word, 0.0)
        excess = own > 0 and i > 0 and words[i - 1] in ("over", "too")
        if (own < 0 < sentiments[-1]) or excess:
            sentiments[-1] = 0.0
        return sentiments


@functools.cache
def _mood_vader() -> _MoodVader:
    return _MoodVader()


def valence(text: str) -> float:
    """VADER compound score in [-1, 1]: the valence baseline (design §5), with the
    demo-testing fixes in `_MoodVader`. A misspelled word is unknown to VADER, so neutral:
    correcting it without a dictionary misread real words ("brother" as "bother")."""
    return float(_mood_vader().polarity_scores(text)["compound"])


def load_all() -> None:
    """Parse every lexicon now, so a bad file stops the app at startup."""
    for name in ("emotions", "cues", "distortions"):
        load(name)


def claims(message: str) -> tuple[frozenset[str], ...]:
    """Each clause of `message` holding a thinking-trap phrase, as its content words
    (design §8.1). The guard compares replies against these; they are never stored."""
    patterns = [p for lex in load("distortions").values() for p, _ in lex.terms]
    found: list[frozenset[str]] = []
    for clause in _CLAUSE.split(base_form(message)):
        words = content_words(clause)
        trap = any(p.search(clause) for p in patterns) or harsh_label(clause, FIRST_PERSON)
        if words and words not in found and trap:
            found.append(words)
    return tuple(found)


def harsh_label_score(norm: str, n: int) -> float:
    """An unlisted harsh label ("I'm a horrible person") scores like one labelling term."""
    return min(1.0, LABEL_TERM / max(n, 1)) if harsh_label(norm, FIRST_PERSON) else 0.0


def extract(message: str) -> Signals:
    norm = base_form(message)
    n = len(norm.split())
    emotions, cues, distortions = load("emotions"), load("cues"), load("distortions")
    by_type = {name: lex.score(norm) for name, lex in distortions.items()}
    by_type["labelling"] = max(by_type["labelling"], harsh_label_score(norm, n))
    return Signals(
        valence=valence(message),
        emotions={e: emotions[e].score(norm) for e in EMOTIONS},
        dysregulation=cues["dysregulation"].score(norm),
        # Sum, not max: several categories in one message add up, and the sum is still a
        # linear model before the clip, so its explanation stays exact.
        distortion=min(1.0, sum(by_type.values())),
        distortion_types=frozenset(t for t, v in by_type.items() if v > 0),
        overwhelm=cues["overwhelm"].score(norm),
        wants_to_talk=cues["wants_to_talk"].score(norm),
        opt_out=cues["opt_out"].score(norm) > 0,
        psychoed_cue=cues["psychoed"].score(norm) > 0,
        asks_advice=cues["asks_advice"].score(norm) > 0,
    )
