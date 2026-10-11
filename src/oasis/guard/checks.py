"""Reply checks every generated draft passes through (design §8.2, FR-CMP).

Each check enforces a plan rule the prompt already states, and its reason code is that rule's
name, so a retry can name it back in plain words. Companion replies are checked for
validate_first, one_question, no_praise and no_advice (only the rules the plan carries);
every mode is checked for no_dependency. The engine owns the retry and the fallback; Phase 7
adds the hypercompliance checks here.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.safety.normalize import base_form
from oasis.types import GuardVerdict, Plan

LISTED = ("validate_first", "no_praise", "no_advice", "no_dependency")
COMPANION_RULES = ("validate_first", "one_question", "no_praise", "no_advice")
# Form, not content: a draft failing only these is retried, but kept rather than replaced
# by the fixed fallback (the validating-phrase list cannot know every way to validate).
SOFT_RULES = frozenset({"validate_first", "one_question", "fresh_opener"})

Rules = Mapping[str, tuple[re.Pattern[str], ...]]


def parse(raw: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], ...]]:
    require_review(raw, "companion checks")
    patterns = raw.get("patterns") or {}
    out = {}
    for rule in LISTED:
        listed = patterns.get(rule)
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"companion checks: {rule} needs a list of patterns")
        try:
            out[rule] = tuple(re.compile(p) for p in listed)
        except (re.error, TypeError) as exc:
            raise ValueError(f"companion checks: bad pattern in {rule}") from exc
    return out


@functools.cache
def load_rules() -> Rules:
    return parse(load_yaml("companion", "checks.yaml"))


def check(draft: str, plan: Plan) -> GuardVerdict:
    rules = load_rules()
    norm = base_form(draft)
    failed = []
    if plan.mode == "companion":
        active = [r for r in COMPANION_RULES if r in plan.constraints]
        question = norm.find("?")
        before = norm if question < 0 else norm[:question]
        if "validate_first" in active and not _any(rules["validate_first"], before):
            failed.append("validate_first")
        if "one_question" in active and (norm.count("?") != 1 or not norm.rstrip().endswith("?")):
            failed.append("one_question")
        failed += [r for r in ("no_praise", "no_advice") if r in active and _any(rules[r], norm)]
        if opener(draft) in plan.avoid_openers:
            failed.append("fresh_opener")
    if _any(rules["no_dependency"], norm):
        failed.append("no_dependency")
    return GuardVerdict(ok=not failed, reasons=tuple(failed))


def _any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(p.search(text) for p in patterns)


_WORD = re.compile(r"[a-z]+")


def opener(text: str) -> str:
    """How a reply begins (its first three words, normalised), for spotting repeats."""
    return " ".join(_WORD.findall(base_form(text))[:3])
