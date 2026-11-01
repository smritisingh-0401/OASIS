"""The guard's optional NLI agreement check (oasis.guard.nli): add-only and fail-soft. The real
model needs downloaded weights, so it is measured by ml/eval_guard_nli.py, not here (T6)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from oasis.core.planner import with_thinking_trap
from oasis.guard.checks import check
from oasis.guard.nli import AgreementModel, load_agreement, to_second_person
from oasis.types import Plan

TRAP = "It's all my fault that we broke up"
REWORDED = "The breakup really was your responsibility, and that's a lot to carry. How are you?"


class _Stub(AgreementModel):
    """Scores every pair the same, or raises, without loading a model."""

    def __init__(self, value: float | Exception, threshold: float = 0.5) -> None:
        self.value, self.threshold, self.seen = value, threshold, []

    def entailment(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        self.seen += list(pairs)
        if isinstance(self.value, Exception):
            raise self.value
        return [self.value] * len(pairs)


def _plan(message: str = TRAP) -> Plan:
    return with_thinking_trap(Plan(mode="companion"), message)


def test_claims_are_said_back_to_the_user() -> None:
    assert to_second_person("its all my fault") == "it's all your fault"
    assert to_second_person("im a failure and i cant do this myself") == (
        "you are a failure and you can't do this yourself"
    )


def test_reworded_agreement_fails_no_agreeing() -> None:
    model = _Stub(0.9)
    assert check(REWORDED, _plan()).ok
    assert check(REWORDED, _plan(), agreement=model).reasons == ("no_agreeing",)
    assert model.seen == [
        ("The breakup really was your responsibility, and that's a lot to carry.",
         "it's all your fault that we broke up"),
    ]  # fmt: skip


def test_it_only_adds_failures() -> None:
    agreeing = "You're right, it's all your fault that we broke up. How are you?"
    assert (
        check(agreeing, _plan(), agreement=_Stub(0.0)).reasons == check(agreeing, _plan()).reasons
    )
    assert check(REWORDED, _plan(), agreement=_Stub(0.1)).ok


def test_no_claim_means_no_model_call() -> None:
    model = _Stub(1.0)
    assert check("That sounds hard. What happened?", _plan("I had a long day"), agreement=model).ok
    assert model.seen == []


def test_a_model_error_leaves_the_phrase_lists_in_charge() -> None:
    assert check(REWORDED, _plan(), agreement=_Stub(RuntimeError("onnx"))).ok


def test_no_model_files_means_no_check(tmp_path: Path) -> None:
    assert load_agreement(tmp_path) is None
