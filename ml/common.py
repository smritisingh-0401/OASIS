"""Shared helpers for the offline training scripts in ml/. Never imported by the app.

Downloads are cached in ml/data/ (git-ignored). Every script uses fixed seeds (rules T7).
"""

from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "ml" / "data"
TESTS = ROOT / "tests" / "data"
REPORTS = ROOT / "docs" / "reports"
SEED = 13

GOEMOTIONS = (
    "https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data/"
)


def fetch(url: str, name: str) -> Path:
    """Download `url` once into ml/data/`name`."""
    path = CACHE / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310  (fixed https URLs)
            path.write_bytes(r.read())
    return path


def goemotions(split: str) -> list[tuple[str, set[str]]]:
    """GoEmotions (Demszky et al. 2020, Apache-2.0): Reddit comments with 27 emotion labels
    plus neutral. `split` is train, dev or test."""
    names = fetch(GOEMOTIONS + "emotions.txt", "goemotions/emotions.txt").read_text().split()
    rows = []
    for line in fetch(GOEMOTIONS + f"{split}.tsv", f"goemotions/{split}.tsv").open(
        encoding="utf-8"
    ):
        text, labels, _ = line.rstrip("\n").split("\t")
        rows.append((text, {names[int(i)] for i in labels.split(",")}))
    return rows


DISTORTIONS = (
    "https://huggingface.co/datasets/masked-kunsiquat/shreevastava-cognitive-distortions/"
    "resolve/main/data/"
)
DISTORTION_NAMES = ("all_or_nothing", "overgeneralisation", "mental_filter",
                    "disqualifying_positive", "mind_reading", "fortune_telling", "magnification",
                    "emotional_reasoning", "should_statements", "labelling", "personalisation",
                    "blame")  # fmt: skip


def distortions() -> list[tuple[str, set[str]]]:
    """Therapy-forum posts annotated with thinking traps (Shreevastava & Foltz 2021), plus
    synthetic rows for the two traps the corpus lacks; MIT, via the Lattice mirror. An
    empty label set means no distortion."""
    rows = []
    for name in ("corpus", "synth_blame", "synth_disqualifying_positive"):
        path = fetch(DISTORTIONS + f"{name}.jsonl", f"distortions/{name}.jsonl")
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            labels = {n for n, on in zip(DISTORTION_NAMES, row["labels"], strict=True) if on}
            rows.append((row["text"], labels))
    return rows


def phrases(path: Path, key: str = "phrases") -> list[str]:
    """Every phrase of a grouped YAML test file."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [p for group in doc.get(key, {}).values() for p in group]


_KEYBOARD = "qwertyuiop asdfghjkl zxcvbnm"


def typo(text: str, rng: random.Random, edits: int = 1) -> str:
    """`text` with `edits` random keyboard typos: a dropped, doubled, swapped or
    neighbouring letter, the kinds seen in demo testing ("kil myself", "i want to dye")."""
    chars = list(text)
    for _ in range(edits):
        spots = [i for i, c in enumerate(chars) if c.isalpha()]
        if len(spots) < 2:
            break
        i = rng.choice(spots)
        kind = rng.randrange(4)
        if kind == 0:
            del chars[i]
        elif kind == 1:
            chars.insert(i, chars[i])
        elif kind == 2 and i + 1 < len(chars) and chars[i + 1].isalpha():
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        else:
            row = next((r for r in _KEYBOARD.split() if chars[i].lower() in r), "")
            j = row.find(chars[i].lower())
            if row:
                chars[i] = row[max(0, min(len(row) - 1, j + rng.choice((-1, 1))))]
    return "".join(chars)


def save_report(name: str, results: dict[str, Any]) -> None:
    path = REPORTS / f"ml-{name}.json"
    path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"saved {path.relative_to(ROOT)}")
