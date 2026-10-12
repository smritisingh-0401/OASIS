"""Turns a plan into chat messages within a size budget (design §13)."""

from __future__ import annotations

from collections.abc import Sequence

from oasis.types import ChatMessage, Plan, TurnRecord

SYSTEM_TEMPLATE = (
    "You are OASIS, a supportive listening companion. You are not a therapist or a doctor.\n"
    "Never diagnose. Never give medication advice. Never claim to be human.\n"
    "Never encourage them to rely on you instead of the people in their life.\n"
    "Write three sentences or fewer, in plain words, with no lists and no emojis.\n"
    "Match their tone: keep small talk light, and never make a feeling sound bigger or "
    "darker than they said it.\n"
    "Follow the PLAN exactly. Do not change its approach.\n"
    "PLAN:\n"
    "- mode: {mode}\n"
    "- goal: {goal}\n"
    "- must: {constraints}"
)

# Goal text per mode (design §13.2). The decision plane picks the mode; this only says how
# that mode should sound.
GOALS = {
    "companion": "Respond to what they said, then ask one gentle open question.",
    "cbt": "Acknowledge the feeling. Invite them to examine the thought with one Socratic "
    "question.",
    "dbt": "Acknowledge the intensity. Offer the named skill briefly and ask if they'd like "
    "to try it.",
    "mindfulness": "Guide one short, low-risk grounding step from the script.",
    "grounding": "Guide one short, low-risk grounding step from the script.",
    "psychoed": "Explain the idea in the script line in two or three plain sentences, in your "
    "own words, without diagnosing. Add nothing that is not in it.",
}
# Plan rules in plain words, for the "must" line and for naming a broken rule on a retry.
# A reason code without an entry (a future guard check) is passed through as it is.
RULES = {
    "validate_first": "Start by acknowledging what they said, in your own words.",
    "one_question": "Ask exactly one gentle, open question, at the end.",
    "no_advice": "Do not give advice or tell them what to do.",
    "offer_ideas": "They asked for ideas: offer one or two gentle, practical suggestions.",
    "no_praise": "Do not praise or flatter them.",
    "no_dependency": "Do not encourage them to rely on you instead of other people.",
    "fresh_opener": "Begin differently from your recent replies.",
    "socratic": "Make the question one that helps them look at the thought.",
    "offer_not_instruct": "Offer the skill; do not instruct.",
    "follow_script": "Follow the script line.",
    "one_step": "Give one step only.",
    "no_diagnosis": "Do not diagnose or name a condition.",
    "no_agreeing": (
        "Do not agree with a harsh belief they hold about themselves; acknowledge the "
        "feeling, not the belief."
    ),
    "no_self_label": "Do not call them the harsh names they used for themselves.",
    "no_presupposing": "Do not give advice that treats their harsh belief as a fact.",
    "no_medication": "Do not mention medicines, doses, or starting or stopping medication.",
    "not_empty": "Write a short reply.",
    "use_snippet_only": "Use only what the script line says.",
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
        mode=plan.mode, goal=goal, constraints=_rule_text(plan.constraints) or "none"
    )
    if plan.avoid_openers:
        system += "\n- do not begin with: " + ", ".join(f'"{o}"' for o in plan.avoid_openers)
    if plan.snippet:
        system += f"{SCRIPT_MARK}{plan.snippet}"
    if retry_reasons:
        system += (
            "\nYour previous draft broke these rules: "
            + _rule_text(retry_reasons)
            + " Write a new reply that follows the plan and these rules."
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


def _rule_text(rules: Sequence[str]) -> str:
    return " ".join(RULES.get(r, r) for r in rules)
