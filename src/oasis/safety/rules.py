"""Load and validate the crisis pattern and allow-list files (design §2.2, §14).

Any problem raises SafetyConfigError, which stops the app at startup: invalid safety
content fails fast at boot, never at turn time (rules S5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from oasis.safety.normalize import normalise, tolerant

TIERS = ("explicit", "passive", "plan_method", "burden", "self_harm")
# Unbounded quantifier applied to a group that itself ends in a quantifier: (a+)+, (\w+ )*.
_NESTED = re.compile(r"[+*][^()]*\)[+*]|[+*][^()]*\)\{\d+,\}")
# Named groups and inline flags would be mangled by the tolerant rewrite.
_INLINE = re.compile(r"\(\?(?![:=!]|<[=!])")


class SafetyConfigError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    id: str
    tier: str
    regex: re.Pattern[str]
    examples: tuple[str, ...]


@dataclass(frozen=True)
class AllowRule:
    id: str
    regex: re.Pattern[str]
    suppresses: frozenset[str]
    positive_example: str
    negative_example: str


@dataclass(frozen=True)
class RuleSet:
    version: str
    rules: tuple[Rule, ...]
    allow: tuple[AllowRule, ...]

    def hits(self, text: str) -> dict[str, str]:
        """Rule id -> tier for every unsuppressed match in any normalised variant."""
        found: dict[str, str] = {}
        for variant in normalise(text):
            idioms = [
                (a.suppresses, m.span()) for a in self.allow for m in a.regex.finditer(variant)
            ]
            for rule in self.rules:
                for m in rule.regex.finditer(variant):
                    start, end = m.span()
                    covered = any(
                        rule.id in sup and s <= start and end <= e for sup, (s, e) in idioms
                    )
                    if not covered:
                        found[rule.id] = rule.tier
                        break
        return found


def _compile(raw: Any, where: str) -> re.Pattern[str]:
    if not isinstance(raw, str) or not raw:
        raise SafetyConfigError(f"{where}: pattern must be a non-empty string")
    if _INLINE.search(raw):
        raise SafetyConfigError(f"{where}: named groups and inline flags are not allowed")
    if _NESTED.search(raw):
        raise SafetyConfigError(f"{where}: unbounded nested quantifier (backtracking risk)")
    try:
        return re.compile(tolerant(raw))
    except (re.error, ValueError) as exc:
        raise SafetyConfigError(f"{where}: does not compile: {exc}") from None


def _parse(text: str, name: str) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SafetyConfigError(f"{name}: invalid YAML: {exc}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("version"), str):
        raise SafetyConfigError(f"{name}: missing version")
    return doc


def _rules(doc: dict[str, Any]) -> tuple[Rule, ...]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for item in doc.get("patterns") or []:
        rid, tier = str(item.get("id", "")), item.get("tier")
        where = f"patterns.yaml {rid or '?'}"
        if tier not in TIERS:
            raise SafetyConfigError(f"{where}: unknown tier {tier!r}")
        prefix = {"plan_method": "plan"}.get(tier, tier)
        if not rid.startswith(prefix + "."):
            raise SafetyConfigError(f"{where}: id must use the prefix {prefix}.")
        if rid in seen:
            raise SafetyConfigError(f"{where}: duplicate id")
        seen.add(rid)
        examples = tuple(item.get("examples") or ())
        if not examples:
            raise SafetyConfigError(f"{where}: at least one example is required")
        rules.append(Rule(rid, tier, _compile(item.get("pattern"), where), examples))
    if not rules:
        raise SafetyConfigError("patterns.yaml: no patterns")
    return tuple(rules)


def _allow(doc: dict[str, Any], rule_ids: set[str]) -> tuple[AllowRule, ...]:
    entries: list[AllowRule] = []
    for item in doc.get("entries") or []:
        aid = str(item.get("id", ""))
        where = f"allowlist.yaml {aid or '?'}"
        suppresses = frozenset(item.get("suppresses") or ())
        if not suppresses or not suppresses <= rule_ids:
            raise SafetyConfigError(f"{where}: suppresses unknown or no rule ids")
        entries.append(
            AllowRule(aid, _compile(item.get("pattern"), where), suppresses,
                      str(item.get("positive_example", "")), str(item.get("negative_example", "")))
        )  # fmt: skip
    return tuple(entries)


def _self_check(ruleset: RuleSet) -> None:
    """Every example must trigger its rule; every idiom must be live and must not over-reach."""
    bare = RuleSet(ruleset.version, ruleset.rules, ())
    for rule in ruleset.rules:
        for example in rule.examples:
            if rule.id not in ruleset.hits(example):
                raise SafetyConfigError(
                    f"patterns.yaml {rule.id}: example not matched: {example!r}"
                )
    for entry in ruleset.allow:
        where = f"allowlist.yaml {entry.id}"
        raw = bare.hits(entry.positive_example)
        if not (set(raw) & entry.suppresses) or set(ruleset.hits(entry.positive_example)) & (
            entry.suppresses
        ):
            raise SafetyConfigError(
                f"{where}: positive_example must match a suppressed rule and be suppressed"
            )
        if not ruleset.hits(entry.negative_example):
            raise SafetyConfigError(f"{where}: negative_example must still trigger")


def load_ruleset(patterns_text: str | None = None, allowlist_text: str | None = None) -> RuleSet:
    """Load the shipped files, or the given YAML text (used by tests)."""
    folder = resources.files("oasis.content") / "safety"
    if patterns_text is None:
        patterns_text = (folder / "patterns.yaml").read_text(encoding="utf-8")
    if allowlist_text is None:
        allowlist_text = (folder / "allowlist.yaml").read_text(encoding="utf-8")
    pdoc = _parse(patterns_text, "patterns.yaml")
    adoc = _parse(allowlist_text, "allowlist.yaml")
    rules = _rules(pdoc)
    ruleset = RuleSet(pdoc["version"], rules, _allow(adoc, {r.id for r in rules}))
    _self_check(ruleset)
    return ruleset
