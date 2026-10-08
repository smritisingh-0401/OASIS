"""The chat engine: one turn through the 8-stage flow (architecture §3).

Order is the safety argument: the safety gate sees the text before any storage access,
and a crisis verdict returns the fixed handoff before anything else runs. Every later
stage degrades to a templated reply instead of failing the turn.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from oasis.assessment.flow import ITEM9, active
from oasis.core.planner import plan_turn
from oasis.core.templates import TEMPLATES, fallback_template
from oasis.core.trace import StageClock, trace_to_json
from oasis.llm.client import LLMClient, LLMFailure, clean_reply
from oasis.llm.prompt import build_messages
from oasis.safety.gate import SafetyGate, check_fail_closed
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.repository import (
    Repository,
    StorageBusy,
    StorageError,
    StorageUnavailable,
)
from oasis.types import (
    AssessmentAction,
    AssessmentCard,
    AssessmentRecord,
    ConversationState,
    GuardVerdict,
    Mode,
    Plan,
    SafetyVerdict,
    TurnRecord,
    TurnTrace,
)

# Shown in history instead of the crisis message, whose text is never stored (design §2.4).
CRISIS_PLACEHOLDER = "A message here was answered with crisis support. Its text was not saved."

turn_log = logging.getLogger("oasis.turn")
log = logging.getLogger("oasis.engine")

# Turns loaded per request: the prompt uses the last `history_turns`; the screening trigger
# reads further back (window plus consecutive turns, design §3).
HISTORY_LOAD = 20
ITEM9_VERDICT = SafetyVerdict(
    is_crisis=True, tiers=frozenset({"item9"}), pattern_ids=("assessment.phq9.item9",)
)

Planner = Callable[[str, ConversationState, AssessmentAction | None], Plan]
Guard = Callable[[str, Plan], GuardVerdict]


def pass_guard(draft: str, plan: Plan) -> GuardVerdict:
    """Guard hook; the hypercompliance guard replaces it in Phase 7."""
    return GuardVerdict(ok=True)


class InvalidSession(Exception):
    pass


_CLEAR = SafetyVerdict(is_crisis=False)


@dataclass(frozen=True)
class TurnResult:
    turn_id: str
    reply: str
    mode: Mode
    templated: bool
    persisted: bool
    degraded: frozenset[str]
    fallback_reason: str | None = None
    verdict: SafetyVerdict = _CLEAR
    card: AssessmentCard | None = None
    # Assessment escalated by a PHQ-9 item-9 answer, saved after the handoff is sent.
    escalated: AssessmentRecord | None = None


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
        # Sessions in post-crisis mode, held in memory so the policy holds even when
        # storage is down (design §2.4). Known limit: grows with crisis sessions only and is
        # lost on restart; the persisted flag covers restarts when storage works.
        self._post_crisis: set[str] = set()

    async def handle_turn(
        self, session_hash: str, message: str, action: AssessmentAction | None = None
    ) -> TurnResult:
        timeout = self.settings.request_timeout_s
        # Reserve a tenth of the budget for recording, so generation never eats it all.
        deadline = time.monotonic() + timeout * 0.9
        turn_id = uuid.uuid4().hex
        clock = StageClock()
        degraded: set[str] = set()

        # Stage 3 — safety, before any storage access (rules S1, S2).
        verdict = check_fail_closed(self.safety, message)
        if not verdict.is_crisis and _item9_positive(action):
            # Checked before storage, so a dead database cannot block the handoff (rules S11).
            verdict = ITEM9_VERDICT
        clock.mark("safety", "crisis" if verdict.is_crisis else "clear")
        if verdict.is_crisis:
            # Nothing else runs: no storage, no planning, no LLM (rules S3, S4). The audit
            # entry is written by record_crisis after the response is sent.
            return self._crisis(session_hash, turn_id, clock, verdict)

        # Stage 4 — load state. Storage failure means a stateless reply, not a failed turn.
        user_id: str | None = None
        history: list[TurnRecord] = []
        assessments: list[AssessmentRecord] = []
        post_crisis = session_hash in self._post_crisis
        try:
            session = await self.repo.get_session(session_hash)
            if session is None:
                raise InvalidSession
            user_id = session.user_id
            post_crisis = post_crisis or session.post_crisis
            history = await self.repo.recent_turns(
                user_id, session_hash, max(self.settings.history_turns, HISTORY_LOAD)
            )
            assessments = await self.repo.list_assessments(user_id)
        except StorageError as exc:
            degraded.add(_storage_code(exc))
        clock.mark("load_state", "degraded" if degraded else "ok")

        # Stage 5 — plan.
        state = ConversationState(
            tuple(history), post_crisis, tuple(assessments), datetime.datetime.now(datetime.UTC)
        )
        try:
            plan = self.planner(message, state, action)
        except Exception:  # fail-soft boundary: a planner bug must still produce a reply
            log.error("planner error")
            plan = Plan(mode="companion", templated=True, template_id="llm_unavailable")
            degraded.add("planner.error")
        clock.mark("plan", plan.mode)
        if plan.mode == "crisis":  # PHQ-9 item 9 answered positively (rules S11)
            return self._crisis(session_hash, turn_id, clock, ITEM9_VERDICT, plan.assessment)
        if "post_crisis.cleared" in plan.reason_codes:
            await self._clear_post_crisis(user_id, session_hash, degraded)
        if plan.assessment is not None:
            plan = await self._save_assessment(user_id, plan, degraded)

        # Stages 6-7 — generate and guard, or use the fixed text the plan names.
        if plan.templated:
            text = plan.text or TEMPLATES[plan.template_id or "llm_unavailable"]
            draft = _Draft(text, 0, (), None)
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
            card=plan.card,
        )

    def _crisis(
        self,
        session_hash: str,
        turn_id: str,
        clock: StageClock,
        verdict: SafetyVerdict,
        escalated: AssessmentRecord | None = None,
    ) -> TurnResult:
        self._post_crisis.add(session_hash)
        turn_log.info(trace_to_json(_trace(turn_id, clock, verdict, "crisis", _NO_DRAFT, set())))
        return TurnResult(turn_id, HANDOFF_REPLY, "crisis", templated=True, persisted=False,
                          degraded=frozenset(), verdict=verdict, escalated=escalated)  # fmt: skip

    async def _save_assessment(self, user_id: str | None, plan: Plan, degraded: set[str]) -> Plan:
        """Persist the assessment step before replying; if that fails, say so and stop."""
        try:
            if user_id is None or plan.assessment is None:
                raise StorageUnavailable
            await self.repo.save_assessment(user_id, plan.assessment)
        except StorageError as exc:
            degraded.add(_storage_code(exc))
            if plan.mode != "assessment":
                return replace(plan, assessment=None, card=None)
            return Plan(mode="assessment", templated=True, template_id="assessment_unavailable",
                        reason_codes=(*plan.reason_codes, "assessment.not_saved"))  # fmt: skip
        return plan

    async def record_crisis(
        self,
        session_hash: str,
        verdict: SafetyVerdict,
        escalated: AssessmentRecord | None = None,
    ) -> None:
        """Best-effort bookkeeping after a crisis reply has been SENT (rules S2).

        Writes the audit entry (tiers and pattern IDs, never text), persists post-crisis
        mode and leaves a placeholder in history. After a PHQ-9 item-9 answer it also marks
        the questionnaire escalated, so it is never scored. Any storage failure is logged by
        type only; it can never affect the reply, which has already gone out.
        """
        try:
            session = await self.repo.get_session(session_hash)
            if session is None:
                return
            detail = json.dumps({
                "tiers": sorted(verdict.tiers),
                "pattern_ids": list(verdict.pattern_ids),
                "ruleset_version": verdict.ruleset_version,
                "source": "item9" if "item9" in verdict.tiers else "text",
            })  # fmt: skip
            await self.repo.set_post_crisis(session.user_id, session_hash, True)
            await self.repo.append_audit(session.user_id, "crisis_handoff", detail)
            await self.repo.append_turn(session.user_id, session_hash,
                                        turn_id=uuid.uuid4().hex, role="placeholder",
                                        content=CRISIS_PLACEHOLDER, mode="crisis",
                                        trace_json=None)  # fmt: skip
            if "item9" in verdict.tiers:
                if escalated is None:
                    now = datetime.datetime.now(datetime.UTC)
                    open_rec, _ = active(await self.repo.list_assessments(session.user_id), now)
                    if open_rec is not None and open_rec.instrument == "PHQ9":
                        escalated = replace(open_rec, status="escalated")
                if escalated is not None:
                    await self.repo.save_assessment(session.user_id, escalated)
        except StorageError as exc:
            log.error("crisis audit not written: %s", type(exc).__name__)

    async def _clear_post_crisis(
        self, user_id: str | None, session_hash: str, degraded: set[str]
    ) -> None:
        self._post_crisis.discard(session_hash)
        if user_id is None:
            return
        try:
            await self.repo.set_post_crisis(user_id, session_hash, False)
        except StorageError as exc:
            degraded.add(_storage_code(exc))

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


def _item9_positive(action: AssessmentAction | None) -> bool:
    return (
        action is not None
        and action.kind == "answer"
        and (action.instrument, action.item) == ITEM9
        and (action.value or 0) >= 1
    )


def _storage_code(exc: StorageError) -> str:
    return "storage.busy" if isinstance(exc, StorageBusy) else "storage.down"
