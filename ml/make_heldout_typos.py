"""Write tests/data/safety/heldout_typos.yaml once: each held-out crisis phrase (batches 1
and 2) with one and with two keyboard typos, from a seed the training never uses. It measures
how the gate copes with misspellings of phrasings it was not trained on. Never overwritten,
so the set stays frozen (rules T8).

Usage: uv run python ml/make_heldout_typos.py
"""

from __future__ import annotations

import random

import yaml

from common import TESTS, typo

OUT = TESTS / "safety" / "heldout_typos.yaml"
SEED = 2026  # not common.SEED, which the training uses


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists; it is frozen")
    rng = random.Random(SEED)
    groups: dict[str, list[str]] = {}
    for name in ("heldout_phrases.yaml", "heldout_v2_phrases.yaml"):
        doc = yaml.safe_load((TESTS / "safety" / name).read_text(encoding="utf-8"))
        for group, items in doc["phrases"].items():
            if group == "harm_others":
                continue  # the classifier is trained on risk to self only
            groups.setdefault(group, []).extend(typo(p, rng, e) for p in items for e in (1, 2))
    header = (
        "# Held-out crisis phrases with keyboard typos, GENERATED once by\n"
        "# ml/make_heldout_typos.py from heldout_phrases.yaml and heldout_v2_phrases.yaml\n"
        "# (seed 2026). Never used for training or tuning (rules T8).\n"
    )
    doc = {"version": "2026.11.0", "review_status": "needs_clinician_review", "phrases": groups}
    OUT.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), "utf-8")
    print(f"wrote {OUT}: {sum(map(len, groups.values()))} phrases")


if __name__ == "__main__":
    main()
