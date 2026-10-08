# Phase 3 — Assessment (PHQ-9 / GAD-7)

**Report topic:** standardised screening inside a conversational agent — consent-first offer design, a state machine that can never score an incomplete questionnaire, item-9 escalation that storage cannot block, and evaluation of the offer trigger.

## 1. Design

| Component | File | Role |
|---|---|---|
| Instrument content | `content/assessment/phq9.yaml`, `gad7.yaml` | Stem, options, items and bands verbatim from the official forms; source URL and verification date |
| Result and step text | `content/assessment/result_text.yaml` | Plain-language text per band, the non-diagnostic disclaimer, offer and step wording (CR-08) |
| Scoring | `assessment/instruments.py` | Validates content at startup; `score()` accepts only a complete set of 0-3 answers |
| State machine | `assessment/flow.py` | Pure functions: offer, consent/decline, items, functional question, score, pause, resume, abort, expiry, item-9 escalation |
| Offer trigger | `assessment/trigger.py`, `content/assessment/trigger.yaml` | Readiness score over a sliding window, explicit requests, guards (CR-09, CR-10) |
| Planner | `core/planner.py` | Precedence: post-crisis → open assessment → assessment offer → companion |
| Storage | `storage/migrations/0003_assessments.sql`, both backends | `save_assessment`, `list_assessments`; CHECK constraints on answers, items, status and totals |
| API and UI | `api/schemas.py`, `api/routes.py`, `web/app.js` | Optional structured `action` on `/chat`; assessment card with 0-3 buttons, Pause, Stop, Resume |

Key mechanisms:

- **Published content only (rules CL1).** Item text, options and the PHQ-9 functional question were checked word for word against the official phqscreeners.com forms (extracted from the PDFs on 2026-10-08); bands against the official instruction manual. The published GAD-7 form has no functional-difficulty question, so GAD-7 asks none — this overrides the design's shared state diagram.
- **Never score an incomplete questionnaire.** `score()` raises unless every item has a 0-3 answer; the database rejects answers outside 0-3, item indexes outside 1-9, a `scored` row without total and band, and GAD-7 totals above 21.
- **Answers are buttons, never free text.** Each button sends its label as the message (so history reads naturally and the safety gate still sees text) plus a structured action naming the instrument and item. A click for any item other than the current one changes nothing, which makes double clicks and stale cards harmless.
- **Item 9 before storage (rules S11).** The engine checks the action for PHQ-9 item 9 with a value of 1 or more before any storage call, so the handoff works with the database down. The questionnaire is then marked `escalated` (never scored or shown) and the audit entry records `source: "item9"`, both after the response.
- **Consent first.** Nothing starts without "Yes, let's start". Typing while an offer is open counts as "not now"; typing mid-questionnaire pauses it and the message is answered normally. Pause, Resume and Stop are always on the card; Stop discards the answers.
- **Offer trigger.** Per-turn evidence is the capped sum of the weights of the symptom domains a message mentions (one domain per PHQ-9 item 1-8 and GAD-7 item 1-7, plus duration). Readiness is the decayed mean over six user turns; an offer needs three turns in a row at or above 0.45, or an explicit request. Messages about someone else do not count. Guards: an open assessment, a decline within 24 hours, the same instrument completed within 14 days, or a crisis earlier in the loaded conversation. The stored reason is a code plus the numbers (for example `{"reason": "sustained_readiness", "R": 0.62, "turns": 3, "top_domains": ["worry", "nervous", "trouble_relaxing"]}`), never message text.

## 2. Evaluation method

- **Labelled conversations written before the trigger** (commit `a3f2772`): 24 conversations — 14 where an offer is appropriate (6 depressive, 5 anxious, 3 explicit requests) with the earliest appropriate turn, and 10 where it is not (one bad day, venting, a friend's depression, flu, hyperbole, nerves before a test).
- **Tests before implementation** (commit `84f4f1c`): band edges for both instruments; Hypothesis properties (total equals the sum and stays in range, every total maps to exactly one band, bands are monotone, incomplete or invalid answers are never scored); consent, decline with reason, pause, resume, abort, expiry, stale clicks, item 9 at 0-3; trigger guards; storage contract on both backends; database CHECK constraints; the full questionnaire and item 9 over HTTP; item 9 with storage down.
- **Mutation spot-check:** 13 deliberate faults in scoring, the state machine, the trigger, the engine and the migration.
- **Live check** in the browser against the running server.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass |
| Tests | 591 passed, 0 skipped |
| Coverage | 97.5% overall; `oasis.assessment` 99.0%, `oasis.safety` 97.1% (target ≥ 95%) |
| Trigger, before tuning | Precision 0.80, recall 0.31 (4 of 13 conversations found at the time; the one false positive was "I read about the PHQ-9" counted as a request) |
| Trigger, after tuning | Precision 1.00, recall 0.93 (13 of 14), mean offer latency 0.85 turns after the earliest appropriate turn; 0 of 10 false offers |
| Mutation spot-check | 11/13 caught on the first run. Survivors: the pre-storage item-9 threshold (tests only used value 3 with storage down) and the third-person exclusion (no test had sustained third-person symptoms). Both now have tests; 13/13 caught |
| Live check | Explicit request → offer → items with verbatim text → Pause → Resume continues at the next item → functional question → result with the disclaimer (1/27, minimal); item 9 = "Several days" → crisis handoff, help card opens and takes focus, card hidden; four anxious messages → GAD-7 offer; typing after the offer counts as "not now"; no server errors |

**Tuning (on the labelled set, so the after-tuning numbers are not an unbiased estimate):** the domain weights were raised from 0.5 to 0.7 (duration and uncontrolled worry from 0.3 to 0.4) while keeping the design's threshold of 0.45; an explicit request now needs a verb ("take", "do", "try") or a phrase like "depression test"; the first-person-only rule, which missed messages with no subject ("nothing feels enjoyable anymore"), became an exclusion of messages about someone else.

**Remaining miss:** `anx_cant_control` (4 short turns): with a six-turn window and three consecutive turns required, the design formula cannot reach the threshold before the conversation ends.

## 4. Known limits

- **Trigger quality on real conversations is unmeasured.** 24 synthetic conversations, used for tuning; a fresh labelled set is needed. The valence term waits for the Phase 4 signals object.
- **Earliest sustained offer is the fifth symptomatic turn** under the design's window and threshold; shorter conversations rely on an explicit request.
- **Decline cooldown also blocks explicit requests** for 24 hours, as the design states. Whether a user who changes their mind should be able to ask again sooner is a question for CR-10.
- **Paused expiry is measured from the start** of the questionnaire, not from the pause.
- **The card is not restored after a page reload;** typing pauses the questionnaire and the paused card appears on that turn.
- **English only.** Translations of both instruments exist on phqscreeners.com but are not used.
- **Clinician review pending** for CR-07 to CR-10 (item-9 handling, result and step text, trigger, cooldowns).
