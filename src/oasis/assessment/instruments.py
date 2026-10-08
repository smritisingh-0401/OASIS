"""PHQ-9 and GAD-7: published items, options and bands, and scoring (design §4, rules CL1).

The content files are validated when first loaded; the app loads them at startup, so bad
content stops the app instead of failing mid-questionnaire.
"""

from __future__ import annotations

import datetime
import functools
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any, get_args

import yaml

from oasis.types import InstrumentId

INSTRUMENT_IDS: tuple[InstrumentId, ...] = get_args(InstrumentId)
OPTIONS = ("Not at all", "Several days", "More than half the days", "Nearly every day")


@dataclass(frozen=True)
class Band:
    low: int
    high: int
    label: str


@dataclass(frozen=True)
class Instrument:
    id: InstrumentId
    name: str
    stem: str
    options: tuple[str, ...]
    items: tuple[str, ...]
    functional_question: str | None
    functional_options: tuple[str, ...]
    bands: tuple[Band, ...]
    source: str

    @property
    def max_total(self) -> int:
        return 3 * len(self.items)


def score(inst: Instrument, answers: Sequence[int]) -> tuple[int, str]:
    """Total and band. Only a complete set of 0-3 answers is ever scored."""
    if len(answers) != len(inst.items):
        raise ValueError(f"{inst.id}: incomplete answers")
    if any(a not in (0, 1, 2, 3) for a in answers):
        raise ValueError(f"{inst.id}: answers must be 0-3")
    total = sum(answers)
    return total, next(b.label for b in inst.bands if b.low <= total <= b.high)


def load_instrument(inst_id: InstrumentId, text: str | None = None) -> Instrument:
    if text is None:
        text = _content(f"{inst_id.lower()}.yaml")
    raw = yaml.safe_load(text)
    try:
        return _validate(inst_id, raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{inst_id}: invalid instrument file: {exc}") from None


def _validate(inst_id: InstrumentId, raw: dict[str, Any]) -> Instrument:
    if raw["instrument"] != inst_id:
        raise ValueError("instrument id does not match the file")
    if tuple(raw["options"]) != OPTIONS:
        raise ValueError("options must be the four published response options")
    items = tuple(str(i) for i in raw["items"])
    if not items:
        raise ValueError("no items")
    if not str(raw["source"]).startswith("https://"):
        raise ValueError("source must be an https URL")
    verified = raw["verified_on"]
    if not isinstance(verified, datetime.date) or verified > datetime.date.today():
        raise ValueError("verified_on must be a date not in the future")
    bands = tuple(Band(int(b["min"]), int(b["max"]), str(b["label"])) for b in raw["bands"])
    expected = 0
    for band in bands:  # contiguous, in order, covering 0..max exactly once
        if band.low != expected or band.high < band.low:
            raise ValueError("bands must be contiguous from 0")
        expected = band.high + 1
    if expected != 3 * len(items) + 1:
        raise ValueError("bands must end at the maximum total")
    functional = raw.get("functional")
    return Instrument(
        id=inst_id,
        name=str(raw["name"]),
        stem=str(raw["stem"]),
        options=OPTIONS,
        items=items,
        functional_question=str(functional["question"]) if functional else None,
        functional_options=tuple(functional["options"]) if functional else (),
        bands=bands,
        source=str(raw["source"]),
    )


@functools.cache
def instrument(inst_id: str) -> Instrument:
    if inst_id not in INSTRUMENT_IDS:
        raise ValueError(f"unknown instrument {inst_id!r}")
    return load_instrument(inst_id)


@functools.cache
def texts() -> dict[str, Any]:
    """Result text per instrument and band, and the non-diagnostic disclaimer (CR-08)."""
    doc: dict[str, Any] = yaml.safe_load(_content("result_text.yaml"))
    for inst_id in INSTRUMENT_IDS:
        missing = {b.label for b in instrument(inst_id).bands} - set(doc[inst_id])
        if missing:
            raise ValueError(f"result_text.yaml: {inst_id} has no text for {sorted(missing)}")
    return doc


def load_all() -> None:
    """Load and validate every assessment file now (called at startup)."""
    for inst_id in INSTRUMENT_IDS:
        instrument(inst_id)
    texts()


def _content(name: str) -> str:
    return (resources.files("oasis.content") / "assessment" / name).read_text(encoding="utf-8")
