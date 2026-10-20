"""Per-turn language features of a user message (design §9.1, FR-TRK-1).

Pure and LLM-free: the engine passes the message, the signals it already extracted and the
turn's timestamps. Only numbers come out; the message itself is never kept.
"""

from __future__ import annotations

import datetime
import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.types import Signals, TurnFeatures

LABEL = "language-based mood trend, not a clinical measure"
FEATURES = tuple(f.name for f in fields(TurnFeatures))
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")
_STRAIGHT = {0x2018: "'", 0x2019: "'"}  # curly apostrophes count as straight ones


@dataclass(frozen=True)
class FeatureInfo:
    source: str | None  # a checked citation, or None when exploratory
    note: str | None  # what the source does and does not show
    exploratory: bool


@dataclass(frozen=True)
class TrackingConfig:
    label: str
    ewma_alpha: float
    baseline_sessions: int
    change_z: float
    latency_cap_s: float
    first_person: frozenset[str]
    absolutist: frozenset[str]
    not_before: frozenset[str]
    features: Mapping[str, FeatureInfo]


def parse(raw: Mapping[str, Any]) -> TrackingConfig:
    what = "tracking features"
    require_review(raw, what)
    if raw.get("label") != LABEL:
        raise ValueError(f"{what}: the label must read {LABEL!r} (FR-TRK-3)")
    items = raw.get("features") or {}
    if set(items) != set(FEATURES):
        raise ValueError(f"{what}: features must be exactly {FEATURES}")
    info = {}
    for name, item in items.items():
        source, exploratory = (item or {}).get("source"), (item or {}).get("exploratory") is True
        if bool(source) == exploratory:
            raise ValueError(f"{what}: {name} needs a source or exploratory: true (FR-TRK-4)")
        info[name] = FeatureInfo(source or None, (item or {}).get("note"), exploratory)
    agg = raw["aggregation"]
    cfg = TrackingConfig(
        label=LABEL,
        ewma_alpha=float(agg["ewma_alpha"]),
        baseline_sessions=int(agg["baseline_sessions"]),
        change_z=float(agg["change_z"]),
        latency_cap_s=float(agg["latency_cap_s"]),
        first_person=_words(raw, "first_person"),
        absolutist=_words(raw, "absolutist"),
        not_before=_words(raw, "not_before"),
        features=info,
    )
    # A baseline SD needs at least two sessions.
    if not (0 < cfg.ewma_alpha <= 1 and cfg.baseline_sessions >= 2 and cfg.change_z > 0
            and cfg.latency_cap_s > 0):  # fmt: skip
        raise ValueError(f"{what}: aggregation values out of range")
    if not (cfg.first_person and cfg.absolutist):
        raise ValueError(f"{what}: the first-person and absolutist word lists are required")
    return cfg


def _words(raw: Mapping[str, Any], key: str) -> frozenset[str]:
    return frozenset(str(w).lower() for w in raw.get(key) or ())


@functools.cache
def load_config() -> TrackingConfig:
    return parse(load_yaml("tracking", "features.yaml"))


def turn_features(
    message: str,
    signals: Signals,
    *,
    received_at: datetime.datetime,
    last_reply_at: datetime.datetime | None,
    client_ts: datetime.datetime | None,
    cfg: TrackingConfig | None = None,
) -> TurnFeatures:
    cfg = cfg or load_config()
    words = _WORD.findall(message.lower().translate(_STRAIGHT))
    n = len(words) or 1  # no words: both rates are 0
    absolutist = sum(
        w in cfg.absolutist and (i == 0 or words[i - 1] not in cfg.not_before)
        for i, w in enumerate(words)
    )
    latency = None
    if last_reply_at is not None:
        gap = (received_at - last_reply_at).total_seconds()
        latency = min(cfg.latency_cap_s, max(0.0, gap))
    e = signals.emotions
    return TurnFeatures(
        valence=signals.valence,
        sadness=e["sadness"],
        anxiety=e["anxiety"],
        anger=e["anger"],
        shame=e["shame"],
        loneliness=e["loneliness"],
        fp_pronoun_rate=sum(w in cfg.first_person for w in words) / n,
        absolutist_rate=absolutist / n,
        msg_length=len(words),
        reply_latency_s=latency,
        hour_of_day=client_ts.hour if client_ts else None,  # the client's own offset: local
    )
