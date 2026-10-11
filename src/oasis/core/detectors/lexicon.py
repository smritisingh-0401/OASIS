"""Hand-weighted lexicon scorers (design §5).

score(x) = clip(b + scale * sum_i w_i * count_i(x) / max(1, n_tokens(x)), 0, 1)

Features are term-count rates, so the pre-clip value is a linear model and its explanation
is exact (design §10). Patterns are matched against the safety normaliser's base form
(casefolded, apostrophes removed, stretched letters collapsed), so "can't" is written "cant".
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from oasis.content import load_yaml


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

    def score(self, norm: str, n_tokens: int) -> float:
        rate = sum(w * len(p.findall(norm)) for p, w in self.terms) / max(1, n_tokens)
        return min(1.0, max(0.0, self.bias + self.scale * rate))


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
