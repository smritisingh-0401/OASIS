"""Router weights and the exact weighted-sum score per mode (design §7.1)."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.types import ROUTER_MODES, Contribution, ModeScore, RouterMode, Signals


@dataclass(frozen=True)
class ModeWeights:
    bias: float
    weights: Mapping[str, float]


@dataclass(frozen=True)
class RouterConfig:
    margin: float
    hysteresis_turns: int
    acute_threshold: float
    modes: Mapping[RouterMode, ModeWeights]
    version: str


def parse(raw: Mapping[str, Any]) -> RouterConfig:
    require_review(raw, "router weights")
    modes = raw["modes"]
    if set(modes) != set(ROUTER_MODES):
        raise ValueError(f"router weights must cover exactly {ROUTER_MODES}")
    cfg = RouterConfig(
        margin=float(raw["margin"]),
        hysteresis_turns=int(raw["hysteresis_turns"]),
        acute_threshold=float(raw["acute_overwhelm_threshold"]),
        modes={m: _mode(modes[m]) for m in ROUTER_MODES},
        version=str(raw["version"]),
    )
    if cfg.margin < 0 or cfg.hysteresis_turns < 1 or not 0 < cfg.acute_threshold <= 1:
        raise ValueError("router margin, hysteresis or acute threshold out of range")
    return cfg


def _mode(raw: Mapping[str, Any]) -> ModeWeights:
    return ModeWeights(float(raw["bias"]), {s: float(w) for s, w in raw["weights"].items()})


@functools.cache
def config() -> RouterConfig:
    return parse(load_yaml("router", "weights.yaml"))


def features(signals: Signals, extra: Mapping[str, float] | None = None) -> dict[str, float]:
    """The router's input vector x: every value in [0, 1]."""
    x = {
        "valence_neg": max(0.0, -signals.valence),
        **signals.emotions,
        "dysregulation": signals.dysregulation,
        "distortion": signals.distortion,
        "overwhelm": signals.overwhelm,
        "wants_to_talk": signals.wants_to_talk,
    }
    x.update(extra or {})
    return x


def score_modes(x: Mapping[str, float], cfg: RouterConfig) -> tuple[ModeScore, ...]:
    """Every mode's score with its exact contributions, highest score first.

    Ties keep ROUTER_MODES order, so companion (the default) wins a tie.
    """
    scores = []
    for mode in ROUTER_MODES:
        m = cfg.modes[mode]
        parts = [Contribution(s, w * x.get(s, 0.0)) for s, w in m.weights.items()]
        parts.sort(key=lambda c: -abs(c.value))
        scores.append(ModeScore(mode, m.bias + sum(c.value for c in parts), m.bias, tuple(parts)))
    return tuple(sorted(scores, key=lambda s: -s.score))  # stable: ties keep mode order
