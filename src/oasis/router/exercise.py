"""Exercise scripts for the structured modes: loading, and one step per turn (CR-12).

A running exercise is just `RouterState.exercise` (which script) and `.step` (the next step
to show), so it survives a reload with the rest of the router memory.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from importlib import resources
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.types import ExerciseCard, Mode, RouterState

EXERCISE_MODES = frozenset({"cbt", "dbt", "mindfulness", "grounding"})


@dataclass(frozen=True)
class Technique:
    id: str
    mode: Mode
    name: str
    offer: str
    steps: tuple[str, ...]
    source: str
    version: str
    review_status: str


def parse(raw: Mapping[str, Any]) -> Technique:
    steps = raw.get("steps")
    if raw.get("mode") not in EXERCISE_MODES or not isinstance(steps, list) or not steps:
        raise ValueError(f"technique {raw.get('id')}: needs a structured mode and steps")
    require_review(raw, f"technique {raw.get('id')}")
    fields = ("id", "name", "offer", "source", "version")
    if not all(isinstance(raw.get(f), str) and raw[f] for f in fields):
        raise ValueError(f"technique {raw.get('id')}: missing {fields}")
    return Technique(raw["id"], raw["mode"], raw["name"], raw["offer"],
                     tuple(str(s) for s in steps), raw["source"], raw["version"],
                     raw["review_status"])  # fmt: skip


@functools.cache
def load_all() -> dict[str, Technique]:
    folder = resources.files("oasis.content") / "techniques"
    return index(
        parse(load_yaml("techniques", f.name)) for f in folder.iterdir() if f.name.endswith(".yaml")
    )


def index(found: Iterable[Technique]) -> dict[str, Technique]:
    found = list(found)
    if sorted(t.mode for t in found) != sorted(EXERCISE_MODES):
        raise ValueError("exactly one technique per structured mode is expected")
    return {t.id: t for t in found}


def technique_for(mode: str) -> Technique:
    return next(t for t in load_all().values() if t.mode == mode)


def start(rs: RouterState, technique_id: str) -> RouterState:
    return replace(rs, exercise=technique_id, step=0)


def deliver(rs: RouterState) -> tuple[str, RouterState, ExerciseCard | None]:
    """The next step's text, the state after it, and the card (None once the last step is out)."""
    if rs.exercise is None:
        raise ValueError("no exercise running")
    t = load_all()[rs.exercise]
    text, nxt = t.steps[rs.step], rs.step + 1
    if nxt >= len(t.steps):
        return text, replace(rs, exercise=None, step=0), None
    card = ExerciseCard("active", rs.current, t.name, nxt, len(t.steps))
    return text, replace(rs, step=nxt), card


def card_for(rs: RouterState) -> ExerciseCard | None:
    """The card an open offer or a running exercise shows right now (used after a reload)."""
    if rs.offered is not None:
        return ExerciseCard("offer", rs.offered, technique_for(rs.offered).name)
    if rs.exercise is not None:
        t = load_all()[rs.exercise]
        return ExerciseCard("active", rs.current, t.name, rs.step, len(t.steps))
    return None
