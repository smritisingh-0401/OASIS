"""Choose the psychoeducation similarity threshold and measure what retrieval adds.

The system is the planner's: the cue lexicon and item cues first; the semantic matcher only
when they found nothing. The threshold is the lowest on a grid that gives at most 1 of the
ordinary messages in tests/data/psychoed/ordinary.yaml an item; it is written to
content/psychoed/semantic.yaml. tests/data/psychoed/heldout_semantic.yaml (never tuned
against) is then scored once: the right item for each `cue` question, and no item for each
`ordinary` message. The same run without the question check is reported as an ablation.

Usage: uv run python ml/eval_psychoed.py   (needs the ml extra and ml/fetch_models.py)
"""

from __future__ import annotations

import re
import statistics
import time
from typing import Any

import yaml

from common import ROOT, TESTS, save_report
from oasis.core.signals import extract
from oasis.psychoed import selector
from oasis.psychoed.semantic import Embedder, SemanticMatcher

GRID = (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)
MAX_TUNING_FALSE = 1
CONFIG = ROOT / "src" / "oasis" / "content" / "psychoed" / "semantic.yaml"


def pick(m: SemanticMatcher | None, message: str, gate: bool = True) -> str | None:
    if extract(message).psychoed_cue:
        item = selector.select(message, ())
        return item.id if item else None
    if m is None:
        return None
    if gate:
        found = m.match(message, ())
        return found.id if found else None
    sims = m.similarities(message)
    best = max(range(len(sims)), key=sims.__getitem__)
    return m.items[best].id if sims[best] >= m.threshold else None


def score(m: SemanticMatcher | None, cue: list[dict[str, str]], ordinary: list[str],
          gate: bool = True) -> dict[str, Any]:  # fmt: skip
    got = [pick(m, c["message"], gate) for c in cue]
    false = [o for o in ordinary if pick(m, o, gate)]
    return {"right_item": sum(g == c["item"] for g, c in zip(got, cue, strict=True)),
            "any_item": sum(g is not None for g in got), "n_cue": len(cue),
            "ordinary_given_item": len(false), "n_ordinary": len(ordinary),
            "false_items": false,
            "missed": [c["message"] for g, c in zip(got, cue, strict=True)
                       if g != c["item"]]}  # fmt: skip


def main() -> None:
    load = lambda name: yaml.safe_load((TESTS / "psychoed" / name).read_text("utf-8"))  # noqa: E731
    tune_cue, tune_ordinary = load("trigger.yaml")["messages"], load("ordinary.yaml")["messages"]
    held = load("heldout_semantic.yaml")
    m = SemanticMatcher(Embedder(ROOT / "models" / "embed"), selector.load_all(), 1.0)

    grid = {}
    for t in GRID:
        m.threshold = t
        grid[t] = score(m, tune_cue, tune_ordinary)
    t = min(x for x in GRID if grid[x]["ordinary_given_item"] <= MAX_TUNING_FALSE)
    m.threshold = t
    report: dict[str, Any] = {
        "threshold": t,
        "grid": {str(x): {k: v for k, v in r.items() if isinstance(v, int)}
                 for x, r in grid.items()},
        "heldout": {"phrase_lists": score(None, held["cue"], held["ordinary"]),
                    "phrase_lists_or_semantic": score(m, held["cue"], held["ordinary"]),
                    "without_question_check": score(m, held["cue"], held["ordinary"], False)},
    }  # fmt: skip
    print(f"threshold {t}")
    for name, r in report["heldout"].items():
        print(f"  {name:<26} right item {r['right_item']:>2}/{r['n_cue']}  any item "
              f"{r['any_item']:>2}/{r['n_cue']}  ordinary given an item "
              f"{r['ordinary_given_item']}/{r['n_ordinary']}")  # fmt: skip

    samples = []
    for _ in range(30):
        start = time.perf_counter()
        m.match("why do I feel so tired all the time?", ())
        samples.append((time.perf_counter() - start) * 1000)
    report["latency_ms"] = {"median": round(statistics.median(samples), 1),
                            "max": round(max(samples), 1)}  # fmt: skip
    print(f"latency per question: median {report['latency_ms']['median']} ms")

    text = CONFIG.read_text(encoding="utf-8")
    CONFIG.write_text(re.sub(r"threshold: [\d.]+", f"threshold: {t}", text), encoding="utf-8")
    save_report("psychoed", report)


if __name__ == "__main__":
    main()
