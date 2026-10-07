"""Normaliser golden tests (design §2.1)."""

from __future__ import annotations

import re

import pytest

from oasis.safety.normalize import base_form, normalise, tolerant


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("KILL", "kill"),
        ("ｋｉｌｌ", "kill"),  # fullwidth -> NFKC
        ("kіll", "kill"),  # Cyrillic i
        ("ki​ll", "kill"),  # zero-width space
        ("ki­ll", "kill"),  # soft hyphen
        ("don’t", "dont"),  # curly apostrophe removed
        ("I'm", "im"),
        ("kiiiiill", "kiill"),  # runs of 3+ letters reduced to 2
        ("a   b\n\t c", "a b c"),
        ("ΚILL", "kill"),  # Greek capital kappa
    ],
)
def test_base_form(raw: str, expected: str) -> None:
    assert base_form(raw) == expected


@pytest.mark.parametrize(
    ("raw", "variant"),
    [
        ("k1ll myself", "kill myself"),
        ("su1c!de", "suicide"),
        ("d3ath", "death"),
        ("k i l l myself", "kill myself"),
        ("k.i.l.l myself", "kill myself"),
        ("k-1-l-l myself", "kill myself"),
    ],
)
def test_variants_decode_obfuscation(raw: str, variant: str) -> None:
    assert variant in normalise(raw)


def test_leet_leaves_number_only_tokens_alone() -> None:
    assert normalise("I have 3 kids") == ("i have 3 kids",)


def test_ordinary_text_has_a_single_variant() -> None:
    assert normalise("I had a long day") == ("i had a long day",)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("kill", "k+i+l+"),
        ("of{2}", "o+f{2}"),
        (r"\bself", r"\bs+e+l+f+"),
        ("[a-z]x", "[a-z]x+"),
        ("(?:ing|ed)?", "(?:i+n+g+|e+d+)?"),
        (r"\w+ ?a", r"\w+ ?a+"),
        ("ab?c", "a+b*c+"),
        ("ab??c", "a+b??c+"),
    ],
)
def test_tolerant_pattern_transform(pattern: str, expected: str) -> None:
    assert tolerant(pattern) == expected


@pytest.mark.parametrize("text", ["kill", "kil", "kiill", "killl"])
def test_tolerant_pattern_accepts_repeated_letters(text: str) -> None:
    assert re.fullmatch(tolerant("kill"), text)


def test_explicit_double_stays_double() -> None:
    assert re.fullmatch(tolerant("of{2}"), "off")
    assert not re.fullmatch(tolerant("of{2}"), "of")
