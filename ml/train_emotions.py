"""Learn add-only sadness, anxiety, anger and shame scorers from GoEmotions and write them to
content/lexicons/emotions_learned.yaml. signals.py takes the larger of the hand-written
scorer (emotions.yaml) and the learned one, so the learned scorer can raise an emotion the
hand terms miss ("I'm gutted", "dreading tomorrow") but never lower one: Reddit vocabulary
lacks some of OASIS's own phrasings ("on edge", "my mind is racing"), and replacing the hand
terms lost them (the router's natural-phrasing tests caught it).

The learned model has the lexicon's own form, so the explanations stay exact SHAP values
(design §10.1): an L1 logistic regression whose features are the lexicon's, each word's
count per token on the base form. Its logit z becomes the lexicon's pre-clip value
(z - t) / K, with t the dev-set threshold of best F0.5 (precision counts double, since a
false raise changes a route): a score is 0 below it and 1 from K above it.

Labels (GoEmotions -> OASIS): sadness <- sadness, grief, disappointment; anxiety <- fear,
nervousness; anger <- anger, annoyance; shame <- embarrassment, remorse. C is chosen on the
dev split by ROC-AUC; the test split is used once, for the report.

Usage: uv run python ml/train_emotions.py
"""

from __future__ import annotations

import datetime
import re
from typing import Any

import numpy as np
import yaml
from scipy.sparse import diags
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import fbeta_score, precision_score, recall_score, roc_auc_score

from common import ROOT, goemotions, save_report
from oasis.core.detectors.lexicon import Lexicon, load, parse
from oasis.safety.normalize import base_form

OUT = ROOT / "src" / "oasis" / "content" / "lexicons" / "emotions_learned.yaml"
LABELS = {
    "sadness": {"sadness", "grief", "disappointment"},
    "anxiety": {"fear", "nervousness"},
    "anger": {"anger", "annoyance"},
    "shame": {"embarrassment", "remorse"},
}
K = 3.0
C_GRID = (0.03, 0.1, 0.3, 1.0)
_PLACEHOLDER = re.compile(r"\[[A-Z]+\]")


def norm(text: str) -> str:
    return base_form(_PLACEHOLDER.sub(" ", text))


def rates(vec: CountVectorizer, texts: list[str]) -> Any:
    """Each word's count per whitespace token, as Lexicon.rates computes it."""
    return diags([1.0 / max(1, len(t.split())) for t in texts]) @ vec.transform(texts)


def raw(lex: Lexicon, text: str) -> float:
    part = lex.segment(text)
    return lex.linear(part, len(part.split()))


def main() -> None:
    data = {s: goemotions(s) for s in ("train", "dev", "test")}
    texts = {s: [norm(t) for t, _ in rows] for s, rows in data.items()}
    vec = CountVectorizer(token_pattern=r"\b[^\W\d_]+\b", lowercase=False, min_df=5)
    vec.fit(texts["train"])
    names = vec.get_feature_names_out()
    x = {s: rates(vec, t) for s, t in texts.items()}

    hand = load("emotions")
    doc: dict[str, Any] = {
        "schema": "oasis.content/v1",
        "kind": "lexicon",
        "version": datetime.date.today().isoformat(),
        "review_status": "needs_clinician_review",
        "trained_by": "ml/train_emotions.py",
        "scorers": {},
    }
    report: dict[str, Any] = {}
    for emotion, labels in LABELS.items():
        y = {s: np.array([bool(ls & labels) for _, ls in rows]) for s, rows in data.items()}
        fits = {}
        for c in C_GRID:
            model = LogisticRegression(
                l1_ratio=1, solver="liblinear", C=c, class_weight="balanced", max_iter=2000
            ).fit(x["train"], y["train"])
            fits[c] = (roc_auc_score(y["dev"], model.decision_function(x["dev"])), model)
        best = max(fits, key=lambda c: fits[c][0])
        model = fits[best][1]
        dev = model.decision_function(x["dev"])
        t = float(max(np.quantile(dev, np.linspace(0.5, 0.995, 100)),
                      key=lambda q: fbeta_score(y["dev"], dev >= q, beta=0.5)))  # fmt: skip
        terms = {rf"\b{names[i]}\b": round(float(w), 3)
                 for i, w in enumerate(model.coef_[0]) if abs(w) >= 0.001}  # fmt: skip
        doc["scorers"][emotion] = {
            "bias": round((float(model.intercept_[0]) - t) / K, 4),
            "scale": round(1 / K, 6),
            "terms": dict(sorted(terms.items(), key=lambda kv: -abs(kv[1]))),
        }
        learned = parse(doc)[emotion]

        probe = [p for p in texts["test"] if not re.search(r"[.!?;\n]", p)][:300]
        gap = np.abs(np.array([learned.linear(p, len(p.split())) * K + t for p in probe])
                     - model.decision_function(rates(vec, probe)))  # fmt: skip
        assert gap.max() < 0.05, (emotion, gap.max())  # noqa: S101

        test, yt = texts["test"], y["test"]
        fired = {"hand": np.array([hand[emotion].score(p) > 0 for p in test]),
                 "learned": np.array([learned.score(p) > 0 for p in test])}  # fmt: skip
        fired["hand_or_learned"] = fired["hand"] | fired["learned"]
        r = report[emotion] = {
            "positives_test": int(yt.sum()),
            "C": best,
            "threshold_logit": round(t, 4),
            "terms": len(terms),
            "hand_test_auc": round(roc_auc_score(yt, [raw(hand[emotion], p) for p in test]), 4),
            "learned_test_auc": round(roc_auc_score(yt, [raw(learned, p) for p in test]), 4),
            **{
                f"{k}_test": {
                    "precision": round(precision_score(yt, f, zero_division=0), 4),
                    "recall": round(recall_score(yt, f), 4),
                }
                for k, f in fired.items()
            },
        }
        print(
            f"{emotion:<8} AUC hand {r['hand_test_auc']:.3f} learned {r['learned_test_auc']:.3f}"
            f" | recall hand {r['hand_test']['recall']:.3f} -> hand or learned "
            f"{r['hand_or_learned_test']['recall']:.3f} (precision "
            f"{r['hand_test']['precision']:.3f} -> {r['hand_or_learned_test']['precision']:.3f})"
        )

    header = (
        "# Learned emotion scorers, GENERATED by ml/train_emotions.py (logistic regression on\n"
        "# GoEmotions); do not edit by hand. Add-only: signals.py takes the larger of these and\n"
        "# the hand-written scorers in emotions.yaml. Not clinically validated.\n"
    )
    OUT.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), "utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    save_report("emotions", report)


if __name__ == "__main__":
    main()
