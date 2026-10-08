"""Screening offer: readiness score, explicit requests and guards (design §3)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
import yaml

from oasis.assessment.trigger import decide, evaluate
from oasis.types import AssessmentRecord, TurnRecord

NOW = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.UTC)
LABELLED = Path(__file__).resolve().parents[1] / "data" / "assessment" / "labelled_conversations.yaml"

LOW_MOOD = [
    "I've been feeling really down for weeks",
    "nothing feels enjoyable anymore",
    "I can barely sleep and I'm exhausted all day",
    "I feel hopeless about everything",
]


def _history(*messages: str) -> tuple[TurnRecord, ...]:
    return tuple(TurnRecord(f"t{i}", i, "user", m, None, "") for i, m in enumerate(messages))


def _record(inst: str, status: str, ago: datetime.timedelta) -> AssessmentRecord:
    when = (NOW - ago).isoformat()
    return AssessmentRecord("a1", inst, status, "{}", when, completed_at=when)  # type: ignore[arg-type]


def test_a_single_low_message_does_not_offer() -> None:
    assert decide((), "I've been feeling really down for weeks", (), NOW) is None


def test_sustained_readiness_offers_phq9_with_its_score() -> None:
    offer = decide(_history(*LOW_MOOD[:-1]), LOW_MOOD[-1], (), NOW)
    assert offer is not None
    assert offer.instrument == "PHQ9"
    reason = json.loads(offer.reason)
    assert reason["reason"] == "sustained_readiness"
    assert reason["R"] >= 0.45
    assert reason["turns"] == 3
    assert reason["top_domains"]


@pytest.mark.parametrize(
    ("text", "inst"),
    [
        ("can I take a depression test?", "PHQ9"),
        ("is there an anxiety questionnaire I could do", "GAD7"),
        ("could we do the PHQ-9 together", "PHQ9"),
        ("I'd like to do the gad7", "GAD7"),
    ],
)
def test_explicit_request_offers_immediately(text: str, inst: str) -> None:
    offer = decide((), text, (), NOW)
    assert offer is not None
    assert offer.instrument == inst
    assert json.loads(offer.reason)["reason"] == "explicit_request"


# --- guards: each one blocks even an explicit request ----------------------------------

REQUEST = "can I take a depression test?"


@pytest.mark.parametrize("status", ["offered", "in_progress", "paused"])
def test_open_assessment_blocks_a_new_offer(status: str) -> None:
    assert decide((), REQUEST, (_record("GAD7", status, datetime.timedelta(minutes=5)),), NOW) is None


def test_recent_decline_blocks_for_24_hours() -> None:
    declined = _record("PHQ9", "declined", datetime.timedelta(hours=23))
    assert decide((), REQUEST, (declined,), NOW) is None
    older = _record("PHQ9", "declined", datetime.timedelta(hours=25))
    assert decide((), REQUEST, (older,), NOW) is not None


def test_completed_instrument_is_not_repeated_within_14_days() -> None:
    done = _record("PHQ9", "scored", datetime.timedelta(days=13))
    assert decide((), REQUEST, (done,), NOW) is None
    assert decide((), "can I take an anxiety questionnaire?", (done,), NOW) is not None
    old = _record("PHQ9", "scored", datetime.timedelta(days=15))
    assert decide((), REQUEST, (old,), NOW) is not None


def test_recent_crisis_in_the_conversation_blocks_offers() -> None:
    history = (TurnRecord("p", 1, "placeholder", "x", "crisis", ""),)
    assert decide(history, REQUEST, (), NOW) is None


# --- labelled conversations (reported in full by scripts/trigger_eval.py) -------------


def test_labelled_conversations_meet_the_reported_floor() -> None:
    doc = yaml.safe_load(LABELLED.read_text(encoding="utf-8"))
    result = evaluate(doc["conversations"])
    assert result["precision"] >= 0.8, result
    assert result["recall"] >= 0.8, result
