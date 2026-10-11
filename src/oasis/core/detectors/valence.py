"""Valence baseline: the VADER compound score in [-1, 1] (design §5)."""

from __future__ import annotations

import functools

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


@functools.cache
def _analyzer() -> SentimentIntensityAnalyzer:
    return SentimentIntensityAnalyzer()  # loads the bundled lexicon once


def valence(text: str) -> float:
    return float(_analyzer().polarity_scores(text)["compound"])
