"""Safety detector evaluation: held-out recall, benign false-positive rate, latency.

Usage:  uv run python scripts/safety_eval.py [--json PATH]

The held-out set was committed before any pattern existed and is never used for tuning
(rules T8). Misses are listed by name so they can be triaged as defects.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import yaml

from oasis.safety.gate import RuleBasedSafetyGate

DATA = Path(__file__).resolve().parent.parent / "tests" / "data" / "safety"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load((DATA / name).read_text(encoding="utf-8"))
    return doc


def evaluate(gate: RuleBasedSafetyGate, groups: dict[str, list[str]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for group, phrases in groups.items():
        flagged = [p for p in phrases if gate.check(p).is_crisis]
        out[group] = {
            "n": len(phrases),
            "flagged": len(flagged),
            "rate": len(flagged) / len(phrases),
            "not_flagged": [p for p in phrases if p not in flagged],
            "flagged_items": flagged,
        }
    return out


def latency(gate: RuleBasedSafetyGate, messages: list[str], repeats: int) -> dict[str, float]:
    samples = []
    for _ in range(repeats):
        for message in messages:
            start = time.perf_counter()
            gate.check(message)
            samples.append((time.perf_counter() - start) * 1000)
    q = statistics.quantiles(samples, n=100, method="inclusive")
    return {"n": len(samples), "p50_ms": q[49], "p95_ms": q[94], "p99_ms": q[98],
            "max_ms": max(samples)}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write results as JSON")
    args = parser.parse_args()

    gate = RuleBasedSafetyGate.load()
    heldout_doc = load("heldout_phrases.yaml")
    heldout = heldout_doc["phrases"]
    heldout_status = heldout_doc.get("status", "fresh")
    train = load("train_phrases.yaml")
    benign = load("benign.yaml")["phrases"]

    results = {
        "ruleset_version": gate.ruleset.version,
        "patterns": len(gate.ruleset.rules),
        "allowlist": len(gate.ruleset.allow),
        "heldout_recall": evaluate(gate, heldout),
        "train_recall": evaluate(gate, train["phrases"]),
        "known_gaps": evaluate(gate, {"expected_misses": train.get("expected_misses", [])}),
        "benign_fpr": evaluate(gate, benign),
    }
    every = [p for g in (heldout, train["phrases"], benign) for ps in g.values() for p in ps]
    long_messages = [" ".join(every)[:2000], "a" * 2000, "kill " * 400, "i " * 1000]
    results["latency"] = latency(gate, every + long_messages, repeats=20)

    print(f"Ruleset {results['ruleset_version']}: {results['patterns']} patterns, "
          f"{results['allowlist']} allow-list idioms\n")  # fmt: skip
    for title, key, word in (
        (f"HELD-OUT RECALL [{heldout_status}]", "heldout_recall", "missed"),
        ("TRAIN RECALL (must be 100%)", "train_recall", "missed"),
    ):
        section = results[key]
        total = sum(g["n"] for g in section.values())
        hit = sum(g["flagged"] for g in section.values())
        print(f"{title}: {hit}/{total} = {hit / total:.1%}")
        for group, g in section.items():
            print(f"  {group:<24}{g['flagged']:>3}/{g['n']:<3} {g['rate']:6.1%}")
            for p in g["not_flagged"]:
                print(f"      {word}: {p}")
        if key == "heldout_recall" and heldout_status == "consumed":
            print("  NOTE: this set was used for tuning; its recall is NOT an unbiased estimate.")
            print("  First measurement before tuning (2026-10-07): 63/71 = 88.7%.")
        print()
    print("BENIGN FALSE-POSITIVE RATE")
    for group, g in results["benign_fpr"].items():
        print(f"  {group:<24}{g['flagged']:>3}/{g['n']:<3} {g['rate']:6.1%}")
        for p in g["flagged_items"]:
            print(f"      flagged: {p}")
    gaps = results["known_gaps"]["expected_misses"]
    print(f"\nKNOWN GAPS (documented, not asserted): {gaps['flagged']}/{gaps['n']} now caught")
    lat = results["latency"]
    print(f"\nLATENCY over {lat['n']} checks: p50 {lat['p50_ms']:.3f} ms, p95 {lat['p95_ms']:.3f} ms,"
          f" p99 {lat['p99_ms']:.3f} ms, max {lat['max_ms']:.3f} ms (target p99 < 10 ms)")  # fmt: skip

    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved {args.json}")


if __name__ == "__main__":
    main()
