"""PHQ-9 / GAD-7 content and scoring (design §4, rules CL1)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from oasis.assessment.instruments import INSTRUMENT_IDS, instrument, load_instrument, score

PHQ9 = instrument("PHQ9")
GAD7 = instrument("GAD7")
OPTIONS = ("Not at all", "Several days", "More than half the days", "Nearly every day")


# --- shipped content matches the published forms -----------------------------------


def test_published_structure() -> None:
    assert len(PHQ9.items) == 9
    assert len(GAD7.items) == 7
    assert PHQ9.options == GAD7.options == OPTIONS
    assert PHQ9.items[8] == (
        "Thoughts that you would be better off dead or of hurting yourself in some way"
    )
    assert GAD7.items[0] == "Feeling nervous, anxious or on edge"
    assert PHQ9.functional_question is not None
    assert GAD7.functional_question is None  # the published GAD-7 form has none
    for inst in (PHQ9, GAD7):
        assert inst.source.startswith("https://www.phqscreeners.com/")
        assert inst.max_total == 3 * len(inst.items)


@pytest.mark.parametrize(
    ("inst_id", "total", "band"),
    [
        ("PHQ9", 0, "minimal"), ("PHQ9", 4, "minimal"), ("PHQ9", 5, "mild"),
        ("PHQ9", 9, "mild"), ("PHQ9", 10, "moderate"), ("PHQ9", 14, "moderate"),
        ("PHQ9", 15, "moderately severe"), ("PHQ9", 19, "moderately severe"),
        ("PHQ9", 20, "severe"), ("PHQ9", 27, "severe"),
        ("GAD7", 0, "minimal"), ("GAD7", 4, "minimal"), ("GAD7", 5, "mild"),
        ("GAD7", 9, "mild"), ("GAD7", 10, "moderate"), ("GAD7", 14, "moderate"),
        ("GAD7", 15, "severe"), ("GAD7", 21, "severe"),
    ],
)  # fmt: skip
def test_band_edges(inst_id: str, total: int, band: str) -> None:
    inst = instrument(inst_id)
    answers = _answers_summing_to(total, len(inst.items))
    assert score(inst, answers) == (total, band)


def _answers_summing_to(total: int, n: int) -> list[int]:
    answers = []
    for _ in range(n):
        answers.append(min(3, total))
        total -= answers[-1]
    return answers


# --- properties ----------------------------------------------------------------------


@given(st.sampled_from(INSTRUMENT_IDS), st.data())
def test_total_is_the_sum_and_in_range(inst_id: str, data: st.DataObject) -> None:
    inst = instrument(inst_id)
    answers = data.draw(st.lists(st.integers(0, 3), min_size=len(inst.items), max_size=len(inst.items)))
    total, band = score(inst, answers)
    assert total == sum(answers)
    assert 0 <= total <= inst.max_total
    assert band in {b.label for b in inst.bands}


@pytest.mark.parametrize("inst_id", INSTRUMENT_IDS)
def test_every_total_maps_to_exactly_one_band_and_bands_are_monotone(inst_id: str) -> None:
    inst = instrument(inst_id)
    order = [b.label for b in inst.bands]
    previous = 0
    for total in range(inst.max_total + 1):
        matching = [b for b in inst.bands if b.low <= total <= b.high]
        assert len(matching) == 1
        rank = order.index(matching[0].label)
        assert rank >= previous
        previous = rank


@given(st.sampled_from(INSTRUMENT_IDS), st.data())
def test_incomplete_or_invalid_answers_are_never_scored(inst_id: str, data: st.DataObject) -> None:
    inst = instrument(inst_id)
    n = len(inst.items)
    short = data.draw(st.lists(st.integers(0, 3), max_size=n - 1))
    with pytest.raises(ValueError, match="incomplete"):
        score(inst, short)
    bad = data.draw(st.lists(st.integers(0, 3), min_size=n, max_size=n))
    bad[data.draw(st.integers(0, n - 1))] = data.draw(st.sampled_from([-1, 4, 7]))
    with pytest.raises(ValueError, match="0-3"):
        score(inst, bad)


# --- loader refuses bad content ------------------------------------------------------

GOOD = """
instrument: GAD7
name: GAD-7
source: https://www.phqscreeners.com/x.pdf
verified_on: 2026-10-08
stem: "Over the last 2 weeks?"
options: ["Not at all", "Several days", "More than half the days", "Nearly every day"]
items: ["a", "b"]
functional: null
bands:
  - {min: 0, max: 2, label: low}
  - {min: 3, max: 6, label: high}
"""


def test_minimal_instrument_loads() -> None:
    assert load_instrument("GAD7", GOOD).max_total == 6


@pytest.mark.parametrize(
    "bad",
    [
        GOOD.replace("instrument: GAD7", "instrument: PHQ9"),
        GOOD.replace('"Nearly every day"]', '"Always"]'),
        GOOD.replace('items: ["a", "b"]', "items: []"),
        GOOD.replace("{min: 3, max: 6", "{min: 4, max: 6"),  # gap at 3
        GOOD.replace("{min: 3, max: 6", "{min: 3, max: 5"),  # does not reach the maximum
        GOOD.replace("https://www.phqscreeners.com/x.pdf", "http://example.com"),
        GOOD.replace("verified_on: 2026-10-08", "verified_on: 2999-01-01"),
    ],
)
def test_invalid_instrument_refuses_to_load(bad: str) -> None:
    with pytest.raises(ValueError, match="GAD7"):
        load_instrument("GAD7", bad)
