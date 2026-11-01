"""Aggregation of the per-turn features (design §9.2, FR-TRK-2).

Per-session mean and sample variance of every feature, an exponentially weighted trend over
session mean valence, and a change flag against the user's own earlier sessions. Pure, and
recomputed from the stored features on each request, so nothing here is stored.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from oasis.tracking.features import FEATURES, TrackingConfig
from oasis.types import SignalRecord


@dataclass(frozen=True)
class SessionSummary:
    session: int  # 1-based, in order of each session's first turn
    started_at: str
    turns: int
    mean: Mapping[str, float | None]  # None: the feature had no value in this session
    variance: Mapping[str, float | None]  # None: fewer than two values
    valence: tuple[float, ...] = ()  # turn by turn, for the conversation's own graph
    is_current: bool = False  # the conversation the request came from


@dataclass(frozen=True)
class Trend:
    label: str
    sessions: list[SessionSummary]
    ewma: list[float]  # over session mean valence
    change_flags: list[bool]
    current: list[tuple[str, float]]  # this session's turns: (time, valence)


def summarise(records: Sequence[SignalRecord], current: str = "") -> list[SessionSummary]:
    by_session: dict[str, list[SignalRecord]] = {}
    for r in sorted(records, key=lambda r: r.created_at):
        by_session.setdefault(r.session_hash, []).append(r)
    out = []
    for i, (session_hash, recs) in enumerate(by_session.items(), start=1):
        mean: dict[str, float | None] = {}
        variance: dict[str, float | None] = {}
        for name in FEATURES:
            values = [float(v) for r in recs if (v := getattr(r.features, name)) is not None]
            mean[name] = statistics.fmean(values) if values else None
            variance[name] = statistics.variance(values) if len(values) > 1 else None
        valence = tuple(r.features.valence for r in recs)
        out.append(SessionSummary(i, recs[0].created_at, len(recs), mean, variance, valence,
                                  session_hash == current))  # fmt: skip
    return out


def ewma(values: Sequence[float], alpha: float) -> list[float]:
    """e_1 = x_1; e_t = alpha * x_t + (1 - alpha) * e_(t-1)."""
    out: list[float] = []
    for x in values:
        out.append(x if not out else alpha * x + (1 - alpha) * out[-1])
    return out


def change_flags(values: Sequence[float], k: int, z: float) -> list[bool]:
    """A value is flagged when at least k values come before it and it lies more than z
    sample SDs from their mean. A baseline with no spread flags nothing."""
    flags = []
    for i, x in enumerate(values):
        base = values[:i]
        flag = False
        if len(base) >= k:
            sd = statistics.stdev(base)
            flag = sd > 0 and abs(x - statistics.fmean(base)) > z * sd
        flags.append(flag)
    return flags


def trend(records: Sequence[SignalRecord], session_hash: str, cfg: TrackingConfig) -> Trend:
    sessions = summarise(records, session_hash)
    means = [s.mean["valence"] or 0.0 for s in sessions]  # every turn has a valence
    current = [(r.created_at, r.features.valence)
               for r in sorted(records, key=lambda r: r.created_at)
               if r.session_hash == session_hash]  # fmt: skip
    return Trend(
        cfg.label,
        sessions,
        ewma(means, cfg.ewma_alpha),
        change_flags(means, cfg.baseline_sessions, cfg.change_z),
        current,
    )
