"""The guard hook every generated reply passes through (design §8.3).

Phase 7 replaces `pass_guard` with the hypercompliance, diagnosis, medication and companion
checks; the engine calls it the same way, so nothing else changes then.
"""

from __future__ import annotations

from oasis.types import GuardVerdict, Plan


def pass_guard(draft: str, plan: Plan) -> GuardVerdict:
    return GuardVerdict(ok=True)
