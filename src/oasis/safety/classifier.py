"""Add-only crisis classifier (rules S7): catches misspelled and reworded crisis messages the
patterns miss ("i want to dye"). The gate ORs it with the rules, so it can raise an alert but
never clear one.

A logistic regression over word and character n-grams, trained offline by
ml/train_crisis.py and shipped as weights in content/safety/classifier.yaml, so scoring is a
sum of weights in pure Python (rules S8). Each sentence is scored on its own and the highest
score is used, so a long message cannot add up many small weights into an alert.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from importlib import resources
from itertools import pairwise

import yaml

from oasis.safety.normalize import base_form
from oasis.safety.rules import SafetyConfigError

_SENTENCE = re.compile(r"[.!?;\n]+")
_WORD = re.compile(r"[^\W_]+")


def sentences(text: str) -> list[str]:
    """The base-form sentences of `text` that hold a word."""
    return [s for s in (base_form(p) for p in _SENTENCE.split(text)) if _WORD.search(s)]


def features(sentence: str) -> set[str]:
    """Words, word pairs and the 3-5 letter pieces of each word (with its edges), so a typo
    changes only a few features. ml/train_crisis.py trains on this same function."""
    words = _WORD.findall(sentence)
    found = {f"w:{w}" for w in words} | {f"w:{a} {b}" for a, b in pairwise(words)}
    for w in set(words):
        found |= _pieces(w)
    return found


@functools.lru_cache(maxsize=4096)
def _pieces(word: str) -> frozenset[str]:
    padded = f" {word} "
    return frozenset(
        f"c:{padded[i : i + n]}" for n in (3, 4, 5) for i in range(len(padded) - n + 1)
    )


@dataclass(frozen=True)
class CrisisClassifier:
    version: str
    bias: float
    threshold: float
    weights: dict[str, float]

    def logit(self, sentence: str) -> float:
        return self.bias + sum(self.weights.get(f, 0.0) for f in features(sentence))

    def score(self, text: str) -> float:
        """The highest sentence logit; the bias for text without words."""
        return max((self.logit(s) for s in sentences(text)), default=self.bias)

    def flags(self, text: str) -> bool:
        return self.score(text) >= self.threshold


def load_classifier(text: str | None = None) -> CrisisClassifier:
    """Load the shipped weights, or the given YAML text (used by tests). A bad file stops the
    app at startup (rules S5), and every listed example must still be flagged."""
    if text is None:
        folder = resources.files("oasis.content") / "safety"
        text = (folder / "classifier.yaml").read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
        clf = CrisisClassifier(
            version=str(doc["version"]),
            bias=float(doc["bias"]),
            threshold=float(doc["threshold"]),
            weights={str(k): float(v) for k, v in doc["weights"].items()},
        )
        examples = [str(e) for e in doc["examples"]]
    except (yaml.YAMLError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SafetyConfigError(f"classifier.yaml: {type(exc).__name__}") from None
    missed = [e for e in examples if not clf.flags(e)]
    if not clf.weights or not examples or missed:
        raise SafetyConfigError(f"classifier.yaml: examples not flagged: {missed}")
    return clf
