from __future__ import annotations

from oasis.llm.prompt import build_messages
from oasis.types import Plan, TurnRecord

PLAN = Plan(mode="companion", constraints=("one_question",))


def _turn(seq: int, role: str, content: str) -> TurnRecord:
    return TurnRecord(f"t{seq}", seq, role, content, None, "2026-01-01T00:00:00.000Z")  # type: ignore[arg-type]


def test_system_first_user_last_and_plan_in_system() -> None:
    msgs = build_messages(PLAN, [], "hi", history_turns=6)
    assert msgs[0].role == "system"
    assert "companion" in msgs[0].content
    assert "Ask exactly one gentle, open question" in msgs[0].content
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "hi"


def test_history_window_keeps_most_recent_turns_in_order() -> None:
    history = [_turn(i, "user" if i % 2 else "assistant", f"m{i}") for i in range(1, 11)]
    msgs = build_messages(PLAN, history, "now", history_turns=4)
    assert [m.content for m in msgs[1:-1]] == ["m7", "m8", "m9", "m10"]


def test_placeholder_turns_never_enter_the_prompt() -> None:
    history = [_turn(1, "user", "a"), _turn(2, "placeholder", "Crisis support was shown.")]
    msgs = build_messages(PLAN, history, "b", history_turns=6)
    assert all("Crisis support" not in m.content for m in msgs)


def test_history_char_budget_drops_oldest_first() -> None:
    history = [_turn(1, "user", "x" * 5000), _turn(2, "assistant", "recent")]
    msgs = build_messages(PLAN, history, "now", history_turns=6)
    assert [m.content for m in msgs[1:-1]] == ["recent"]


def test_retry_constraints_are_added_to_system_prompt() -> None:
    msgs = build_messages(PLAN, [], "hi", history_turns=6, retry_reasons=("G-AGREE",))
    assert "G-AGREE" in msgs[0].content


def test_each_mode_gets_its_goal_from_the_prompt_table() -> None:
    for mode, phrase in [("companion", "Respond to what they said"), ("cbt", "Socratic question"),
                         ("dbt", "named skill"), ("mindfulness", "grounding step")]:  # fmt: skip
        msgs = build_messages(Plan(mode=mode), [], "hi", history_turns=6)  # type: ignore[arg-type]
        assert phrase in msgs[0].content


def test_an_exercise_step_is_not_given_to_the_model_to_rephrase() -> None:
    plan = Plan(mode="grounding", constraints=("ack_only",), snippet="Name five things.")
    system = build_messages(plan, [], "ok", history_turns=6)[0].content
    assert "Name five things." not in system
    assert "one short sentence" in system
    assert "no question and no exercise step" in system


def test_earlier_step_letters_are_left_out_of_the_history() -> None:
    # Manual testing, 2026-10-13: shown "T is for Take a step back." in the history, the model
    # wrote "R is for Reconnect with what feels safe." in the next companion reply.
    step = _turn(1, "assistant", "That makes sense. T is for Take a step back. Give yourself a "
                 "little space.")  # fmt: skip
    msgs = build_messages(PLAN, [step], "i think i can restart", history_turns=6)
    assert msgs[1].content == "That makes sense. Give yourself a little space."


def test_no_script_line_without_a_step() -> None:
    assert "- script:" not in build_messages(PLAN, [], "hi", history_turns=6)[0].content
