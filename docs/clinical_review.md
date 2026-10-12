# OASIS — Clinician Review Register

Everything in this register is an **engineering choice that needs review by a qualified clinician** before OASIS is used by anyone outside development. The only clinical content treated as fixed is the standard published PHQ-9 and GAD-7 items, answer options and scoring bands.

Status values: `pending` · `in_review` · `approved` · `changes_requested`.
Reviewer: _not yet assigned (open item O3)._

| ID | Item | Where it lives | Phase | Status | Notes |
|---|---|---|---|---|---|
| CR-01 | Crisis phrase lists (explicit intent, passive ideation, plan/method, burden, self-harm) | `content/safety/patterns.yaml` | 2 | pending | Recall/FPR reported in `docs/reports/phase-02.md`. The `self_harm` tier (non-suicidal self-injury gets the full handoff) was added in Phase 2 and needs confirmation |
| CR-02 | Idiom allow-list | `content/safety/allowlist.yaml` | 2 | pending | Each entry has its own test |
| CR-03 | Crisis handoff wording, and the help card's opening lines | `safety/handoff.py` (compiled-in constant), `web/index.html` | 2 | pending | Points to the "Need help now?" card. 2026-10-12, owner's decision: the reply and the card open with "If you feel like talking to someone in person…" and no longer tell the user to call the emergency number. Flagged for the clinician: safe-messaging guidance favours a route to immediate help. Country emergency numbers are still listed in the card, which still ends with the local-emergency-number line |
| CR-04 | Crisis resource list: Tier 1 (40 countries, verified crisis line + emergency number) and Tier 2 (184 countries and territories, emergency number from FCDO travel advice) | `content/safety/resources.yaml` | 2 | pending | Verification date and source stored per entry; countries whose official sites could not be fetched are Tier 2 (list in `docs/reports/phase-02.md`) |
| CR-05 | Post-crisis policy (minimal supportive mode until the user opts to continue; the continue phrases; behaviour after restart with storage down) | `core/planner.py`, `core/templates.py` | 2 | pending | Provisional |
| CR-06 | Crisis message text not stored in history (placeholder "A message here was answered with crisis support. Its text was not saved.", shown as a muted note); audit keeps tiers and pattern IDs only | `core/engine.py` (`record_crisis`), `audit_log` | 2 | pending | Also a privacy decision |
| CR-07 | PHQ-9 item-9 handling (any answer ≥ 1 → crisis protocol; questionnaire marked escalated and never scored) | `assessment/flow.py`, `core/engine.py` | 3 | pending | Checked before storage so a database failure cannot block it |
| CR-08 | Plain-language score explanations, the "see a professional" threshold (10, the published threshold for further evaluation), the offer and step wording | `content/assessment/result_text.yaml` | 3 | pending | |
| CR-09 | Screening trigger: domain lexicons, weights (raised from 0.5 to 0.7 after the first measurement), window, threshold, consecutive-turn rule, third-person exclusion | `content/assessment/trigger.yaml` | 3 | pending | Precision/recall reported in `docs/reports/phase-03.md`. 2026-10-12, owner's decision: k lowered from 3 to 2 turns in a row; on the 24 labelled conversations precision 1.00 → 0.93, recall 0.93 → 1.00 (one offer a turn before the labelled earliest point; no offer in any of the 10 negative conversations) |
| CR-10 | Assessment cooldowns (10-day re-administration, 24-hour decline cooldown for unprompted offers only (an explicit request overrides it), 24-hour paused expiry, typing after an offer counts as "not now") | `content/assessment/trigger.yaml`, `assessment/flow.py` | 3 | pending | 2026-10-12, owner's decision: re-administration lowered from 14 to 10 days, for offers and requests alike; the same window now decides how long a moderate-or-worse result informs the router. Flagged for the clinician: both instruments ask about the last two weeks, so a retake after 10 days overlaps 4 days of the previous recall period |
| CR-11 | Router weights, margin, hysteresis N, acute-overwhelm threshold; consent policy (ask once per session before cbt/dbt/mindfulness; "Not now" or typing over the offer resets the lead, so it can be offered again after N more turns; grounding starts without asking) | `content/router/weights.yaml`, `router/router.py` | 4 | pending | Start values: margin 0.15, N = 3, acute 0.6; pinned by the scenario table in `tests/unit/test_router.py` |
| CR-12 | Technique scripts (v1: low-risk skills only — no cold exposure, breath-holding or intense exercise): Thought check (CBT), STOP skill (DBT), Notice the breath (mindfulness), 5-4-3-2-1 senses (grounding); offer wording; the stop and decline replies | `content/techniques/*.yaml`, `core/templates.py` | 4 | pending | A test rejects breath-holding, cold, running and similar wording |
| CR-13 | Psychoeducation: the 11 item texts and their topic cues, the item order (specific topics before the general item), the `psychoed` cue phrases ("what's wrong with me", "is it normal", diagnosis questions, stigma statements), once-per-session rule, grade-8 reading ceiling | `content/psychoed/items.yaml`, `content/lexicons/cues.yaml` | 5 | pending | Every source page (NHS, WHO) checked 2026-10-11; Flesch-Kincaid grade 4.2-8.0, checked at startup |
| CR-14 | Companion reply checks: validating phrases, praise, advice and dependency phrase lists; one question ending the reply; soft (form) versus hard (content) rules; varied openers (last 3); warmth about good news allowed (Smriti); the advice-request cue that lifts `no_advice`; companion-only scope (dependency in every mode); the plain-language rule wording in the prompt | `content/companion/checks.yaml`, `content/lexicons/cues.yaml` (`asks_advice`), `llm/prompt.py` | 6 | pending | Curated good/bad replies in `tests/data/companion/`; real-model transcripts from `scripts/tone_check.py` pending |
| CR-15 | Socratic question bank | `content/guard/socratic_bank.yaml` | 7 | pending | |
| CR-16 | Distortion categories and guard markers | `content/guard/*.yaml` | 7 | pending | Burns's categories |
| CR-17 | Trend-change flag (baseline sessions K, z threshold) and feature selection | `content/tracking/config.yaml` | 8 | pending | Labelled non-clinical in UI |
| CR-18 | Templated fallback replies, including the companion fallback ("I hear you. What feels most important to talk about right now?") used when a companion draft breaks a content rule twice | `core/templates.py` | 1+ | pending | |
| CR-19 | After a crisis earlier in the conversation, once post-crisis mode is cleared, PHQ-9/GAD-7 can be asked for and can also be offered unprompted | `assessment/trigger.py`, `core/planner.py` | 3 | pending | Explicit requests decided 2026-10-09; unprompted offers allowed by the owner on 2026-10-12 (they were blocked before). PHQ-9 item 9 still escalates (CR-07) |
| CR-20 | Signal lexicons: emotions, dysregulation, overwhelm, wanting to talk, opt-out phrases, and the eleven Burns distortion categories | `content/lexicons/*.yaml` | 4 | pending | Engineering start values; golden examples in `tests/unit/test_signals.py` |

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-07 | Register created with seed items | Smriti |
| 2026-10-08 | Phase 2: CR-01 adds the self-harm tier; CR-03..06 and CR-18 locations updated to the implementation | Smriti |
| 2026-10-08 | Phase 3: CR-07..10 updated to the implementation | Smriti |
| 2026-10-09 | CR-19 added: explicit screening requests allowed after a crisis | Smriti |
| 2026-10-11 | Phase 4: CR-11 and CR-12 updated to the implementation; CR-20 added (signal lexicons) | Smriti |
| 2026-10-11 | Phase 5: CR-13 updated to the implementation | Smriti |
| 2026-10-11 | Phase 6: CR-14 updated to the implementation | Smriti |
