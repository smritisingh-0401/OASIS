# Phase 4 — Therapy router (+ signal extraction, guard hook)

**Goal.** Deterministic, explainable mode selection: each turn's approach (companion, CBT, DBT, mindfulness, or grounding under acute overwhelm) is chosen by a transparent weighted rule, never by the LLM.

## 1. Design

| Component | File | Role |
|---|---|---|
| Signals | `core/signals.py`, `types.Signals` | One message → one frozen record of numbers and category names (no text) |
| Lexicon scorer | `core/detectors/lexicon.py`, `content/lexicons/*.yaml` | `clip(b + scale · Σ wᵢ·countᵢ / tokens, 0, 1)` over the safety normaliser's base form; emotions, dysregulation, overwhelm, wanting to talk, opt-out, eleven Burns distortion categories (CR-20) |
| Valence baseline | `core/detectors/valence.py` | VADER compound score in [-1, 1] (new dependency `vaderSentiment`, decision log 2026-10-11) |
| Router scoring | `router/weights.py`, `content/router/weights.yaml` | `score_m = b_m + Σ_s w_{m,s}·x_s`, with every contribution returned exactly and sorted by size (CR-11) |
| Router decision | `router/router.py` | Acute override, mid-exercise hold, opt-out, margin, hysteresis, consent offer, switch; state as JSON |
| Exercises | `router/exercise.py`, `content/techniques/*.yaml` | One low-risk script per mode, one step per user message (CR-12) |
| Planner | `core/planner.py` | Post-crisis → open questionnaire → questionnaire offer (skipped mid-exercise) → router; constraints per mode (design §13.2) |
| Prompt | `llm/prompt.py` | Goal text per mode; an exercise step goes in as a `- script:` line |
| Guard hook | `guard/hook.py` | The pass-through guard, moved out of the engine so Phase 7 plugs in unchanged |
| Engine | `core/engine.py` | Loads and saves router memory (best effort); an exercise step is its own fallback when the LLM fails; the trace carries the decision and reason codes |
| Storage | both backends | `SessionInfo.router_state`, `set_router_state` (existing `sessions.router_state` column; no migration) |
| API and UI | `api/schemas.py`, `api/routes.py`, `web/app.js` | `exercise_consent` and `exercise_stop` actions; exercise card (offer: Yes / Not now; running: "Step k of n" with Stop); `/history` restores it |

**Decision rule** (design §7.3). A running exercise holds unless the user opts out; grounding also holds under fresh overwhelm instead of restarting. Overwhelm at or above 0.6 goes straight to grounding, keeping consents and dropping any open offer. Otherwise the top-scoring mode must beat the runner-up by 0.15 for 3 turns in a row; a structured mode the user has not yet agreed to is then offered, not entered. Companion never asks.

**Exercises.** Thought check (CBT, 3 steps), STOP skill (DBT, 4), Notice the breath (mindfulness, 3), 5-4-3-2-1 senses (grounding, 5). All marked `needs_clinician_review`; a test rejects breath-holding, cold, running and similar wording (rules CL7).

**Departures from the phase plan's file list.** Hysteresis lives inside `router/router.py` (one rule, no module of its own); exercise scripts load from `router/exercise.py` rather than a separate package.

## 2. Evaluation method

- **Scenario table** (`tests/unit/test_router.py`): 30 signal vectors with the expected leading mode, plus 4 acute rows that must route to grounding. It pins the start weights: a weight change that moves a row must update the table on purpose (CR-11).
- **Stability:** strong CBT and DBT cues alternating for 12 turns; strong cues interleaved with ordinary talk; a lead narrower than the margin.
- **Overrides:** acute overwhelm mid-hysteresis, mid-exercise of another mode, and during grounding; mid-exercise hold against strong other cues; typed and button opt-out.
- **Property test** (Hypothesis): for random feature vectors, `bias + Σ contributions == score` for every mode, contributions sorted by size, every weighted signal present, modes ranked by score.
- **Detectors** (`tests/unit/test_signals.py`): golden messages for every cue and every Burns category, an ordinary-talk set that must raise nothing, opt-out phrases versus look-alikes, dilution in longer messages, scores in range for random text, and invalid-content rejection.
- **End to end:** planner flows (offer, accept, steps, stop, lapse, acute, precedence), engine (memory across turns, LLM failure, storage failure, trace without text), HTTP (consent, steps, reload restore, malformed actions), storage contract on both backends.
- **Mutation spot-check:** 15 deliberate faults across router, exercises, planner, signals and engine, each run against the suite.
- **Live check** in the browser against the fake LLM.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass |
| Tests | 799 passed, 0 skipped |
| Coverage | 98.1% overall; `oasis.router` 100%, `oasis.assessment` 98.6%, `oasis.safety` 97.1% (target ≥ 95%) |
| Scenario table | 34/34 rows (30 scored + 4 acute) |
| Stability | 0 mode changes and 0 offers over 12 alternating strong cues (streak never above 1); 0 over strong cues broken by ordinary talk |
| Contribution additivity | Holds on every Hypothesis example; contributions always sorted |
| Detector golden set | Every emotion, cue and Burns category fires on its example; 4/4 ordinary messages raise no cue |
| Latency (signals + routing, dev machine) | p50 0.24 ms, p95 0.51 ms, p99 0.52 ms over 300 realistic messages; a 2 000-character message 14 ms |
| Mutation spot-check | 15/15 caught on the first run |
| Live check | Three "I'm such a failure, I always mess everything up" messages → "Try: Thought check" offer; Yes → step 1 with "Step 1 of 3" and Stop; each reply moves one step; reload restores "Step 2 of 3"; acute message → 5-4-3-2-1 step 1 at once, no offer; Stop → "Okay, let's stop the exercise there…", card closes; no console errors |

## 4. Known limits

- **Detector accuracy on real conversations is not measured.** The scenario table checks the policy given signals; the golden set checks hand-picked phrasings. A labelled set of natural messages is needed before claiming routing accuracy (not verified here).
- **Lexical cues are brittle.** Paraphrases outside the word lists are missed, and dividing by token count dilutes a cue in a long message. The normaliser handles case, apostrophes and stretched letters only.
- **Opt-out can misfire safely:** "I want to stop smoking" typed mid-exercise ends the exercise. Failing towards stopping is deliberate.
- **"Not now" is not a cooldown.** After declining, the same offer can return after 3 more turns of strong cues (CR-11).
- **No screening offer mid-exercise**, even when asked explicitly; the user can stop the exercise first (design §3.2 guard).
- **Real-model phrasing of exercise steps is not verified here.** The fake LLM returns the step verbatim; `scripts/` runs against the real model are still pending.
- **A failed router save** loses that turn's change; the next turn starts from the last saved memory (logged as `storage.down`).
- English only; lexicons and weights are engineering start values awaiting clinician review (CR-11, CR-12, CR-20).
