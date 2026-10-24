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
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from oasis.assessment.flow import ITEM9, active
from oasis.core.planner import plan_turn
from oasis.core.signals import extract
from oasis.core.templates import TEMPLATES, fallback_template
from oasis.core.trace import StageClock, trace_to_json
from oasis.explain.builder import build as build_explanation
from oasis.explain.builder import unavailable
from oasis.guard.checks import SOFT_RULES
from oasis.guard.checks import check as check_reply
from oasis.guard.socratic import socratic_question
from oasis.llm.client import LLMClient, LLMFailure, clean_reply
from oasis.llm.prompt import build_messages
from oasis.router.router import dump_state, load_state
from oasis.safety.gate import SafetyGate, check_fail_closed
from oasis.safety.handoff import HANDOFF_REPLY
from oasis.settings import Settings
from oasis.storage.repository import (
    Repository,
    StorageBusy,
    StorageError,
    UserSettings,
)
from oasis.style.suggest import suggest
from oasis.tracking.features import turn_features
from oasis.types import (
    AssessmentAction,
    AssessmentCard,
    AssessmentRecord,
    ConversationState,
    ExerciseAction,
    ExerciseCard,
    GuardVerdict,
    Mode,
    Plan,
    RouterState,
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

Action = AssessmentAction | ExerciseAction
Planner = Callable[[str, ConversationState, Action | None], Plan]
Guard = Callable[[str, Plan], GuardVerdict]
Explainer = Callable[..., str]  # (message, plan, *, typed, attempts, ...) -> explanation JSON


class InvalidSession(Exception):
    pass


class ConsentRequired(Exception):
    """A non-crisis message from a session that has not accepted the current data notice."""


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
    exercise_card: ExerciseCard | None = None
    # Assessment escalated by a PHQ-9 item-9 answer, saved after the handoff is sent.
    escalated: AssessmentRecord | None = None
    preface: str | None = None  # shown as its own message before `reply`
    explanation_id: str | None = None  # the reply's turn ID, once its explanation is stored
    # Their recent messages are hedged: point them to the indirect style in Settings. Only a
    # suggestion; the profile is never changed here (FR-CUL-2).
    style_suggestion: bool = False


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
        guard: Guard = check_reply,
        explainer: Explainer = build_explanation,
        consent_version: str | None = None,
    ) -> None:
        self.safety = safety
        self.llm = llm
        self.repo = repo
        self.settings = settings
        self.planner = planner
        self.guard = guard
        self.explainer = explainer
        # The data notice a session must have accepted before a non-crisis reply (FR-PRV-1);
        # None turns the gate off (engine unit tests). The app always sets it.
        self.consent_version = consent_version
        # Sessions known to have accepted it, so the gate holds through a storage outage
        # without locking them out (architecture §3.3). Same lifetime as _post_crisis.
        self._consented: set[str] = set()
        # Sessions in post-crisis mode, held in memory so the policy holds even when
        # storage is down (design §2.4). Known limit: grows with crisis sessions only and is
        # lost on restart; the persisted flag covers restarts when storage works.
        self._post_crisis: set[str] = set()

    async def handle_turn(
        self,
        session_hash: str,
        message: str,
        action: Action | None = None,
        *,
        client_ts: datetime.datetime | None = None,
    ) -> TurnResult:
        received_at = datetime.datetime.now(datetime.UTC)
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
        router_state = RouterState()
        chosen = UserSettings()
        post_crisis = session_hash in self._post_crisis
        try:
            session = await self.repo.get_session(session_hash)
            if session is None:
                raise InvalidSession
            user_id = session.user_id
            if session.consent_version == self.consent_version:
                self._consented.add(session_hash)
            post_crisis = post_crisis or session.post_crisis
            router_state = load_state(session.router_state)
            history = await self.repo.recent_turns(
                user_id, session_hash, max(self.settings.history_turns, HISTORY_LOAD)
            )
            assessments = await self.repo.list_assessments(user_id)
            chosen = await self.repo.get_settings(user_id)
        except StorageError as exc:
            degraded.add(_storage_code(exc))
        clock.mark("load_state", "degraded" if degraded else "ok")
        if self.consent_version is not None and session_hash not in self._consented:
            # After the safety gate, so a crisis is always answered (architecture §3.3).
            raise ConsentRequired

        # Stage 5 — plan.
        state = ConversationState(
            tuple(history),
            post_crisis,
            tuple(assessments),
            datetime.datetime.now(datetime.UTC),
            router_state,
        )
        try:
            plan = self.planner(message, state, action)
        except Exception:  # fail-soft boundary: a planner bug must still produce a reply
            log.error("planner error")
            plan = Plan(mode="companion", templated=True, template_id="llm_unavailable")
            degraded.add("planner.error")
        # After planning, so the style can change how a reply is worded but never what it
        # does (FR-CUL-3, invariance test).
        plan = replace(plan, style=chosen.style)
        clock.mark("plan", plan.mode)
        if plan.mode == "crisis":  # PHQ-9 item 9 answered positively (rules S11)
            return self._crisis(session_hash, turn_id, clock, ITEM9_VERDICT, plan.assessment)
        if "post_crisis.cleared" in plan.reason_codes:
            self._post_crisis.discard(session_hash)
            await self._best_effort(
                user_id, degraded, lambda uid: self.repo.set_post_crisis(uid, session_hash, False)
            )
        if plan.assessment is not None:
            plan = await self._save_assessment(user_id, plan, degraded)
        rs = plan.router_state
        if rs is not None and rs != router_state:
            # If saving fails, this reply is still right; the next turn starts from the last
            # saved router memory.
            await self._best_effort(
                user_id, degraded,
                lambda uid: self.repo.set_router_state(uid, session_hash, dump_state(rs)),
            )  # fmt: skip

        # Stages 6-7 — generate and guard, or use the fixed text the plan names.
        if plan.templated:
            text = plan.text or TEMPLATES[plan.template_id or "llm_unavailable"]
            draft = _Draft(text, 0, (), None)
        else:
            draft = await self._generate(plan, history, message, deadline)
            if plan.is_step and draft.fallback_reason is None:
                draft.reply = f"{draft.reply} {plan.snippet}"  # the step itself, as written
        clock.mark("generate", draft.fallback_reason or "ok")

        # Stage 8 — explain, now that every decision is final, then record.
        try:
            explanation = self.explainer(
                message,
                plan,
                typed=action is None,
                attempts=draft.attempts,
                guard_outcomes=draft.guard_outcomes,
                fallback_reason=draft.fallback_reason,
            )
        except Exception:  # fail-soft boundary (FR-XAI-1): the reply never depends on it
            log.error("explanation error")
            explanation = unavailable("explain.error")
            degraded.add("explain.error")
        clock.mark("explain", "error" if "explain.error" in degraded else "ok")
        trace = _trace(turn_id, clock, verdict, plan, draft, degraded)
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
                if plan.preface is not None:
                    await self.repo.append_turn(
                        user_id,
                        session_hash,
                        turn_id=uuid.uuid4().hex,
                        role="assistant",
                        content=plan.preface,
                        mode=plan.mode,
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
                    explanation_json=explanation,
                )
                persisted = True
            except StorageError as exc:
                degraded.add(_storage_code(exc))
        if persisted and action is None:
            # Language features of what they typed (design §9.1); a button press is not
            # their words. Numbers only; a failed write never fails the turn.
            features = turn_features(
                message,
                extract(message),
                received_at=received_at,
                last_reply_at=_last_reply_at(history),
                client_ts=client_ts,
            )
            await self._best_effort(
                user_id, degraded, lambda uid: self.repo.append_signals(uid, session_hash, features)
            )
        clock.mark("record", "ok" if persisted else "skipped")

        turn_log.info(trace_to_json(_trace(turn_id, clock, verdict, plan, draft, degraded)))
        return TurnResult(
            turn_id,
            draft.reply,
            plan.mode,
            templated=draft.fallback_reason is not None or plan.templated,
            persisted=persisted,
            degraded=frozenset(degraded),
            fallback_reason=draft.fallback_reason,
            card=plan.card,
            exercise_card=plan.exercise_card,
            preface=plan.preface,
            explanation_id=turn_id if persisted else None,
            style_suggestion=action is None
            and not plan.templated
            and suggest(message, [t.content for t in history if t.role == "user"], plan.style),
        )

    def remember_consent(self, session_hash: str) -> None:
        self._consented.add(session_hash)

    def forget(self, session_hash: str) -> None:
        """Drop what the engine holds in memory about a deleted session."""
        self._consented.discard(session_hash)
        self._post_crisis.discard(session_hash)

    def _crisis(
        self,
        session_hash: str,
        turn_id: str,
        clock: StageClock,
        verdict: SafetyVerdict,
        escalated: AssessmentRecord | None = None,
    ) -> TurnResult:
        self._post_crisis.add(session_hash)
        crisis_plan = Plan(mode="crisis", templated=True)
        turn_log.info(trace_to_json(_trace(turn_id, clock, verdict, crisis_plan, _NO_DRAFT, set())))
        return TurnResult(turn_id, HANDOFF_REPLY, "crisis", templated=True, persisted=False,
                          degraded=frozenset(), verdict=verdict, escalated=escalated)  # fmt: skip

    async def _save_assessment(self, user_id: str | None, plan: Plan, degraded: set[str]) -> Plan:
        """Persist the assessment step before replying; if that fails, say so and stop."""
        rec = plan.assessment
        if rec is None or await self._best_effort(
            user_id, degraded, lambda uid: self.repo.save_assessment(uid, rec)
        ):
            return plan
        if plan.mode != "assessment":
            return replace(plan, assessment=None, card=None)
        return Plan(mode="assessment", templated=True, template_id="assessment_unavailable",
                    reason_codes=(*plan.reason_codes, "assessment.not_saved"))  # fmt: skip

    async def _best_effort(
        self, user_id: str | None, degraded: set[str], write: Callable[[str], Awaitable[None]]
    ) -> bool:
        """One storage write; a failure (or no user, after a failed load) is recorded in
        `degraded`, never raised. True if the write happened."""
        if user_id is None:
            degraded.add("storage.down")
            return False
        try:
            await write(user_id)
        except StorageError as exc:
            degraded.add(_storage_code(exc))
            return False
        return True

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

    async def _generate(
        self, plan: Plan, history: Sequence[TurnRecord], message: str, deadline: float
    ) -> _Draft:
        """One draft, one constrained retry on guard rejection, then the Socratic fallback."""
        outcomes: list[str] = []
        retry_reasons: tuple[str, ...] = ()
        seed = len(history)  # deterministic per turn, and varies along a conversation
        # A draft whose only faults are style rules (a repeated opener) is retried, but kept
        # rather than replaced by the fixed fallback if the retry does no better.
        soft: _Draft | None = None
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if attempt == 2 and remaining < self.settings.guard_retry_min_budget_s:
                return soft or _fallback(plan, "guard.no_budget", attempt - 1, outcomes, seed)
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
                if plan.is_step:
                    # The model tends to run on into a step of its own ("N is for Notice…")
                    # after a good first sentence: keep only that sentence.
                    text = _FIRST_SENTENCE.match(text).group(0).strip()  # type: ignore[union-attr]
            except TimeoutError:
                return soft or _fallback(plan, "llm.timeout", attempt, outcomes, seed)
            except LLMFailure as failure:
                return soft or _fallback(plan, f"llm.{failure.reason}", attempt, outcomes, seed)

            verdict = self.guard(text, plan)
            outcomes.append("pass" if verdict.ok else "reject")
            if verdict.ok:
                return _Draft(text, attempt, tuple(outcomes), None)
            if soft is None and set(verdict.reasons) <= SOFT_RULES:
                soft = _Draft(text, attempt, tuple(outcomes), None)
            retry_reasons = verdict.reasons
        return soft or _fallback(plan, "guard.fallback", 2, outcomes, seed)


def _fallback(plan: Plan, reason: str, attempts: int, outcomes: list[str], seed: int) -> _Draft:
    if plan.snippet:  # an exercise step or item is its own vetted fallback, so it carries on
        text = plan.snippet
    elif reason.startswith("guard.") and (plan.distortion_types or plan.mode in ("cbt", "dbt")):
        # Reroute (design §8.3): validate the feeling, then one vetted Socratic question.
        text = socratic_question(plan.distortion_types, seed)
    else:
        text = TEMPLATES[fallback_template(reason)]
    return _Draft(text, attempts, tuple(outcomes), reason)


_NO_DRAFT = _Draft("", 0, (), None)
_FIRST_SENTENCE = re.compile(r"\s*[^.!?]*[.!?]*")  # always matches, possibly empty


def _trace(
    turn_id: str,
    clock: StageClock,
    verdict: SafetyVerdict,
    plan: Plan,
    draft: _Draft,
    degraded: set[str],
) -> TurnTrace:
    return TurnTrace(
        turn_id,
        tuple(clock.stages),
        verdict,
        plan.mode,
        draft.attempts,
        draft.guard_outcomes,
        draft.fallback_reason,
        frozenset(degraded),
        plan.reason_codes,
        plan.route,
    )


def _last_reply_at(history: Sequence[TurnRecord]) -> datetime.datetime | None:
    """When OASIS last replied in this session (server time), for the reply latency."""
    last = next((t for t in reversed(history) if t.role == "assistant"), None)
    return datetime.datetime.fromisoformat(last.created_at) if last else None


def _item9_positive(action: Action | None) -> bool:
    return (
        isinstance(action, AssessmentAction)
        and action.kind == "answer"
        and (action.instrument, action.item) == ITEM9
        and (action.value or 0) >= 1
    )


def _storage_code(exc: StorageError) -> str:
    return "storage.busy" if isinstance(exc, StorageBusy) else "storage.down"
