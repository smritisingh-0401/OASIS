"""Every text colour meets WCAG 2.2 AA on whatever can show through the glass (design §15.2)."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "contrast_check.py"
C: dict[str, Any] = runpy.run_path(str(SCRIPT))


@pytest.mark.parametrize(("what", "worst", "need"), C["check"](), ids=lambda v: str(v))
def test_text_meets_aa_over_the_darkest_backdrop(what: str, worst: float, need: float) -> None:
    assert worst >= need, f"{what}: {worst:.2f}:1"


def test_ratio_and_compositing() -> None:
    white, black = (255, 255, 255, 1.0), (0, 0, 0, 1.0)
    assert C["ratio"](white, black) == pytest.approx(21.0)
    assert C["over"]((255, 255, 255, 0.5), black)[:3] == (127.5, 127.5, 127.5)
    # A gradient gives one colour per stop; vars resolve through :root.
    css = ":root {\n  --a: #000000;\n}\n.x {\n  background: linear-gradient(var(--a), #fff);\n}\n"
    assert C["colours"](C["value"](".x", "background", css), css) == [black, white]


def test_the_darkest_orb_is_part_of_the_backdrop() -> None:
    darkest = min(C["backdrop"](C["_css"]()), key=C["luminance"])
    assert darkest[:3] == (0x73, 0x99, 0xEA)
