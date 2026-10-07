"""Planner hook. Phase 1 is a pass-through to companion mode; the fixed-precedence planner
(post-crisis → assessment → psychoeducation → offer → router/companion) arrives in Phases 3-6.
"""

from __future__ import annotations

from collections.abc import Sequence

from oasis.types import Plan, TurnRecord


def plan_turn(history: Sequence[TurnRecord]) -> Plan:
    return Plan(mode="companion", reason_codes=("planner.passthrough",))
