"""Train the add-only crisis classifier (rules S7) and write content/safety/classifier.yaml.

Data:
- crisis: tests/data/safety/train_phrases.yaml (never the held-out files, rules T8), each
  with 20 typo variants; a phrase and its variants share a group, so a fold never sees a
  typo of a phrase it is tested on. `expected_misses` stays out, as a showcase of typos.
- not crisis: GoEmotions training comments, one sentence each, minus any the rules flag
  (the rules would raise those anyway), plus the allow-list's idioms and the contrastive
  sentences in ml/hard_negatives.yaml (with 5 typo variants each, weighted x5), and the
  sentences of therapy-forum posts (common.distortions: distressed and self-critical, but
  not crisis once the rules filter them), weighted x2.

Model: L1 logistic regression over oasis.safety.classifier.features, chosen by 5-fold grouped
cross-validation. The threshold keeps the out-of-fold false-alarm rate on GoEmotions at
0.1%. The untouched GoEmotions test split gives a message-level false-alarm rate. Then run
scripts/safety_eval.py for held-out recall and benign false alarms.

Usage: uv run python ml/train_crisis.py
"""

from __future__ import annotations

import datetime
import random

import numpy as np
import yaml
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

from common import ROOT, SEED, TESTS, distortions, goemotions, phrases, save_report, typo
from oasis.safety.classifier import features, load_classifier, sentences
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset

OUT = ROOT / "src" / "oasis" / "content" / "safety" / "classifier.yaml"
VARIANTS = 20
MAX_FPR = 0.001
C_GRID = (0.3, 1.0, 3.0)
HARD_WEIGHT = 5.0
FORUM_WEIGHT = 2.0


def hard_negatives() -> list[str]:
    doc = yaml.safe_load((ROOT / "ml" / "hard_negatives.yaml").read_text(encoding="utf-8"))
    return [f.format(w) for f in doc["frames"] for w in doc["wants"]] + doc["sentences"]


def dataset() -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    rng = random.Random(SEED)
    gate = RuleBasedSafetyGate(load_ruleset())
    texts, labels, groups, weights = [], [], [], []
    for g, phrase in enumerate(phrases(TESTS / "safety" / "train_phrases.yaml")):
        variants = [phrase] + [typo(phrase, rng, 1 + i % 2) for i in range(VARIANTS)]
        for v in variants:
            texts += sentences(v)[:1]
            labels.append(1)
            groups.append(g)
            weights.append(1.0)
    for phrase in hard_negatives():
        g += 1
        for v in [phrase] + [typo(phrase, rng) for _ in range(5)]:
            texts += sentences(v)[:1]
            labels.append(0)
            groups.append(g)
            weights.append(HARD_WEIGHT)
    allow = yaml.safe_load((ROOT / "src/oasis/content/safety/allowlist.yaml").read_text())
    idioms = [e["positive_example"] for e in allow["entries"]]
    comments = [t for t, _ in goemotions("train")]
    for source, weight in ((idioms + comments, 1.0), ([t for t, _ in distortions()], FORUM_WEIGHT)):
        negatives = [s for t in source for s in sentences(t) if not gate.check(s).is_crisis]
        start = len(groups)
        texts += negatives
        labels += [0] * len(negatives)
        groups += range(start, start + len(negatives))
        weights += [weight] * len(negatives)
    return texts, np.array(labels), np.array(groups), np.array(weights)


def fit(
    texts: list[str], y: np.ndarray, w: np.ndarray, c: float
) -> tuple[CountVectorizer, LogisticRegression]:
    vec = CountVectorizer(analyzer=features, binary=True, min_df=2)
    x = vec.fit_transform(texts)
    model = LogisticRegression(
        l1_ratio=1, solver="liblinear", C=c, class_weight="balanced", max_iter=1000
    )
    return vec, model.fit(x, y, sample_weight=w)


def out_of_fold(
    texts: list[str], y: np.ndarray, groups: np.ndarray, w: np.ndarray, c: float
) -> np.ndarray:
    scores = np.zeros(len(y))
    folds = StratifiedGroupKFold(5, shuffle=True, random_state=SEED)
    for train, test in folds.split(texts, y, groups):
        vec, model = fit([texts[i] for i in train], y[train], w[train], c)
        scores[test] = model.decision_function(vec.transform([texts[i] for i in test]))
    return scores


def main() -> None:
    texts, y, groups, w = dataset()
    print(f"{y.sum()} crisis sentences, {(y == 0).sum()} others")
    cv = {}
    for c in C_GRID:
        oof = out_of_fold(texts, y, groups, w, c)
        t = float(np.quantile(oof[y == 0], 1 - MAX_FPR))
        cv[c] = {"threshold": t, "recall": float((oof[y == 1] >= t).mean()),
                 "fpr": float((oof[y == 0] >= t).mean())}  # fmt: skip
        print(f"C={c}: out-of-fold recall {cv[c]['recall']:.3f} at FPR {cv[c]['fpr']:.4f}")
    best = max(C_GRID, key=lambda c: cv[c]["recall"])

    vec, model = fit(texts, y, w, best)
    names = vec.get_feature_names_out()
    weights = {str(names[i]): round(float(w), 4) for i, w in enumerate(model.coef_[0]) if w}
    bias = float(model.intercept_[0])
    examples = phrases(TESTS / "safety" / "train_phrases.yaml")[:8]
    doc = {
        "version": datetime.date.today().isoformat(),
        "review_status": "needs_clinician_review",
        "model": "L1 logistic regression over word, word-pair and 3-5 letter features",
        "trained_by": "ml/train_crisis.py",
        "cross_validation": {"C": best, **cv[best]},
        "bias": round(bias, 4),
        "threshold": round(cv[best]["threshold"], 4),
        "examples": examples,
        "weights": dict(sorted(weights.items(), key=lambda kv: -abs(kv[1]))),
    }
    header = (
        "# Add-only crisis classifier weights (rules S7). GENERATED by ml/train_crisis.py; do\n"
        "# not edit by hand. Scored in pure Python by oasis.safety.classifier.\n"
    )
    OUT.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), "utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(weights)} weights, C={best}")

    clf = load_classifier()
    sample = texts[:: max(1, len(texts) // 500)]
    gap = np.abs(np.array([clf.logit(s) for s in sample]) - model.decision_function(
        vec.transform(sample)))  # fmt: skip
    assert gap.max() < 0.05, gap.max()  # noqa: S101

    gate = RuleBasedSafetyGate(load_ruleset())
    test = [t for t, _ in goemotions("test") if not gate.check(t).is_crisis]
    flagged = [t for t in test if clf.flags(t)]
    print(f"GoEmotions test: {len(flagged)}/{len(test)} = {len(flagged) / len(test):.2%} flagged")
    save_report("crisis", {"sentences": {"crisis": int(y.sum()), "other": int((y == 0).sum())},
                           "cross_validation": cv, "chosen_C": best, "weights": len(weights),
                           "parity_max_gap": float(gap.max()),
                           "goemotions_test_fpr": {"n": len(test), "flagged": len(flagged),
                                                   "examples": flagged[:20]}})  # fmt: skip


if __name__ == "__main__":
    main()
