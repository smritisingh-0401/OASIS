"""Fixed crisis reply. Zero LLM calls; no routing, companion or guard logic (rules S3, S4).

Clinician review pending: CR-03. The text is a compiled-in constant so the handoff works
even if content files cannot be read. Country-specific crisis lines are shown by the
"Need help now?" card, which the UI opens alongside this reply.
"""

from __future__ import annotations

HANDOFF_REPLY = (
    "I'm really glad you told me. It sounds like you're going through something very painful, "
    "and you deserve support from a person right now. If you are in immediate danger, please "
    'call your local emergency number. I\'ve opened "Need help now?" so you can find a crisis '
    "line in your country. You don't have to go through this alone."
)
