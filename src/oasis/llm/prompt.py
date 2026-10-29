"""Turns a plan into chat messages within a size budget (design §13)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from oasis.style.framing import framing
from oasis.types import ChatMessage, Plan, TurnRecord

SYSTEM_TEMPLATE = (
    "You are OASIS, a supportive listening companion. You are not a therapist or a doctor.\n"
    "Never diagnose. Never give medication advice. Never claim to be human.\n"
    # A demo tester asked "Who is your owner" and got "created by Google" (2026-10-29).
    "If asked who made or owns you: OASIS is an independent project that runs an open "
    "language model on its own computer; it is not made by any company.\n"
    "Never encourage them to rely on you instead of the people in their life.\n"
    "Write three sentences or fewer, in plain words, with no lists and no emojis.\n"
    "Match their tone: keep small talk light, and never make a feeling sound bigger or "
    "darker than they said it.\n"
    "Follow the PLAN exactly. Do not change its approach.\n"
    "{style}"  # the user's chosen wording (design §13.1); empty for the default style
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
    "no_question": "Do not ask a question: reflect what they said and let them know you are "
    "listening.",
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
    "no_exercise_step": "Do not write exercise steps of your own.",
    "offer_one_idea": "Offer one small, practical idea as a suggestion they can take or leave.",
    "encourage": "Add one hopeful sentence that leaves their feeling alone, such as that small "
    "steps still count. Never tell them to stay positive or look on the bright side.",
    "no_toxic_positivity": "Do not tell them to stay positive, look on the bright side, or "
    "that it could be worse.",
    "brief": "Reply in one short sentence that acknowledges what they said, with no question.",
    "no_maker_claim": "Do not say a company made you or name another assistant.",
    "ack_only": "Write one short sentence responding to them, with no question and no exercise "
    "step.",
}
# A companion reply that only listens (demo testing, 2026-10-29).
LISTEN_GOAL = "Respond to what they said and let them know you are listening."
BRIEF_GOAL = "Acknowledge what they said, warmly and briefly."
SCRIPT_MARK = "\n- script: "
# An exercise step is added after the reply word for word (the 4B model, asked to rephrase
# "T is for Take a step back", wrote "N is for Name what you are feeling"), so the step text
# is not in the prompt and the model only responds to what they said.
STEP_GOAL = (
    "They are in the middle of a short exercise. Write one short sentence that responds to "
    'what they just said, such as "That sounds really frustrating." or "Thank you for '
    'staying with this." The next step of the exercise is added after your sentence, so '
    "give no instructions, describe no step and ask no question."
)

# Known limit: characters approximate tokens (~3.5 chars/token for English). Switch to
# llama-server's /tokenize endpoint when the full token budget lands with real prompts.
# An exercise step's letter line ("T is for Take a step back.") in an earlier reply. Left in
# the history, the model copies the pattern and invents steps ("R is for Reconnect..."), so
# the prompt shows earlier replies without it; the chat itself is unchanged.
_STEP_LETTER = re.compile(r"\s*\b[A-Za-z] is for\b[^.!?]*[.!?]*")

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
    if plan.is_step:
        goal = STEP_GOAL
    elif "no_question" in plan.constraints:
        goal = LISTEN_GOAL
    elif "brief" in plan.constraints:
        goal = BRIEF_GOAL
    else:
        goal = GOALS.get(plan.mode, GOALS["companion"])
    style = framing(plan.style)
    system = SYSTEM_TEMPLATE.format(
        style=style + "\n" if style else "",
        mode=plan.mode,
        goal=goal,
        constraints=_rule_text(plan.constraints) or "none",
    )
    if plan.avoid_openers:
        system += "\n- do not begin with: " + ", ".join(f'"{o}"' for o in plan.avoid_openers)
    if plan.snippet and not plan.is_step:  # the psychoed item to explain
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
        if turn.role == "user":
            window.append(ChatMessage("user", turn.content))
        else:
            window.append(ChatMessage("assistant", _STEP_LETTER.sub("", turn.content).strip()))
    window.reverse()

    return [
        ChatMessage("system", system),
        *window,
        ChatMessage("user", message[:MESSAGE_CHAR_BUDGET]),
    ]


def _rule_text(rules: Sequence[str]) -> str:
    return " ".join(RULES.get(r, r) for r in rules)
