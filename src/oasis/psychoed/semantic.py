"""Optional semantic retrieval for psychoeducation (FR-PSY; measured by ml/eval_psychoed.py).

The cue lexicon and item cues are phrase lists, so a question in other words ("does needing
support mean I'm weak?") gets no item. A small sentence-embedding model
(sentence-transformers/all-MiniLM-L6-v2, int8 ONNX) compares the message with each vetted
item (its topic and text) and picks the closest above a threshold.

Add-only: it is asked only when the cue lexicon found nothing, and only for a question,
since a statement on the same topic ("I couldn't sleep last night") wants listening, not
an explanation. The item text is the vetted text either way. Optional: it needs the `ml`
extra and the files from ml/fetch_models.py; without them, or if the model errors, the
phrase lists work alone.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

from oasis.content import load_yaml, require_review
from oasis.psychoed.selector import Item
from oasis.safety.normalize import base_form

log = logging.getLogger("oasis.psychoed")

_QUESTION = re.compile(
    r"\?|^(?:what|why|how|is|are|am|do|does|did|can|could|should|would|will|whats|hows)\b"
)


def is_question(message: str) -> bool:
    return bool(_QUESTION.search(base_form(message)))


class Embedder:
    def __init__(self, folder: Path) -> None:
        # Imported here: the `ml` extra is optional (load_matcher handles its absence).
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

    def embed(self, texts: Sequence[str]) -> Any:
        """Unit-length mean-pooled sentence vectors, one row per text."""
        np = self._np
        enc = self.tokenizer.encode_batch(list(texts))
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": mask,
            "token_type_ids": np.array([e.type_ids for e in enc], dtype=np.int64),
        }
        hidden = self.session.run(None, feed)[0]
        pooled = (hidden * mask[..., None]).sum(axis=1) / mask.sum(axis=1, keepdims=True)
        return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


class SemanticMatcher:
    def __init__(self, embedder: Embedder, items: Sequence[Item], threshold: float) -> None:
        self.embedder, self.items, self.threshold = embedder, tuple(items), threshold
        self.vectors = embedder.embed([f"{i.topic}. {i.text}" for i in self.items])

    def similarities(self, message: str) -> list[float]:
        """Cosine similarity of `message` to each item, in file order."""
        return [float(s) for s in self.vectors @ self.embedder.embed([message])[0]]

    def match(self, message: str, shown: Collection[str]) -> Item | None:
        """The closest item not yet shown, for a question at or above the threshold."""
        if not is_question(message):
            return None
        try:
            sims = self.similarities(message)
        except Exception:  # fail-soft boundary: the cue lexicon already ran on this message
            log.warning("psychoed semantic match failed")
            return None
        ranked = sorted(zip(sims, self.items, strict=True), key=lambda p: -p[0])
        return next((i for s, i in ranked if s >= self.threshold and i.id not in shown), None)


def load_matcher(folder: Path, items: Sequence[Item]) -> SemanticMatcher | None:
    """The matcher, or None when the `ml` extra or the model files are missing."""
    raw = load_yaml("psychoed", "semantic.yaml")
    require_review(raw, "psychoeducation similarity threshold")
    if not (folder / "model.onnx").exists():
        log.info("psychoed semantic match off: no model in %s (ml/fetch_models.py)", folder)
        return None
    try:
        return SemanticMatcher(Embedder(folder), items, float(raw["threshold"]))
    except ImportError:
        log.info("psychoed semantic match off: install the ml extra (uv sync --extra ml)")
        return None
