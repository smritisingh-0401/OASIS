"""Turns a plan into chat messages within a size budget (design §13)."""

from __future__ import annotations

from collections.abc import Sequence

from oasis.types import ChatMessage, Plan, TurnRecord

SYSTEM_TEMPLATE = (
    "You are OASIS, a supportive listening companion. You are not a therapist or a doctor.\n"
    "Never diagnose. Never give medication advice. Never claim to be human.\n"
    "Write three sentences or fewer, in plain words, with no lists and no emojis.\n"
    "Follow the PLAN exactly. Do not change its approach.\n"
    "PLAN:\n"
    "- mode: {mode}\n"
    "- goal: {goal}\n"
    "- must: {constraints}"
)

# Goal text per mode (design §13.2). The decision plane picks the mode; this only says how
# that mode should sound.
GOALS = {
    "companion": "Reflect the feeling you notice, then ask one gentle open question.",
    "cbt": "Acknowledge the feeling. Invite them to examine the thought with one Socratic "
    "question.",
    "dbt": "Acknowledge the intensity. Offer the named skill briefly and ask if they'd like "
    "to try it.",
    "mindfulness": "Guide one short, low-risk grounding step from the script.",
    "grounding": "Guide one short, low-risk grounding step from the script.",
    "psychoed": "Explain the idea in the script line in two or three plain sentences, in your "
    "own words, without diagnosing. Add nothing that is not in it.",
}
SCRIPT_MARK = "\n- script: "
STEP_GOAL = (
    "Guide them through the script step below, in your own words, keeping its meaning. "
    "Do not add steps or advice."
)

# Known limit: characters approximate tokens (~3.5 chars/token for English). Switch to
# llama-server's /tokenize endpoint when the full token budget lands with real prompts.
HISTORY_CHAR_BUDGET = 2100
MESSAGE_CHAR_BUDGET = 1050


def build_messages(
    plan: Plan,
    history: Sequence[TurnRecord],
    message: str,
    *,
    history_turns: int,
    retry_reasons: Sequence[str] = (),
) -> list[ChatMessage]:
    # A snippet is an exercise step, except in psychoed mode, where it is the item to explain.
    step = plan.snippet and plan.mode != "psychoed"
    goal = STEP_GOAL if step else GOALS.get(plan.mode, GOALS["companion"])
    system = SYSTEM_TEMPLATE.format(
        mode=plan.mode, goal=goal, constraints=", ".join(plan.constraints) or "none"
    )
    if plan.snippet:
        system += f"{SCRIPT_MARK}{plan.snippet}"
    if retry_reasons:
        system += (
            "\nYour previous draft broke these rules: "
            + ", ".join(retry_reasons)
            + ". Write a new reply that follows the plan and these rules."
        )

    window: list[ChatMessage] = []
    used = 0
    usable = [t for t in history if t.role in ("user", "assistant")]
    recent = usable[-history_turns:] if history_turns else []
    for turn in reversed(recent):  # newest first, so the oldest are dropped when over budget
        used += len(turn.content)
        if used > HISTORY_CHAR_BUDGET:
            break
        window.append(ChatMessage("user" if turn.role == "user" else "assistant", turn.content))
    window.reverse()

    return [
        ChatMessage("system", system),
        *window,
        ChatMessage("user", message[:MESSAGE_CHAR_BUDGET]),
    ]
