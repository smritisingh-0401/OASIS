"""One message in, one frozen Signals record out (design §5). Pure and LLM-free."""

from __future__ import annotations

from oasis.core.detectors.lexicon import load
from oasis.core.detectors.valence import valence
from oasis.safety.normalize import base_form
from oasis.types import Signals

EMOTIONS = ("sadness", "anxiety", "anger", "shame", "loneliness")


def load_all() -> None:
    """Parse every lexicon now, so a bad file stops the app at startup."""
    for name in ("emotions", "cues", "distortions"):
        load(name)


def extract(message: str) -> Signals:
    norm = base_form(message)
    n = len(norm.split())
    emotions, cues, distortions = load("emotions"), load("cues"), load("distortions")
    by_type = {name: lex.score(norm, n) for name, lex in distortions.items()}
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
    )
