"""Download the two optional ONNX models into models/ (git-ignored), at pinned revisions.

- models/nli: cross-encoder/nli-deberta-v3-xsmall (Apache-2.0), int8, ~87 MB. The guard's
  agreement check (oasis.guard.nli).
- models/embed: sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0), int8, ~23 MB.
  Psychoeducation retrieval (oasis.psychoed.semantic).

Both need the `ml` extra (`uv sync --extra ml`); without the files or the extra, OASIS runs
as before.

Usage: uv run python ml/fetch_models.py
"""

from __future__ import annotations

import urllib.request

from common import ROOT

MODELS = {
    "nli": ("cross-encoder/nli-deberta-v3-xsmall", "a150876415327c80daeff35ca6f68f5ed8cf5c24"),
    "embed": ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"),
}
# The AVX2 build runs on any x86-64 CPU from the last decade.
FILES = {"model.onnx": "onnx/model_quint8_avx2.onnx", "tokenizer.json": "tokenizer.json",
         "config.json": "config.json"}  # fmt: skip


def main() -> None:
    for name, (repo, rev) in MODELS.items():
        folder = ROOT / "models" / name
        folder.mkdir(parents=True, exist_ok=True)
        for local, remote in FILES.items():
            path = folder / local
            if path.exists():
                continue
            url = f"https://huggingface.co/{repo}/resolve/{rev}/{remote}"
            print(f"downloading {url}")
            with urllib.request.urlopen(url, timeout=120) as r:
                path.write_bytes(r.read())
        print(f"{name}: {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
