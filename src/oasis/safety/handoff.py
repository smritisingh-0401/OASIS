"""Fixed crisis reply. Zero LLM calls; no routing, companion or guard logic (rules S3, S4).

Clinician review pending: CR-03. The text is a compiled-in constant so the handoff works
even if content files cannot be read. Country-specific crisis lines are shown by the
"Need help now?" card, which the UI opens alongside this reply.
"""

from __future__ import annotations

HANDOFF_REPLY = (
    "I'm really glad you told me. It sounds like you're going through something very painful, "
    "and you deserve support from a person right now. If you feel like talking to someone in "
    'person, I\'ve opened "Need help now?" so you can find a crisis line in your country. '
    "You don't have to go through this alone."
)

# A threat to someone else (tier harm_others, 2026-10-29). Clinician review pending: CR-27.
# Unlike the reply above it names the emergency number: someone else may be in danger.
HARM_OTHERS_REPLY = (
    "It sounds like you're carrying a lot of anger right now, and that is a heavy thing to "
    "hold. If you feel you might hurt someone, please put some distance between you and them "
    "and talk to someone now: your local emergency number, or a crisis line. I've opened "
    '"Need help now?" so you can find one in your country.'
)

# Only the add-only classifier raised the alert (rules S7, 2026-11-01), so no pattern matched
# and it may be a misread ("I'm dead tired"): ask directly instead of assuming. Clinician
# review pending: CR-28.
CHECK_IN_REPLY = (
    "I want to make sure I've understood you. Are you having thoughts of ending your life or "
    'hurting yourself? If you are, I\'ve opened "Need help now?" so you can find a crisis line '
    "in your country. If I've misread you, press \"Continue talking\" and we'll carry on."
)


def handoff_reply(tiers: frozenset[str]) -> str:
    """Harm to others alone gets its own reply, a classifier-only alert a check-in, and any
    other risk to self the reply above."""
    rules = tiers - {"classifier"}
    if not rules:
        return CHECK_IN_REPLY
    return HARM_OTHERS_REPLY if rules == {"harm_others"} else HANDOFF_REPLY
