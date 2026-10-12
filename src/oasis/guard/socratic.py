"""Vetted Socratic fallback questions (design §8.3, FR-GRD-3, CR-15).

When a reply to a thinking-trap message (or any CBT or DBT reply) fails the guard twice, the
reply is one of these: an acknowledgement of the feeling, then exactly one question. The pick
follows the thinking trap and is deterministic for a given turn.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Any

from oasis.content import load_yaml, require_review

BANK_KEYS = ("all_or_nothing", "overgeneralisation", "mental_filter", "disqualifying_positive",
             "mind_reading", "fortune_telling", "magnification", "emotional_reasoning",
             "should_statements", "labelling", "personalisation", "general")  # fmt: skip

Bank = Mapping[str, tuple[str, ...]]


def parse_bank(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    require_review(raw, "socratic bank")
    questions = raw.get("questions") or {}
    out = {}
    for key in BANK_KEYS:
        listed = questions.get(key)
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"socratic bank: {key} needs a list of questions")
        for text in listed:
            if not isinstance(text, str) or text.count("?") != 1 or not text.endswith("?"):
                raise ValueError(f"socratic bank: {key} entries must end in exactly one question")
        out[key] = tuple(listed)
    return out


@functools.cache
def load_bank() -> Bank:
    return parse_bank(load_yaml("guard", "socratic_bank.yaml"))


def socratic_question(distortion_types: frozenset[str], seed: int) -> str:
    """The question for the first thinking trap found (alphabetical), else a general one."""
    bank = load_bank()
    key = next((t for t in sorted(distortion_types) if t in bank), "general")
    options = bank[key]
    return options[seed % len(options)]
