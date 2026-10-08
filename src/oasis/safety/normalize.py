"""Text normalisation for crisis matching (design §2.1). Pure functions, stdlib only.

Obfuscation is handled by producing a few *variants* of the message and matching every
variant: a match in any one triggers. Ordinary text yields a single variant, so the
cost of the extra variants is only paid on unusual input.
"""

from __future__ import annotations

import re
import unicodedata

# Look-alike letters from Cyrillic and Greek (after case folding) mapped to Latin.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
        "ј": "j", "ѕ": "s", "ԁ": "d", "к": "k", "м": "m", "т": "t", "н": "h", "в": "b",
        "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
        "υ": "u", "χ": "x", "ϲ": "c",
    }
)  # fmt: skip
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"))
_APOSTROPHES = re.compile(r"['‘’‛ʼ`´′]")
_STRETCH = re.compile(r"([^\W\d_])\1{2,}")
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"}
)
# Three or more single letters separated by one space/dot/dash/underscore/star: "k i l l".
_SPACED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][ .\-_*]){2,}[^\W\d_](?![^\W\d_])")
_SEPARATORS = re.compile(r"[ .\-_*]")


def base_form(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).casefold()
    text = text.translate(_CONFUSABLES)
    text = _APOSTROPHES.sub("", text)
    text = _STRETCH.sub(r"\1\1", text)
    return " ".join(text.split())


def _leet(text: str) -> str:
    # Only tokens that already contain a letter: "k1ll" decodes, "3 kids" does not.
    return " ".join(
        tok.translate(_LEET) if any(c.isalpha() for c in tok) else tok for tok in text.split(" ")
    )


def _unspace(text: str) -> str:
    return _SPACED.sub(lambda m: _SEPARATORS.sub("", m.group()), text)


def normalise(text: str) -> tuple[str, ...]:
    """Distinct normalised variants of `text`; the first is the plain base form."""
    base = base_form(text)
    leet = _leet(base)
    return tuple(dict.fromkeys((base, leet, _unspace(base), _unspace(leet))))


def tolerant(pattern: str) -> str:
    """Rewrite a regex so each literal letter also matches repeats of itself.

    "kill" -> "k+i+l+" matches kil, kill, kiill; an optional letter "s?" becomes "s*".
    A letter with any other explicit quantifier keeps it, so "of{2}" stays strictly double.
    Escapes and character classes are copied unchanged.
    """
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\":
            out.append(pattern[i : i + 2])
            i += 2
        elif c == "[":
            # Known limit: assumes no "]" inside a class; the loader rejects such patterns.
            end = pattern.index("]", i + 1)
            out.append(pattern[i : end + 1])
            i = end + 1
        elif c.isalpha():
            j = i
            while j + 1 < n and pattern[j + 1] == c:
                j += 1
            nxt = pattern[j + 1] if j + 1 < n else ""
            if nxt == "?" and pattern[j + 2 : j + 3] != "?":
                out.append(c + "*")  # optional letter: zero or more ("wrists?" -> wristss)
                i = j + 2
                continue
            out.append(pattern[i : j + 1] if nxt and nxt in "?*+{" else c + "+")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)
