"""Mode decision with margin, hysteresis, acute override and the mid-exercise hold (design §7.2).

Pure functions over frozen state: the planner passes the session's RouterState in and
persists the returned one. Hysteresis lives here rather than in its own module because it
is one rule inside `route`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, replace

from oasis.router.exercise import load_all
from oasis.router.weights import RouterConfig, config, features, score_modes
from oasis.types import ROUTER_MODES, RouteDecision, RouterMode, RouterState, Signals


def route(
    signals: Signals,
    rs: RouterState,
    *,
    extra: Mapping[str, float] | None = None,
    cfg: RouterConfig | None = None,
) -> RouteDecision:
    cfg = cfg or config()
    scores = score_modes(features(signals, extra), cfg)

    def decide(reason: str, state: RouterState, offer: RouterMode | None = None) -> RouteDecision:
        return RouteDecision(state.current, reason, scores, state, offer)

    # Grounding keeps going under fresh overwhelm instead of restarting at step one; any
    # other exercise gives way to the acute override below.
    acute = signals.overwhelm >= cfg.acute_threshold
    if rs.exercise is not None and not signals.opt_out and (rs.current == "grounding" or not acute):
        return decide("mid_exercise_hold", rs)
    if acute:
        # Immediate, even mid-hysteresis or mid-exercise; consents and shown items are kept.
        fresh = RouterState(current="grounding", consented=rs.consented,
                            psychoed_shown=rs.psychoed_shown)  # fmt: skip
        return decide("acute_override", fresh)

    rs = replace(rs, exercise=None, step=0)  # opted out (or nothing was running)
    if rs.current == "grounding":
        rs = replace(rs, current="companion")  # grounding lasts as long as its script
    if rs.offered is not None:
        # Typing instead of answering counts as "not now"; the lead must build up again.
        rs = replace(rs, offered=None, challenger=None, streak=0)

    leader, runner = scores[0], scores[1]
    if leader.mode == rs.current:
        return decide("incumbent", replace(rs, challenger=None, streak=0))
    if leader.score - runner.score < cfg.margin:
        return decide("margin_not_met", rs)
    streak = rs.streak + 1 if leader.mode == rs.challenger else 1
    rs = replace(rs, challenger=leader.mode, streak=streak)
    if streak < cfg.hysteresis_turns:
        return decide(f"hysteresis.{streak}_of_{cfg.hysteresis_turns}", rs)
    if leader.mode != "companion" and leader.mode not in rs.consented:
        return decide("offer_structured_mode", replace(rs, offered=leader.mode), leader.mode)
    return decide("switch", replace(rs, current=leader.mode, challenger=None, streak=0))


_CURRENT = frozenset({*ROUTER_MODES, "grounding"})
_STRUCTURED = frozenset(ROUTER_MODES) - {"companion"}


def dump_state(rs: RouterState) -> str:
    data = asdict(rs)
    data["consented"] = sorted(rs.consented)
    data["psychoed_shown"] = sorted(rs.psychoed_shown)
    return json.dumps(data, separators=(",", ":"))


def load_state(text: str) -> RouterState:
    """Parse stored router memory; anything malformed starts over in companion mode.

    The row is our own data, but a bad one must never break a turn, and a fresh start is
    always a safe state (the user just gets companion replies until cues build up again).
    """
    try:
        raw = json.loads(text)
        sets = {k: frozenset(raw.get(k, ())) for k in ("consented", "psychoed_shown")}
        rs = RouterState(**{**raw, **sets})
    except (ValueError, TypeError, AttributeError):
        return RouterState()
    steps = len(load_all()[rs.exercise].steps) if rs.exercise in load_all() else 0
    valid = (
        rs.current in _CURRENT
        and rs.challenger in {None, *ROUTER_MODES}
        and rs.offered in {None, *_STRUCTURED}
        and rs.consented <= _STRUCTURED
        and all(type(i) is str for i in rs.psychoed_shown)
        and type(rs.streak) is int and rs.streak >= 0
        and type(rs.step) is int
        and (0 <= rs.step < steps if rs.exercise is not None else rs.step == 0)
    )  # fmt: skip
    return rs if valid else RouterState()


def accept(rs: RouterState) -> RouterState:
    """Yes on the offer card: switch to the offered mode and remember the consent."""
    if rs.offered is None:
        raise ValueError("no structured mode on offer")
    return replace(rs, current=rs.offered, offered=None, challenger=None, streak=0,
                   consented=rs.consented | {rs.offered})  # fmt: skip


def decline(rs: RouterState) -> RouterState:
    return replace(rs, offered=None, challenger=None, streak=0)


def stop(rs: RouterState) -> RouterState:
    """End the running exercise; the mode stays until the router moves on."""
    return replace(rs, exercise=None, step=0)
