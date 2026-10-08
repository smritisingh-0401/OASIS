# OASIS — Clinician Review Register

Everything in this register is an **engineering choice that needs review by a qualified clinician** before OASIS is used by anyone outside development. The only clinical content treated as fixed is the standard published PHQ-9 and GAD-7 items, answer options and scoring bands.

Status values: `pending` · `in_review` · `approved` · `changes_requested`.
Reviewer: _not yet assigned (open item O3)._

| ID | Item | Where it lives | Phase | Status | Notes |
|---|---|---|---|---|---|
| CR-01 | Crisis phrase lists (explicit intent, passive ideation, plan/method, burden, self-harm) | `content/safety/patterns.yaml` | 2 | pending | Recall/FPR reported in `docs/reports/phase-02.md`. The `self_harm` tier (non-suicidal self-injury gets the full handoff) was added in Phase 2 and needs confirmation |
| CR-02 | Idiom allow-list | `content/safety/allowlist.yaml` | 2 | pending | Each entry has its own test |
| CR-03 | Crisis handoff wording | `safety/handoff.py` (compiled-in constant) | 2 | pending | Points to the "Need help now?" card |
| CR-04 | Crisis resource list: Tier 1 (40 countries, verified crisis line + emergency number) and Tier 2 (184 countries and territories, emergency number from FCDO travel advice) | `content/safety/resources.yaml` | 2 | pending | Verification date and source stored per entry; countries whose official sites could not be fetched are Tier 2 (list in `docs/reports/phase-02.md`) |
| CR-05 | Post-crisis policy (minimal supportive mode until the user opts to continue; the continue phrases; behaviour after restart with storage down) | `core/planner.py`, `core/templates.py` | 2 | pending | Provisional |
| CR-06 | Crisis message text not stored in history (placeholder "A message here was answered with crisis support. Its text was not saved.", shown as a muted note); audit keeps tiers and pattern IDs only | `core/engine.py` (`record_crisis`), `audit_log` | 2 | pending | Also a privacy decision |
| CR-07 | PHQ-9 item-9 handling (any answer ≥ 1 → crisis protocol; questionnaire marked escalated and never scored) | `assessment/flow.py`, `core/engine.py` | 3 | pending | Checked before storage so a database failure cannot block it |
| CR-08 | Plain-language score explanations, the "see a professional" threshold (10, the published threshold for further evaluation), the offer and step wording | `content/assessment/result_text.yaml` | 3 | pending | |
| CR-09 | Screening trigger: domain lexicons, weights (raised from 0.5 to 0.7 after the first measurement), window, threshold, consecutive-turn rule, third-person exclusion | `content/assessment/trigger.yaml` | 3 | pending | Precision/recall reported in `docs/reports/phase-03.md` |
| CR-10 | Assessment cooldowns (14-day re-administration, 24-hour decline cooldown for unprompted offers only (an explicit request overrides it), 24-hour paused expiry, typing after an offer counts as "not now") | `content/assessment/trigger.yaml`, `assessment/flow.py` | 3 | pending | |
| CR-11 | Router weights, margin, hysteresis N, acute-overwhelm threshold | `content/router/weights.yaml` | 4 | pending | |
| CR-12 | Technique scripts (v1: low-risk skills only — no cold exposure, breath-holding or intense exercise) | `content/techniques/*.yaml` | 4 | pending | |
| CR-13 | Psychoeducation text | `content/psychoed/items.yaml` | 5 | pending | Each item has source and reading level |
| CR-14 | Companion constraints (praise, advice, dependency lists) | `content/companion/*.yaml` | 6 | pending | |
| CR-15 | Socratic question bank | `content/guard/socratic_bank.yaml` | 7 | pending | |
| CR-16 | Distortion categories and guard markers | `content/guard/*.yaml` | 7 | pending | Burns's categories |
| CR-17 | Trend-change flag (baseline sessions K, z threshold) and feature selection | `content/tracking/config.yaml` | 8 | pending | Labelled non-clinical in UI |
| CR-18 | Templated fallback replies | `core/templates.py` | 1+ | pending | |

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-07 | Register created with seed items | Smriti |
| 2026-10-08 | Phase 2: CR-01 adds the self-harm tier; CR-03..06 and CR-18 locations updated to the implementation | Smriti |
| 2026-10-08 | Phase 3: CR-07..10 updated to the implementation | Smriti |
