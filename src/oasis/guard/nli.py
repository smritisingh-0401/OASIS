"""Optional NLI agreement check for the guard (G-AGREE; measured by ml/eval_guard_nli.py).

The phrase lists catch agreement that echoes the user's words or says "you're right". A reply
that rewords the claim and takes it as true ("the breakup really was your responsibility" for
"it's all my fault") slips past them (guard stress check, 2026-10-13). A small natural
language inference model (cross-encoder/nli-deberta-v3-xsmall, int8 ONNX) scores whether a
reply sentence entails the user's claim said back to them ("its all your fault").

Add-only: it can fail a reply the phrase lists passed, never pass one they failed. Optional:
it needs the `ml` extra and the files from ml/fetch_models.py; without them, or if the model
errors, the guard runs the phrase lists alone.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from oasis.content import load_yaml, require_review

log = logging.getLogger("oasis.guard")

_SENTENCE = re.compile(r"[^.!?]+[.!?]*")
_WORD = re.compile(r"[a-z]+")
_TO_YOU = {"i": "you", "im": "you are", "ive": "you have", "id": "you would", "ill": "you will",
           "me": "you", "my": "your", "mine": "yours", "myself": "yourself", "am": "are",
           "its": "it's", "cant": "can't", "dont": "don't", "doesnt": "doesn't",
           "didnt": "didn't", "wont": "won't", "isnt": "isn't", "arent": "aren't",
           "wasnt": "wasn't", "havent": "haven't", "couldnt": "couldn't",
           "shouldnt": "shouldn't", "wouldnt": "wouldn't"}  # fmt: skip


def to_second_person(clause: str) -> str:
    """The user's claim as said to them: "its all my fault" -> "its all your fault"."""
    return _WORD.sub(lambda m: _TO_YOU.get(m[0], m[0]), clause)


class AgreementModel:
    def __init__(self, folder: Path, threshold: float) -> None:
        import numpy as np
        import onnxruntime
        from tokenizers import Tokenizer

        self._np = np
        self.session = onnxruntime.InferenceSession(
            str(folder / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_padding()
        self.tokenizer.enable_truncation(256)
        labels = json.loads((folder / "config.json").read_text(encoding="utf-8"))["id2label"]
        self.entail = next(int(i) for i, name in labels.items() if name.lower() == "entailment")
        self.threshold = threshold

    def entailment(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """P(premise entails hypothesis) for each (premise, hypothesis) pair."""
        np = self._np
        enc = self.tokenizer.encode_batch(list(pairs))
        feed = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
        }
        logits: Any = self.session.run(None, feed)[0]
        p = np.exp(logits - logits.max(axis=1, keepdims=True))
        return [float(v) for v in (p / p.sum(axis=1, keepdims=True))[:, self.entail]]

    def score(self, reply: str, claims: Sequence[str]) -> float:
        """The highest entailment of any claim by any statement of the reply (questions
        assert nothing); 0 when there is nothing to compare."""
        statements = [s.strip() for s in _SENTENCE.findall(reply) if s.strip()]
        statements = [s for s in statements if not s.endswith("?")]
        pairs = [(s, to_second_person(c)) for s in statements for c in claims]
        return max(self.entailment(pairs), default=0.0) if pairs else 0.0

    def agrees(self, reply: str, claims: Sequence[str]) -> bool:
        try:
            return self.score(reply, claims) >= self.threshold
        except Exception:
            log.warning("nli agreement check failed")
            return False


def load_agreement(folder: Path) -> AgreementModel | None:
    """The model, or None when the `ml` extra or the model files are missing."""
    raw = load_yaml("guard", "nli.yaml")
    require_review(raw, "guard NLI threshold")
    if not (folder / "model.onnx").exists():
        log.info("guard NLI check off: no model in %s (ml/fetch_models.py)", folder)
        return None
    try:
        return AgreementModel(folder, float(raw["entailment_threshold"]))
    except ImportError:
        log.info("guard NLI check off: install the ml extra (uv sync --extra ml)")
        return None
