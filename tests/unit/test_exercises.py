"""Exercise scripts: content checks (rules CL6, CL7) and step-by-step delivery (CR-12)."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import pytest

from oasis.router.exercise import (
    card_for,
    deliver,
    index,
    load_all,
    parse,
    start,
    technique_for,
)
from oasis.types import RouterState

MODES = ("cbt", "dbt", "mindfulness", "grounding")

# Rules CL7: v1 scripts are low-risk skills only.
FORBIDDEN = re.compile(
    r"hold (?:your|the) breath|breath[- ]?hold|holding your breath|cold water|\bice\b"
    r"|\bsprint|\brun\b|push-?ups?|exercise hard|until it hurts",
    re.IGNORECASE,
)


def test_every_structured_mode_has_one_script() -> None:
    assert {t.mode for t in load_all().values()} == set(MODES)
    for mode in MODES:
        assert technique_for(mode).mode == mode


@pytest.mark.parametrize("mode", MODES)
def test_scripts_are_complete_and_flagged_for_review(mode: str) -> None:
    t = technique_for(mode)
    for value in (t.name, t.offer, t.source, t.version):
        assert value
    assert len(t.steps) >= 2
    assert t.review_status == "needs_clinician_review"


@pytest.mark.parametrize("mode", MODES)
def test_scripts_are_low_risk_only(mode: str) -> None:
    t = technique_for(mode)
    for text in (t.offer, *t.steps):
        assert not FORBIDDEN.search(text), text


def test_the_grounding_script_is_five_four_three_two_one() -> None:
    steps = technique_for("grounding").steps
    assert len(steps) == 5
    for n, step in zip(("5", "4", "3", "2", "1"), steps, strict=True):
        assert n in step or ["five", "four", "three", "two", "one"][5 - int(n)] in step.lower()


def test_steps_are_delivered_in_order_and_the_exercise_then_ends() -> None:
    t = technique_for("dbt")
    rs = start(RouterState(current="dbt"), t.id)
    seen = []
    for k in range(1, len(t.steps) + 1):
        text, rs, card = deliver(rs)
        seen.append(text)
        if k < len(t.steps):
            assert card is not None
            assert (card.step, card.mode, card.item, card.item_count) == (
                "active", "dbt", k, len(t.steps))  # fmt: skip
            # The fixed step text is on the card, so the step is never lost if the model
            # drops it from its reply (manual test, 2026-10-12).
            assert card.instruction == text
            assert rs.exercise == t.id
        else:
            assert card is None
            assert (rs.exercise, rs.step) == (None, 0)
    assert seen == list(t.steps)
    assert rs.current == "dbt"


def test_card_for_restores_an_offer_or_the_running_step() -> None:
    assert card_for(RouterState()) is None
    offer = card_for(RouterState(offered="cbt"))
    assert offer is not None
    assert (offer.step, offer.mode, offer.name) == ("offer", "cbt", technique_for("cbt").name)
    t = technique_for("mindfulness")
    active = card_for(RouterState(current="mindfulness", exercise=t.id, step=2))
    assert active is not None
    assert (active.step, active.item, active.item_count) == ("active", 2, len(t.steps))
    assert active.instruction == t.steps[1]
    assert offer.instruction is None


# --- invalid content stops startup -----------------------------------------------------------


def _raw(**over: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": "x", "mode": "cbt", "name": "X", "offer": "Try X?", "source": "S",
        "version": "1", "review_status": "needs_clinician_review", "steps": ["One.", "Two."],
    }  # fmt: skip
    raw.update(over)
    return raw


@pytest.mark.parametrize("bad", [
    {"mode": "companion"},
    {"steps": []},
    {"steps": "one step"},
    {"review_status": "approved_by_nobody"},
    {"offer": ""},
    {"name": None},
])  # fmt: skip
def test_invalid_scripts_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="technique x"):
        parse(_raw(**bad))


def test_each_structured_mode_needs_exactly_one_script() -> None:
    scripts = list(load_all().values())
    with pytest.raises(ValueError, match="one technique per"):
        index(scripts[:-1])
    with pytest.raises(ValueError, match="one technique per"):
        index([*scripts, replace(scripts[0], id="duplicate")])
    assert index(scripts) == load_all()


def test_delivering_with_no_exercise_running_is_a_bug() -> None:
    with pytest.raises(ValueError, match="no exercise"):
        deliver(RouterState())
