"""WCAG 2.2 AA contrast for every text colour on what it sits on (design §15.2, Phase 13).

Reads src/oasis/web/styles.css, so a colour change is checked against the same pairs. The
glass is translucent: each layer is composited over every colour that can show through it
(the page gradient and the background orbs, with each gradient stop) and the worst case
counts. Normal text needs 4.5:1, large text (the wordmark) 3:1. Also run by
tests/unit/test_contrast.py.

    uv run python scripts/contrast_check.py
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "src" / "oasis" / "web" / "styles.css"
RGBA = tuple[float, float, float, float]
Ref = tuple[str, str]  # (selector, property)

TEXT: Ref = ("body", "color")
CHAT: Ref = (".chat", "background")
BOT: Ref = (".msg.bot", "background")
CARD: Ref = (".card", "background")
HELP: Ref = (".help-card", "background")

# (what, text colour, layers from the page up, large text)
PAIRS: list[tuple[str, Ref, list[Ref], bool]] = [
    ("Wordmark", (".brand", "background"), [], True),
    ("Footer", (".footer", "color"), [], False),
    ("Need help now? and pills", (".pill", "color"), [(".pill", "background")], False),
    ("Help summary", (".help summary", "color"), [(".help summary", "background")], False),
    ("Help card heading", (".help-card summary", "color"),
     [HELP, (".help-card summary", "background")], False),
    ("Help card country", TEXT, [HELP, (".help-card .country > summary", "background")], False),
    ("Help card phone link", (".help-card a", "color"), [HELP], False),
    ("Help card hours", (".help-card .hours", "color"), [HELP], False),
    ("Help card other countries", (".help-card .all-countries > summary", "color"), [HELP], False),
    ("OASIS message", TEXT, [CHAT, BOT], False),
    ("Your message", TEXT, [CHAT, (".msg.user", "background")], False),
    ("Note under a message", (".msg .note", "color"), [CHAT, BOT], False),
    ("Why this reply? (summary)", (".why summary", "color"), [CHAT, BOT], False),
    ("Why this reply? (text)", (".why", "color"), [CHAT, BOT], False),
    ("System line", (".msg.system", "color"), [CHAT], False),
    ("Status line", (".status", "color"), [CHAT], False),
    ("Continue talking", (".continue", "color"), [CHAT, (".continue", "background")], False),
    ("Card text", TEXT, [CHAT, CARD], False),
    ("Card hint", (".card-hint", "color"), [CHAT, CARD], False),
    ("Card link", (".card .link", "color"), [CHAT, CARD], False),
    ("Card answer button", TEXT, [CHAT, CARD, (".card-options button", "background")], False),
    ("Message box", TEXT, [CHAT, (".composer", "background")], False),
    ("Message box placeholder", (".composer textarea::placeholder", "color"),
     [CHAT, (".composer", "background")], False),
    ("Send button", (".composer button", "color"), [(".composer button", "background")], False),
    ("Data notice", TEXT, [CHAT, (".notice", "background")], False),
    ("Data notice Read more", (".notice-more summary", "color"),
     [CHAT, (".notice", "background")], False),
    ("Settings panel", TEXT, [CHAT, (".settings-mode", "background")], False),
    ("Style option", TEXT, [CHAT, (".segment > span", "background")], False),
    ("Style example", (".segment .example", "color"), [CHAT, (".segment > span", "background")],
     False),
    ("Delete button", (".settings .danger", "color"), [(".settings .danger", "background")], False),
    ("Trend label", TEXT, [CHAT, (".trend-label", "background")], False),
    ("Trend explanation", (".basis span", "color"), [CHAT], False),
    ("Chart axis labels", (".chart .axis-text", "fill"), [CHAT], False),
]  # fmt: skip

_COLOUR = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|var\(--[\w-]+\)")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def value(selector: str, prop: str, css: str | None = None) -> str:
    """The property's value in the first rule for exactly this selector that sets it."""
    css = css or _css()
    for block in re.finditer(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", css):
        found = re.search(rf"(?:^|[;\s]){re.escape(prop)}\s*:\s*([^;]+);", block.group(1))
        if found is not None:
            return found.group(1).strip()
    raise KeyError(f"{selector} {prop}")


def colours(text: str, css: str | None = None) -> list[RGBA]:
    """Every colour in a declaration, in order (each stop of a gradient), vars resolved."""
    css = css or _css()
    out: list[RGBA] = []
    for token in _COLOUR.findall(text):
        if token.startswith("var("):
            out += colours(value(":root", token[4:-1], css), css)
        elif token.startswith("#"):
            h = token[1:] if len(token) == 7 else "".join(c * 2 for c in token[1:])
            out.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0))
        else:
            parts = [float(p) for p in token[token.index("(") + 1 : -1].split(",")]
            out.append((parts[0], parts[1], parts[2], parts[3] if len(parts) == 4 else 1.0))
    return out


def over(top: RGBA, below: RGBA) -> RGBA:
    a = top[3]
    return (*(a * t + (1 - a) * b for t, b in zip(top[:3], below[:3], strict=True)), 1.0)  # type: ignore[return-value]


def luminance(c: RGBA) -> float:
    def lin(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def ratio(a: RGBA, b: RGBA) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def backdrop(css: str) -> list[RGBA]:
    """What can show through the glass: the page gradient and the orbs' gradient stops."""
    return colours(value("body", "background", css), css) + colours(
        value(".orbs i:not(.dots)", "background", css), css
    )


def check(css: str | None = None) -> list[tuple[str, float, float]]:
    """(what, worst ratio, needed) for every pair."""
    css = css or _css()
    under = backdrop(css)
    results = []
    for what, text_ref, layer_refs, large in PAIRS:
        texts = colours(value(*text_ref, css), css)
        layers = [colours(value(*ref, css), css) for ref in layer_refs]
        worst = min(
            ratio(over(text, bg), bg)
            for base, *stack in itertools.product(under, *layers)
            for bg in [_stack(base, stack)]
            for text in texts
        )
        results.append((what, worst, 3.0 if large else 4.5))
    return results


def _stack(base: RGBA, layers: list[RGBA]) -> RGBA:
    out = base
    for layer in layers:
        out = over(layer, out)
    return out


def main() -> int:
    failed = 0
    for what, worst, need in check():
        ok = worst >= need
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {worst:5.2f}:1 (need {need}:1)  {what}")
    print(f"{len(PAIRS) - failed}/{len(PAIRS)} pairs meet WCAG 2.2 AA")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
