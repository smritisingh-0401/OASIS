"""One message in, one frozen Signals record out (design §5). Pure and LLM-free."""

from __future__ import annotations

import re

from oasis.core.detectors.lexicon import load
from oasis.guard.checks import FIRST_PERSON, content_words, harsh_label, vader
from oasis.safety.normalize import base_form
from oasis.types import Signals

EMOTIONS = ("sadness", "anxiety", "anger", "shame", "loneliness")
LABEL_TERM = 3.0 * 1.5  # labelling scorer scale x a labelling term's weight (distortions.yaml)

_CLAUSE = re.compile(r"[,.;:!?]+|\b(?:and|but)\b")


def valence(text: str) -> float:
    """VADER compound score in [-1, 1]: the valence baseline (design §5)."""
    return float(vader().polarity_scores(text)["compound"])


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


def extract(message: str) -> Signals:
    norm = base_form(message)
    n = len(norm.split())
    emotions, cues, distortions = load("emotions"), load("cues"), load("distortions")
    by_type = {name: lex.score(norm, n) for name, lex in distortions.items()}
    if harsh_label(norm, FIRST_PERSON):
        # An unlisted harsh label ("I'm a horrible person") scores like one labelling term.
        by_type["labelling"] = max(by_type["labelling"], min(1.0, LABEL_TERM / max(n, 1)))
    return Signals(
        valence=valence(message),
        emotions={e: emotions[e].score(norm, n) for e in EMOTIONS},
        dysregulation=cues["dysregulation"].score(norm, n),
        # Sum, not max: several categories in one message add up, and the sum is still a
        # linear model before the clip, so its explanation stays exact.
        distortion=min(1.0, sum(by_type.values())),
        distortion_types=frozenset(t for t, v in by_type.items() if v > 0),
        overwhelm=cues["overwhelm"].score(norm, n),
        wants_to_talk=cues["wants_to_talk"].score(norm, n),
        opt_out=cues["opt_out"].score(norm, n) > 0,
        psychoed_cue=cues["psychoed"].score(norm, n) > 0,
        asks_advice=cues["asks_advice"].score(norm, n) > 0,
    )
