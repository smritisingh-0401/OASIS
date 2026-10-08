"""Score the screening-offer trigger on the labelled conversations (design §3.3).

Usage: uv run python scripts/trigger_eval.py [--json results.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from oasis.assessment.trigger import evaluate

DATA = Path(__file__).resolve().parents[1] / "tests" / "data" / "assessment"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write results as JSON")
    args = parser.parse_args()

    doc = yaml.safe_load((DATA / "labelled_conversations.yaml").read_text(encoding="utf-8"))
    result = evaluate(doc["conversations"])
    print(f"Conversations: {len(doc['conversations'])}")
    counts = ", ".join(f"{k.upper()} {result[k]}" for k in ("tp", "fp", "fn", "tn"))
    print(f"Precision {result['precision']:.2f}  Recall {result['recall']:.2f}  ({counts})")
    if result["mean_latency_turns"] is not None:
        print(
            f"Mean offer latency: {result['mean_latency_turns']:.2f} turns after the earliest point"
        )
    print(
        "NOTE: these conversations were used to tune the lexicon weights; see the phase 3 report."
    )
    print("First measurement before tuning (2026-10-08): precision 0.80, recall 0.31.\n")
    for row in result["conversations"]:
        where = "-" if row["offered_at"] is None else f"turn {row['offered_at']}"
        print(f"  {row['outcome']:<22}{row['id']:<26}{where:<9}{row['instrument'] or ''}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nSaved {args.json}")


if __name__ == "__main__":
    main()
