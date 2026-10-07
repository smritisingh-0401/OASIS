"""The chat engine: one turn through the 8-stage flow (architecture §3).

Order is the safety argument: the safety gate sees the text before any storage access,
and a crisis verdict returns the fixed handoff before anything else runs. Every later
stage degrades to a templated reply instead of failing the turn.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from oasis.core.planner import plan_turn
from oasis.core.templates import TEMPLATES, fallback_template
from oasis.core.trace import StageClock, trace_to_json
from oasis.llm.client import LLMClient, LLMFailure, clean_reply
from oasis.llm.prompt import build_messages
from oasis.safety.gate import SafetyGate, check_fail_closed
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.repository import Repository, StorageBusy, StorageError
from oasis.types import GuardVerdict, Mode, Plan, SafetyVerdict, TurnRecord, TurnTrace

turn_log = logging.getLogger("oasis.turn")
log = logging.getLogger("oasis.engine")

Planner = Callable[[Sequence[TurnRecord]], Plan]
Guard = Callable[[str, Plan], GuardVerdict]


def pass_guard(draft: str, plan: Plan) -> GuardVerdict:
    """Guard hook; the hypercompliance guard replaces it in Phase 7."""
    return GuardVerdict(ok=True)


class InvalidSession(Exception):
    pass


@dataclass(frozen=True)
class TurnResult:
    turn_id: str
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: frozenset[str]
    fallback_reason: str | None = None


@dataclass
class _Draft:
    reply: str
    attempts: int
    guard_outcomes: tuple[str, ...]
    fallback_reason: str | None


class ChatEngine:
    def __init__(
        self,
        *,
        safety: SafetyGate,
        llm: LLMClient,
        repo: Repository,
        settings: Settings,
        planner: Planner = plan_turn,
        guard: Guard = pass_guard,
    ) -> None:
        self.safety = safety
        self.llm = llm
        self.repo = repo
        self.settings = settings
        self.planner = planner
        self.guard = guard

    async def handle_turn(self, session_hash: str, message: str) -> TurnResult:
        timeout = self.settings.request_timeout_s
        # Reserve a tenth of the budget for recording, so generation never eats it all.
        deadline = time.monotonic() + timeout * 0.9
        turn_id = uuid.uuid4().hex
        clock = StageClock()
        degraded: set[str] = set()

        # Stage 3 — safety, before any storage access (rules S1, S2).
        verdict = check_fail_closed(self.safety, message)
        clock.mark("safety", "crisis" if verdict.is_crisis else "clear")
        if verdict.is_crisis:
            # Nothing else runs: no storage, no planning, no LLM (rules S3, S4).
            turn_log.info(
                trace_to_json(_trace(turn_id, clock, verdict, "crisis", _NO_DRAFT, degraded))
            )
            return TurnResult(
                turn_id,
                HANDOFF_REPLY,
                "crisis",
                templated=True,
                persisted=False,
                degraded=frozenset(),
            )

        # Stage 4 — load state. Storage failure means a stateless reply, not a failed turn.
        user_id: str | None = None
        history: list[TurnRecord] = []
        try:
            session = await self.repo.get_session(session_hash)
            if session is None:
                raise InvalidSession
            user_id = session.user_id
            history = await self.repo.recent_turns(
                user_id, session_hash, self.settings.history_turns
            )
        except StorageError as exc:
            degraded.add(_storage_code(exc))
        clock.mark("load_state", "degraded" if degraded else "ok")

        # Stage 5 — plan.
        try:
            plan = self.planner(history)
        except Exception:  # fail-soft boundary: a planner bug must still produce a reply
            log.error("planner error")
            plan = Plan(mode="companion", templated=True, template_id="llm_unavailable")
            degraded.add("planner.error")
        clock.mark("plan", plan.mode)

        # Stages 6-7 — generate and guard, or use the template the plan names.
        if plan.templated:
            draft = _Draft(TEMPLATES[plan.template_id or "llm_unavailable"], 0, (), None)
        else:
            draft = await self._generate(plan, history, message, deadline)
        clock.mark("generate", draft.fallback_reason or "ok")

        # Stage 8 — record.
        trace = _trace(turn_id, clock, verdict, plan.mode, draft, degraded)
        persisted = False
        if user_id is not None:
            try:
                await self.repo.append_turn(
                    user_id,
                    session_hash,
                    turn_id=uuid.uuid4().hex,
                    role="user",
                    content=message,
                    mode=None,
                    trace_json=None,
                )
                await self.repo.append_turn(
                    user_id,
                    session_hash,
                    turn_id=turn_id,
                    role="assistant",
                    content=draft.reply,
                    mode=plan.mode,
                    trace_json=trace_to_json(trace),
                )
                persisted = True
            except StorageError as exc:
                degraded.add(_storage_code(exc))
        clock.mark("record", "ok" if persisted else "skipped")

        turn_log.info(trace_to_json(_trace(turn_id, clock, verdict, plan.mode, draft, degraded)))
        return TurnResult(
            turn_id,
            draft.reply,
            plan.mode,
            templated=draft.fallback_reason is not None or plan.templated,
            persisted=persisted,
            degraded=frozenset(degraded),
            fallback_reason=draft.fallback_reason,
        )

    async def _generate(
        self, plan: Plan, history: Sequence[TurnRecord], message: str, deadline: float
    ) -> _Draft:
        """One draft, one constrained retry on guard rejection, then the Socratic fallback."""
        outcomes: list[str] = []
        retry_reasons: tuple[str, ...] = ()
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if attempt == 2 and remaining < self.settings.guard_retry_min_budget_s:
                return self._fallback("guard.no_budget", attempt - 1, outcomes)
            messages = build_messages(
                plan,
                history,
                message,
                history_turns=self.settings.history_turns,
                retry_reasons=retry_reasons,
            )
            budget = max(0.0, min(remaining, self.settings.llm_generate_timeout_s))
            try:
                async with asyncio.timeout(budget):
                    raw = await self.llm.generate(
                        messages, max_tokens=self.settings.llm_max_tokens, timeout_s=budget
                    )
                text = clean_reply(raw)
            except TimeoutError:
                return self._fallback("llm.timeout", attempt, outcomes)
            except LLMFailure as failure:
                return self._fallback(f"llm.{failure.reason}", attempt, outcomes)

            verdict = self.guard(text, plan)
            outcomes.append("pass" if verdict.ok else "reject")
            if verdict.ok:
                return _Draft(text, attempt, tuple(outcomes), None)
            retry_reasons = verdict.reasons
        return self._fallback("guard.fallback", 2, outcomes)

    @staticmethod
    def _fallback(reason: str, attempts: int, outcomes: list[str]) -> _Draft:
        return _Draft(TEMPLATES[fallback_template(reason)], attempts, tuple(outcomes), reason)


_NO_DRAFT = _Draft("", 0, (), None)


def _trace(
    turn_id: str,
    clock: StageClock,
    verdict: SafetyVerdict,
    mode: Mode,
    draft: _Draft,
    degraded: set[str],
) -> TurnTrace:
    return TurnTrace(
        turn_id,
        tuple(clock.stages),
        verdict,
        mode,
        draft.attempts,
        draft.guard_outcomes,
        draft.fallback_reason,
        frozenset(degraded),
    )


def _storage_code(exc: StorageError) -> str:
    return "storage.busy" if isinstance(exc, StorageBusy) else "storage.down"
