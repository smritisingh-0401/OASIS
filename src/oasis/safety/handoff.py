"""Fixed crisis reply. Zero LLM calls; no routing, companion or guard logic (rules S3, S4).

Phase 2 replaces this placeholder with clinician-reviewed wording and verified,
country-specific resources from the content library. The text is a compiled-in
constant so the handoff works even if content files cannot be read.
"""

from __future__ import annotations

HANDOFF_REPLY = (
    "It sounds like you may be going through something very painful right now, and you "
    "deserve support from a person. If you are in immediate danger, please call your local "
    'emergency number now. You can also open "Need help now?" at the top of the page for '
    "ways to reach someone."
)
