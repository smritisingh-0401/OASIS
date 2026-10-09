"""PHQ-9 / GAD-7 state machine (design §4.1): pure functions from a record and an input to
the next record and what to show. Persistence is the engine's job.

offered -> declined | in_progress;  in_progress -> paused | aborted | escalated | scored;
paused -> in_progress | aborted (stop, or 24 h after the questionnaire started).
"""

from __future__ import annotations

import datetime
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from oasis.assessment.instruments import Instrument, instrument, score, texts
from oasis.assessment.trigger import config
from oasis.types import (
    ACTIVE_STATUSES,
    AssessmentAction,
    AssessmentCard,
    AssessmentRecord,
    InstrumentId,
)

ITEM9 = ("PHQ9", 9)  # any answer >= 1 triggers the crisis protocol (rules S11)


@dataclass(frozen=True)
class Step:
    record: AssessmentRecord | None  # state to persist; None when nothing changed
    text: str | None  # fixed reply; None means "answer the message normally"
    card: AssessmentCard | None = None
    escalate: bool = False
    preface: str | None = None  # a separate message shown before `text`


def offer(inst_id: InstrumentId, reason: str, now: datetime.datetime) -> Step:
    rec = AssessmentRecord(uuid.uuid4().hex, inst_id, "offered", reason, _iso(now))
    inst = instrument(inst_id)
    return Step(rec, _step_text(f"offer_{inst_id}"), AssessmentCard("offer", inst_id, inst.name))


def active(
    records: Sequence[AssessmentRecord], now: datetime.datetime
) -> tuple[AssessmentRecord | None, AssessmentRecord | None]:
    """The open assessment, if any, and an abort record for one that has expired."""
    rec = next((r for r in reversed(records) if r.status in ACTIVE_STATUSES), None)
    if rec is None:
        return None, None
    started = datetime.datetime.fromisoformat(rec.created_at)
    if rec.status == "paused" and now - started >= config().paused_expiry:
        return None, _aborted(rec, now)
    return rec, None


def card_for(rec: AssessmentRecord) -> AssessmentCard | None:
    """The card an open assessment shows right now, so a reloaded page can show it again."""
    inst = instrument(rec.instrument)
    if rec.status == "offered":
        return AssessmentCard("offer", inst.id, inst.name)
    if rec.status == "paused":
        return _paused_card(rec, inst)
    if rec.status == "in_progress":
        return _show(rec, inst, changed=False).card
    return None


def on_action(rec: AssessmentRecord, action: AssessmentAction, now: datetime.datetime) -> Step:
    inst = instrument(rec.instrument)
    kind, status = action.kind, rec.status
    if status == "offered" and kind == "accept":
        return _show(replace(rec, status="in_progress"), inst, changed=True, intro=True)
    if status == "offered" and kind in ("decline", "abort"):
        return Step(_declined(rec, "button", now), _step_text("declined"))
    if status == "in_progress" and kind == "answer":
        return _answer(rec, inst, action, now)
    if status == "in_progress" and kind == "pause":
        return Step(replace(rec, status="paused"), _step_text("paused"), _paused_card(rec, inst))
    if status == "paused" and kind == "resume":
        return _show(replace(rec, status="in_progress"), inst, changed=True, intro=True)
    if status in ("in_progress", "paused") and kind == "abort":
        return Step(_aborted(rec, now), _step_text("aborted"))
    # A stale or repeated click: show the current step again and change nothing.
    if status == "paused":
        return Step(None, _step_text("paused"), _paused_card(rec, inst))
    if status == "offered":
        return replace(offer(rec.instrument, rec.offer_reason, now), record=None)
    return _show(rec, inst, changed=False)


def on_free_text(rec: AssessmentRecord, now: datetime.datetime) -> Step:
    """Typing instead of pressing a button: an open offer lapses, a questionnaire pauses."""
    if rec.status == "offered":
        return Step(_declined(rec, "free_text", now), None)
    if rec.status == "in_progress":
        inst = instrument(rec.instrument)
        return Step(replace(rec, status="paused"), None, _paused_card(rec, inst))
    return Step(None, None)


def _answer(
    rec: AssessmentRecord, inst: Instrument, action: AssessmentAction, now: datetime.datetime
) -> Step:
    expected = _next_item(rec, inst)
    if action.instrument != rec.instrument or action.item != expected or action.value is None:
        return _show(rec, inst, changed=False)
    if expected is None:  # the functional question: recorded, never scored
        total, band = score(inst, rec.answers)
        done = replace(rec, status="scored", functional=action.value, total=total, band=band,
                       completed_at=_iso(now))  # fmt: skip
        return _result(done, inst)
    rec = replace(rec, answers=(*rec.answers, action.value))
    if (rec.instrument, expected) == ITEM9 and action.value >= 1:
        return Step(replace(rec, status="escalated", completed_at=_iso(now)), None, escalate=True)
    if len(rec.answers) == len(inst.items) and inst.functional_question is None:
        total, band = score(inst, rec.answers)
        return _result(replace(rec, status="scored", total=total, band=band,
                               completed_at=_iso(now)), inst)  # fmt: skip
    return _show(rec, inst, changed=True)


def _next_item(rec: AssessmentRecord, inst: Instrument) -> int | None:
    """1-based index of the next item, or None when only the functional question is left."""
    return len(rec.answers) + 1 if len(rec.answers) < len(inst.items) else None


def _show(rec: AssessmentRecord, inst: Instrument, *, changed: bool, intro: bool = False) -> Step:
    """`intro`: on starting or resuming, the instrument's instruction comes first in the chat."""
    item = _next_item(rec, inst)
    n = len(inst.items)
    if item is None:
        card = AssessmentCard("functional", inst.id, inst.name, None, n, inst.functional_options)
        return Step(rec if changed else None,
                    f"{_step_text('functional')} {inst.functional_question}", card)  # fmt: skip
    card = AssessmentCard("item", inst.id, inst.name, item, n, inst.options)
    text = f"Question {item} of {n}: {inst.items[item - 1]}"
    return Step(rec if changed else None, text, card, preface=inst.stem if intro else None)


def _result(rec: AssessmentRecord, inst: Instrument) -> Step:
    doc = texts()
    text = (
        f"Your {inst.name} score is {rec.total} out of {inst.max_total} ({rec.band}). "
        f"{doc[inst.id][str(rec.band)]} {doc['disclaimer']}"
    )
    card = AssessmentCard("result", inst.id, inst.name, total=rec.total, band=rec.band)
    return Step(rec, text, card)


def _paused_card(rec: AssessmentRecord, inst: Instrument) -> AssessmentCard:
    return AssessmentCard("paused", inst.id, inst.name, item=_next_item(rec, inst),
                          item_count=len(inst.items))  # fmt: skip


def _declined(rec: AssessmentRecord, by: str, now: datetime.datetime) -> AssessmentRecord:
    reason = {**json.loads(rec.offer_reason), "declined_by": by}
    return replace(rec, status="declined", offer_reason=json.dumps(reason), completed_at=_iso(now))


def _aborted(rec: AssessmentRecord, now: datetime.datetime) -> AssessmentRecord:
    return replace(rec, status="aborted", answers=(), functional=None, completed_at=_iso(now))


def _step_text(key: str) -> str:
    return str(texts()["steps"][key])


def _iso(now: datetime.datetime) -> str:
    return now.astimezone(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
