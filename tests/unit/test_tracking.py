"""Language-based mood tracking: per-turn features and their aggregation (design §9, FR-TRK)."""

from __future__ import annotations

import datetime
from dataclasses import fields, replace
from typing import Any

import pytest

from oasis.core.signals import EMOTIONS, extract
from oasis.tracking.aggregate import change_flags, ewma, summarise, trend
from oasis.tracking.features import load_config, parse, turn_features
from oasis.types import SignalRecord, TurnFeatures

UTC = datetime.UTC
NOW = datetime.datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def features(message: str, **kw: Any) -> TurnFeatures:
    kw.setdefault("received_at", NOW)
    kw.setdefault("last_reply_at", None)
    kw.setdefault("client_ts", None)
    return turn_features(message, extract(message), **kw)


# --- per-turn features (FR-TRK-1) ---------------------------------------------------------


def test_golden_features() -> None:
    message = "I always mess everything up and I'm not completely sure why, my friends say."
    f = features(message)
    s = extract(message)
    # 14 words; "I" and "I'm" count, possessive "my" does not (Tackman et al. 2019).
    assert f.msg_length == 14
    assert f.fp_pronoun_rate == pytest.approx(2 / 14)
    # "always" and "everything" count; "not completely" is a negated use (Al-Mosaiwi &
    # Johnstone 2018 subtract these false positives).
    assert f.absolutist_rate == pytest.approx(2 / 14)
    assert f.valence == s.valence
    assert {e: getattr(f, e) for e in EMOTIONS} == s.emotions


@pytest.mark.parametrize(("message", "count"), [
    ("I me myself", 3),
    ("Im tired and ive had enough", 2),
    ("I'd rather I'll go", 2),
    ("my mine our we you", 0),      # possessives and other persons do not count
    ("I feel ill, id card lost", 1),  # "ill" and "id" are words, not "I'll" / "I'd"
])  # fmt: skip
def test_first_person_singular_counts_subject_object_and_reflexive(
    message: str, count: int
) -> None:
    f = features(message)
    assert f.fp_pronoun_rate == pytest.approx(count / f.msg_length)


def test_curly_apostrophes_count_like_straight_ones() -> None:
    assert features("I’m done").fp_pronoun_rate == features("I'm done").fp_pronoun_rate


def test_negated_and_qualified_absolutist_words_do_not_count() -> None:
    assert features("never ever").absolutist_rate == pytest.approx(1.0)
    assert features("it was almost completely fine").absolutist_rate == 0.0
    assert features("that isn't always true").absolutist_rate == 0.0


def test_a_message_without_words_has_zero_rates() -> None:
    f = features("... !!!")
    assert (f.msg_length, f.fp_pronoun_rate, f.absolutist_rate) == (0, 0.0, 0.0)


def test_reply_latency_is_capped_and_absent_on_the_first_message() -> None:
    cap = load_config().latency_cap_s
    assert features("hi").reply_latency_s is None
    sec = datetime.timedelta(seconds=1)
    assert features("hi", last_reply_at=NOW - 42 * sec).reply_latency_s == pytest.approx(42)
    assert features("hi", last_reply_at=NOW - 2 * 3600 * sec).reply_latency_s == cap
    assert features("hi", last_reply_at=NOW + 5 * sec).reply_latency_s == 0.0  # clock skew


def test_hour_of_day_is_the_clients_local_hour() -> None:
    local = datetime.datetime.fromisoformat("2026-10-20T23:30:00+05:30")
    assert features("hi", client_ts=local).hour_of_day == 23
    assert features("hi").hour_of_day is None


# --- citations and the label (FR-TRK-3, FR-TRK-4) -------------------------------------------


def test_every_feature_has_a_source_or_is_exploratory() -> None:
    cfg = load_config()
    assert set(cfg.features) == {f.name for f in fields(TurnFeatures)}
    for name, info in cfg.features.items():
        assert bool(info.source) != info.exploratory, name
    for cited in ("valence", "fp_pronoun_rate", "absolutist_rate"):
        assert cfg.features[cited].source, cited
    assert cfg.label == "language-based mood trend, not a clinical measure"


def _raw() -> dict[str, Any]:
    feats = {f.name: {"exploratory": True} for f in fields(TurnFeatures)}
    return {
        "review_status": "needs_clinician_review",
        "label": "language-based mood trend, not a clinical measure",
        "aggregation": {"ewma_alpha": 0.3, "baseline_sessions": 5, "change_z": 1.5,
                        "latency_cap_s": 600},
        "first_person": ["i"],
        "absolutist": ["always"],
        "not_before": ["not"],
        "features": feats,
    }  # fmt: skip


def test_a_valid_config_parses() -> None:
    assert parse(_raw()).baseline_sessions == 5


@pytest.mark.parametrize("change", [
    lambda r: r.update(review_status="approved"),
    lambda r: r["features"].pop("valence"),
    lambda r: r["features"].update(extra={"exploratory": True}),
    lambda r: r["features"]["valence"].update(source="Someone (2020)"),  # both
    lambda r: r["features"].update(valence={}),                          # neither
    lambda r: r.update(label="mood score"),
    lambda r: r["aggregation"].update(ewma_alpha=1.5),
    lambda r: r["aggregation"].update(baseline_sessions=1),
    lambda r: r.update(absolutist=[]),
])  # fmt: skip
def test_an_invalid_config_is_rejected(change: Any) -> None:
    raw = _raw()
    change(raw)
    with pytest.raises(ValueError):
        parse(raw)


# --- aggregation on synthetic timelines (FR-TRK-2) ------------------------------------------


def _record(
    session: str, minute: int, valence: float, latency: float | None = None
) -> SignalRecord:
    base = features("hello")
    f = replace(base, valence=valence, reply_latency_s=latency)
    at = (NOW + datetime.timedelta(minutes=minute)).isoformat()
    return SignalRecord(session, at, f)


def test_session_mean_and_variance_are_exact() -> None:
    records = [_record("s1", 0, 0.2), _record("s1", 1, 0.4), _record("s1", 2, 0.9),
               _record("s2", 60, -0.5)]  # fmt: skip
    s1, s2 = summarise(records)
    assert (s1.session, s1.turns, s2.session, s2.turns) == (1, 3, 2, 1)
    assert s1.mean["valence"] == pytest.approx(0.5)
    assert s1.variance["valence"] == pytest.approx(0.13)  # sample variance
    assert s2.mean["valence"] == pytest.approx(-0.5)
    assert s2.variance["valence"] is None  # one turn: no spread to measure


def test_sessions_are_ordered_by_their_first_turn() -> None:
    records = [_record("late", 90, 0.1), _record("early", 0, 0.3), _record("late", 91, 0.3)]
    assert [s.turns for s in summarise(records)] == [1, 2]


def test_missing_latencies_are_left_out_of_the_mean() -> None:
    (s,) = summarise([_record("s", 0, 0.0, None), _record("s", 1, 0.0, 30.0),
                      _record("s", 2, 0.0, 50.0)])  # fmt: skip
    assert s.mean["reply_latency_s"] == pytest.approx(40.0)
    (only_first,) = summarise([_record("s", 0, 0.0, None)])
    assert only_first.mean["reply_latency_s"] is None


def test_ewma_matches_the_recurrence() -> None:
    assert ewma([0.0, 1.0, 1.0], 0.3) == pytest.approx([0.0, 0.3, 0.51])
    assert ewma([], 0.3) == []


def test_the_change_flag_waits_for_a_baseline_of_k_sessions() -> None:
    calm = [0.1, 0.2, 0.1, 0.2, 0.15]
    # A dramatic drop as the 5th session is not flagged: only 4 sessions came before it.
    assert change_flags([*calm[:4], -0.9], k=5, z=1.5) == [False] * 5
    # The same drop as the 6th session is: 5 sessions of baseline exist.
    assert change_flags([*calm, -0.9], k=5, z=1.5) == [False] * 5 + [True]


def test_the_change_flag_needs_more_than_z_baseline_sds() -> None:
    calm = [0.1, 0.2, 0.1, 0.2, 0.15]  # mean 0.15, sample SD 0.05
    assert change_flags([*calm, 0.2], k=5, z=1.5) == [False] * 6  # 1.0 SD away
    assert change_flags([*calm, 0.25], k=5, z=1.5) == [False] * 5 + [True]  # 2.0 SDs
    assert change_flags([*calm, 0.05], k=5, z=1.5) == [False] * 5 + [True]  # both directions


def test_no_flag_when_the_baseline_has_no_spread() -> None:
    assert change_flags([0.2] * 5 + [0.9], k=5, z=1.5) == [False] * 6


def test_trend_puts_it_together_for_the_current_session() -> None:
    cfg = load_config()
    records = [_record(f"s{i}", i * 60, v) for i, v in enumerate([0.1, 0.2, 0.1, 0.2, 0.15])]
    records += [_record("now", 400, -0.8), _record("now", 401, -1.0)]
    t = trend(records, "now", cfg)
    assert t.label == cfg.label
    assert len(t.sessions) == len(t.ewma) == len(t.change_flags) == 6
    assert t.change_flags[-1] is True
    assert [v for _, v in t.current] == [-0.8, -1.0]
    assert trend([], "now", cfg).sessions == []
