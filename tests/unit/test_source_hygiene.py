"""Source and content files contain no control characters.

A stray control character inside a regex (for example a backspace where "\\b" was meant)
silently changes what a safety pattern matches, so it is checked for every text file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".sql", ".html", ".js", ".css", ".md", ".toml"}
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
FILES = [
    p
    for top in ("src", "tests", "scripts", "docs")
    for p in (ROOT / top).rglob("*")
    if p.suffix in TEXT_SUFFIXES and "__pycache__" not in p.parts
]


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_control_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = CONTROL.search(text)
    assert match is None, f"control character {match.group()!r} at offset {match.start()}"
