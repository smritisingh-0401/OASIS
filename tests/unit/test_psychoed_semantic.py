"""Optional semantic psychoeducation retrieval (oasis.psychoed.semantic): add-only, questions
only, fail-soft. The real model needs downloaded weights, so it is measured by
ml/eval_psychoed.py, not here (T6); these tests use a stand-in embedder."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from oasis.core.engine import ChatEngine
from oasis.core.planner import plan_turn
from oasis.llm.fake import FakeLLM
from oasis.psychoed.selector import load_all
from oasis.psychoed.semantic import Embedder, SemanticMatcher, is_question, load_matcher
from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset
from oasis.settings import Settings
from oasis.storage.memory import MemoryRepository
from oasis.types import ConversationState

NOW = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=datetime.UTC)
ITEMS = load_all()
SLEEP = [i.id for i in ITEMS].index("sleep")
UNCUED = "can bad sleep make my mood worse?"  # no cue phrase, asks to understand


class _Embedder(Embedder):
    """Item texts are unit vectors on their own axis; a message points at `target`."""

    def __init__(self, target: int, similarity: float = 0.8, fail: bool = False) -> None:
        self.target, self.similarity, self.fail = target, similarity, fail

    def embed(self, texts: Sequence[str]) -> Any:
        if self.fail and len(texts) == 1:
            raise RuntimeError("onnx")
        if len(texts) > 1:  # the items, at start-up
            return np.eye(len(texts))
        v = np.zeros(len(ITEMS))
        v[self.target] = self.similarity
        return v[None, :]


def _matcher(**kw: Any) -> SemanticMatcher:
    return SemanticMatcher(_Embedder(SLEEP, **kw), ITEMS, threshold=0.5)


@pytest.mark.parametrize(
    ("message", "question"),
    [(UNCUED, True), ("why am I like this", True), ("I couldn't sleep last night", False)],
)
def test_only_questions_are_matched(message: str, question: bool) -> None:
    assert is_question(message) is question
    assert (_matcher().match(message, ()) is not None) is question


def test_the_closest_item_above_the_threshold_wins() -> None:
    assert _matcher().match(UNCUED, ()) == ITEMS[SLEEP]
    assert _matcher(similarity=0.4).match(UNCUED, ()) is None
    assert _matcher().match(UNCUED, {"sleep"}) is None  # each item once per session


def test_a_model_error_means_no_item() -> None:
    assert _matcher(fail=True).match(UNCUED, ()) is None


def test_no_model_files_means_no_matcher(tmp_path: Path) -> None:
    assert load_matcher(tmp_path, ITEMS) is None


def test_the_planner_uses_the_match_only_when_the_cue_lexicon_found_nothing() -> None:
    plan = plan_turn(UNCUED, ConversationState(now=NOW, psychoed_match="sleep"))
    assert (plan.mode, plan.reason_codes) == ("psychoed", ("psychoed.sleep",))
    assert plan_turn(UNCUED, ConversationState(now=NOW)).mode != "psychoed"
    cued = "is it normal to have panic attacks?"  # the lexicon's item wins
    assert plan_turn(cued, ConversationState(now=NOW, psychoed_match="sleep")).reason_codes == (
        "psychoed.panic",
    )


@pytest.mark.anyio
async def test_the_engine_asks_the_matcher_before_planning(settings: Settings) -> None:
    engine = ChatEngine(safety=RuleBasedSafetyGate(load_ruleset()), llm=FakeLLM(),
                        repo=MemoryRepository(), settings=settings,
                        psychoed_matcher=_matcher())  # fmt: skip
    await engine.repo.create_user_session("h")
    assert (await engine.handle_turn("h", UNCUED)).mode == "psychoed"
