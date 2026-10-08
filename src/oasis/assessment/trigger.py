"""When to offer PHQ-9 or GAD-7: readiness score over a sliding window, plus guards (design §3).

Per user turn, evidence e = min(cap, sum of weights of the symptom domains it mentions).
Readiness R is the linearly decayed mean of e over the last W user turns. An offer is made
on an explicit request, or when R stays at or above the threshold for k turns in a row,
and only if every guard passes. The stored reason is a code plus the numbers behind it.
"""

from __future__ import annotations

import datetime
import functools
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from oasis.safety.normalize import base_form
from oasis.types import ACTIVE_STATUSES, AssessmentRecord, InstrumentId, TurnRecord


@dataclass(frozen=True)
class Domain:
    name: str
    instrument: InstrumentId | None
    weight: float
    regex: re.Pattern[str]


@dataclass(frozen=True)
class TriggerConfig:
    window: int
    threshold: float
    consecutive: int
    decline_cooldown: datetime.timedelta
    repeat_after: datetime.timedelta
    paused_expiry: datetime.timedelta
    max_evidence: float
    domains: tuple[Domain, ...]
    explicit_request: re.Pattern[str]
    anxiety_request: re.Pattern[str]
    first_person: re.Pattern[str]
    third_person: re.Pattern[str]


@dataclass(frozen=True)
class Offer:
    instrument: InstrumentId
    reason: str  # JSON


@functools.cache
def config() -> TriggerConfig:
    text = (resources.files("oasis.content") / "assessment" / "trigger.yaml").read_text(
        encoding="utf-8"
    )
    raw: dict[str, Any] = yaml.safe_load(text)
    return TriggerConfig(
        window=int(raw["window"]),
        threshold=float(raw["threshold"]),
        consecutive=int(raw["consecutive"]),
        decline_cooldown=datetime.timedelta(hours=raw["decline_cooldown_hours"]),
        repeat_after=datetime.timedelta(days=raw["repeat_after_days"]),
        paused_expiry=datetime.timedelta(hours=raw["paused_expiry_hours"]),
        max_evidence=float(raw["max_evidence"]),
        domains=tuple(
            Domain(name, d["instrument"], float(d["weight"]), re.compile(d["pattern"]))
            for name, d in raw["domains"].items()
        ),
        explicit_request=re.compile(raw["explicit_request"]),
        anxiety_request=re.compile(raw["anxiety_request"]),
        first_person=re.compile(raw["first_person"]),
        third_person=re.compile(raw["third_person"]),
    )


def cues(text: str, cfg: TriggerConfig) -> list[Domain]:
    """Domains mentioned in one message; none when it is about someone else."""
    norm = base_form(text)
    if cfg.third_person.search(norm) and not cfg.first_person.search(norm):
        return []
    return [d for d in cfg.domains if d.regex.search(norm)]


def readiness(evidence: Sequence[float], window: int) -> float:
    """Linearly decayed mean of the last `window` evidence values (newest last)."""
    weights = [1 - k / window for k in range(window)]
    recent = list(reversed(evidence[-window:]))
    return sum(w * e for w, e in zip(weights, recent, strict=False)) / sum(weights)


def decide(
    history: Sequence[TurnRecord],
    message: str,
    records: Sequence[AssessmentRecord],
    now: datetime.datetime,
) -> Offer | None:
    cfg = config()
    if any(t.role == "placeholder" for t in history) or _blocked(records, now, cfg):
        return None

    norm = base_form(message)
    if cfg.explicit_request.search(norm):
        inst: InstrumentId = "GAD7" if cfg.anxiety_request.search(norm) else "PHQ9"
        if _recently_completed(records, inst, now, cfg):
            return None
        return Offer(inst, json.dumps({"reason": "explicit_request"}))

    messages = [t.content for t in history if t.role == "user"] + [message]
    per_turn = [cues(m, cfg) for m in messages]
    evidence = [min(cfg.max_evidence, sum(d.weight for d in ds)) for ds in per_turn]
    scores = [readiness(evidence[: len(evidence) - k], cfg.window) for k in range(cfg.consecutive)]
    if len(evidence) < cfg.consecutive or min(scores) < cfg.threshold:
        return None

    window = per_turn[-cfg.window :]
    inst = _instrument(window)
    if _recently_completed(records, inst, now, cfg):
        return None
    counts: dict[str, int] = {}
    for d in (d for ds in window for d in ds if d.instrument):
        counts[d.name] = counts.get(d.name, 0) + 1
    top = sorted(counts, key=lambda n: (-counts[n], n))[:3]
    reason = {"reason": "sustained_readiness", "R": round(scores[0], 3),
              "turns": cfg.consecutive, "top_domains": top}  # fmt: skip
    return Offer(inst, json.dumps(reason))


def _instrument(window: Iterable[list[Domain]]) -> InstrumentId:
    totals = {"PHQ9": 0.0, "GAD7": 0.0}
    for ds in window:
        for d in ds:
            if d.instrument:
                totals[d.instrument] += d.weight
    return "GAD7" if totals["GAD7"] > totals["PHQ9"] else "PHQ9"  # tie -> PHQ-9


def _blocked(
    records: Sequence[AssessmentRecord], now: datetime.datetime, cfg: TriggerConfig
) -> bool:
    for r in records:
        if r.status in ACTIVE_STATUSES:
            return True
        if r.status == "declined" and now - _when(r) < cfg.decline_cooldown:
            return True
    return False


def _recently_completed(
    records: Sequence[AssessmentRecord], inst: str, now: datetime.datetime, cfg: TriggerConfig
) -> bool:
    return any(
        r.instrument == inst and r.status == "scored" and now - _when(r) < cfg.repeat_after
        for r in records
    )


def _when(r: AssessmentRecord) -> datetime.datetime:
    return datetime.datetime.fromisoformat(r.completed_at or r.created_at)


def evaluate(conversations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score the trigger on labelled conversations (design §3.3); see trigger_eval.py."""
    now = datetime.datetime.now(datetime.UTC)
    tp = fp = fn = tn = 0
    latencies: list[int] = []
    rows = []
    for conv in conversations:
        offered_at, offered = None, None
        history: list[TurnRecord] = []
        for i, msg in enumerate(conv["turns"]):
            offer = decide(history, msg, (), now)
            if offer:
                offered_at, offered = i, offer.instrument
                break
            history.append(TurnRecord(str(i), i, "user", msg, None, ""))
        early = offered_at is not None and offered_at < conv.get("earliest", 0)
        if conv["should_offer"] and offered_at is not None and not early:
            tp += 1
            latencies.append(offered_at - conv["earliest"])
            outcome = "TP" if offered == conv.get("instrument") else "TP (other instrument)"
        elif offered_at is not None:
            fp += 1
            outcome = "FP (too early)" if conv["should_offer"] else "FP"
        elif conv["should_offer"]:
            fn += 1
            outcome = "FN"
        else:
            tn += 1
            outcome = "TN"
        rows.append({"id": conv["id"], "outcome": outcome, "offered_at": offered_at,
                     "instrument": offered})  # fmt: skip
    return {
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "mean_latency_turns": sum(latencies) / len(latencies) if latencies else None,
        "conversations": rows,
    }  # fmt: skip
