"""Exact SHAP values for the linear lexicon scorers (design §10.1).

A scorer's pre-clip output is f(x) = b + sum_i c_i x_i, with x_i a term's count per token and
c_i = scale * w_i. With independent features and a background dataset, the SHAP value of each
term is phi_i = c_i (x_i - E[x_i]) and the base value is f(E[x]), which is exactly what
`shap.LinearExplainer` computes (tests/unit/test_explain.py checks it against the library).
Computing it here keeps numpy, scipy and pandas out of the app.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from oasis.content import load_yaml, require_review
from oasis.core.detectors.lexicon import Lexicon
from oasis.safety.normalize import base_form


@dataclass(frozen=True)
class FeatureValue:
    feature: str  # a lexicon term (its pattern) or a named rule, never user text
    phi: float


@dataclass(frozen=True)
class DetectorExplanation:
    detector: str  # "<lexicon file>.<scorer>", e.g. "distortions.overgeneralisation"
    output: float  # the scorer's pre-clip value, from the model formula (not from the phis)
    base: float
    features: tuple[FeatureValue, ...]  # every non-zero phi, largest |phi| first
    clipped: bool  # the score the router used was clipped to [0, 1]


@functools.cache
def neutral_corpus() -> tuple[str, ...]:
    raw = load_yaml("explain", "neutral.yaml")
    require_review(raw, "explanation background corpus")
    sentences = tuple(str(s) for s in raw["sentences"])
    if not sentences:
        raise ValueError("explanation background corpus is empty")
    return sentences


@functools.cache
def background(lex: Lexicon) -> tuple[float, ...]:
    """E[x_i]: each term's mean rate over the neutral corpus."""
    rows = [lex.rates(norm, len(norm.split())) for norm in map(base_form, neutral_corpus())]
    return tuple(sum(col) / len(rows) for col in zip(*rows, strict=True))


def explain_lexicon(detector: str, lex: Lexicon, norm: str, n: int) -> DetectorExplanation:
    coef = [lex.scale * w for _, w in lex.terms]
    mean = background(lex)
    x = lex.rates(norm, n)
    phis = [c * (xi - m) for c, xi, m in zip(coef, x, mean, strict=True)]
    base = lex.bias + sum(c * m for c, m in zip(coef, mean, strict=True))
    output = lex.bias + sum(c * xi for c, xi in zip(coef, x, strict=True))
    features = sorted(
        (FeatureValue(p.pattern, v) for (p, _), v in zip(lex.terms, phis, strict=True) if v),
        key=lambda f: -abs(f.phi),
    )
    return DetectorExplanation(detector, output, base, tuple(features), not 0.0 <= output <= 1.0)
