"""Hand-weighted lexicon scorers (design §5).

score(x) = clip(b + scale * sum_i w_i * count_i(s) / max(1, n_tokens(s)), 0, 1)

where s is the highest-scoring segment of x (a sentence, see `segments`). Features are
term-count rates, so the pre-clip value is a linear model of s and its explanation is exact
(design §10). Patterns are matched against the safety normaliser's base form
(casefolded, apostrophes removed, stretched letters collapsed), so "can't" is written "cant".
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from oasis.content import load_yaml

# Scores are rates per word, so every word added waters a score down. Words that only say who
# someone is or where they live ("As a Muslim woman, ...", "... - Aisha", "My wife and I live
# in Lagos.") must not change what OASIS does (Phase 12 bias evaluation), so each sentence,
# each part after a dash, and a leading "As a ..." or "At 68," clause is scored on its own and
# the highest score is used. Other commas stay inside their sentence, so a one-sentence
# message scores exactly as before.
_SENTENCE = re.compile(r"[.!?;\n]+|\s[-\u2013\u2014]+\s")
_FRAMING = re.compile(r"^\s*(?:as (?:a|an) [^,]{1,40}|at \d{1,3}),")


def segments(norm: str) -> tuple[str, ...]:
    """The parts of a normalised message that are scored separately."""
    parts: list[str] = []
    for sentence in _SENTENCE.split(norm):
        framing = _FRAMING.match(sentence)
        parts += [sentence[: framing.end()], sentence[framing.end() :]] if framing else [sentence]
    return tuple(p for p in parts if p.split()) or (norm,)


class ContentError(ValueError):
    """A lexicon file is invalid; raised at startup, never mid-turn."""


@dataclass(frozen=True)
class Lexicon:
    name: str
    bias: float
    scale: float
    terms: tuple[tuple[re.Pattern[str], float], ...]
    version: str
    review_status: str

    def counts(self, norm: str) -> tuple[int, ...]:
        """Each term's number of matches, in file order."""
        return tuple(len(p.findall(norm)) for p, _ in self.terms)

    def linear(self, norm: str, n_tokens: int, counts: tuple[int, ...] | None = None) -> float:
        """The pre-clip value: the linear model the explanation decomposes (design §10.1).
        `counts` skips the matching when the caller already has them."""
        found = self.counts(norm) if counts is None else counts
        rate = sum(w * k for (_, w), k in zip(self.terms, found, strict=True)) / max(1, n_tokens)
        return self.bias + self.scale * rate

    def segment(self, norm: str) -> str:
        """The part of the message this scorer is computed on: its highest-scoring segment
        (the first, on a tie). For one sentence, the whole message."""
        parts = segments(norm)
        return max(parts, key=lambda p: self.linear(p, len(p.split())))

    def score(self, norm: str) -> float:
        part = self.segment(norm)
        return min(1.0, max(0.0, self.linear(part, len(part.split()))))

    def rates(self, norm: str, n_tokens: int) -> tuple[float, ...]:
        """The feature vector x: each term's count per token, in file order."""
        return tuple(k / max(1, n_tokens) for k in self.counts(norm))


def parse(raw: Mapping[str, Any]) -> dict[str, Lexicon]:
    version, status = raw.get("version"), raw.get("review_status")
    if not version or not status:
        raise ContentError("lexicon needs version and review_status")
    scorers = raw.get("scorers")
    if not isinstance(scorers, Mapping) or not scorers:
        raise ContentError("lexicon has no scorers")
    out = {}
    for name, spec in scorers.items():
        terms = spec.get("terms")
        if not isinstance(terms, Mapping) or not terms:
            raise ContentError(f"{name}: no terms")
        try:
            bias, scale = float(spec["bias"]), float(spec["scale"])
            compiled = tuple((re.compile(p), float(w)) for p, w in terms.items())
        except (KeyError, TypeError, ValueError, re.error) as exc:
            raise ContentError(f"{name}: {type(exc).__name__}") from exc
        if scale <= 0:
            raise ContentError(f"{name}: scale must be positive")
        out[name] = Lexicon(name, bias, scale, compiled, str(version), str(status))
    return out


@functools.cache
def load(name: str) -> dict[str, Lexicon]:
    return parse(load_yaml("lexicons", f"{name}.yaml"))
