# OASIS — Clinician Review Register

Everything in this register is an **engineering choice that needs review by a qualified clinician** before OASIS is used by anyone outside development. The only clinical content treated as fixed is the standard published PHQ-9 and GAD-7 items, answer options and scoring bands.

Status values: `pending` · `in_review` · `approved` · `changes_requested`.
Reviewer: _not yet assigned (open item O3)._

| ID | Item | Where it lives | Phase | Status | Notes |
|---|---|---|---|---|---|
| CR-01 | Crisis phrase lists (explicit intent, passive ideation, plan/method, burden) | `content/safety/patterns.yaml` | 2 | pending | Recall/FPR reported in `docs/reports/phase-02.md` |
| CR-02 | Idiom allow-list | `content/safety/allowlist.yaml` | 2 | pending | Each entry has its own test |
| CR-03 | Crisis handoff wording | `content/safety/handoff.yaml` | 2 | pending | |
| CR-04 | Crisis resource list: Tier 1 (64 countries, crisis line + emergency number) and Tier 2 (emergency number for every other country) | `content/safety/resources.yaml` | 2 | pending | Numbers verified at build time; verification date and source stored per entry; countries without a verifiable line list the emergency number only |
| CR-05 | Post-crisis policy (minimal supportive mode until the user opts to continue; behaviour after restart with storage down) | `core/planner.py`, `content/templates/post_crisis.yaml` | 2 | pending | Provisional |
| CR-06 | Crisis message text not stored in history; audit keeps pattern IDs only | Turn recorder, audit log | 2 | pending | Also a privacy decision |
| CR-07 | PHQ-9 item-9 handling (any answer ≥ 1 → crisis protocol; questionnaire not scored that turn) | `assessment/state_machine.py` | 3 | pending | |
| CR-08 | Plain-language score explanations and any "see a professional" thresholds | `content/assessment/result_text.yaml` | 3 | pending | |
| CR-09 | Screening trigger: domain lexicons, weights, window, threshold, consecutive-turn rule | `content/assessment/trigger.yaml` | 3 | pending | Precision/recall reported |
| CR-10 | Assessment cooldowns (14-day re-administration, decline cooldown) | `content/assessment/trigger.yaml` | 3 | pending | |
| CR-11 | Router weights, margin, hysteresis N, acute-overwhelm threshold | `content/router/weights.yaml` | 4 | pending | |
| CR-12 | Technique scripts (v1: low-risk skills only — no cold exposure, breath-holding or intense exercise) | `content/techniques/*.yaml` | 4 | pending | |
| CR-13 | Psychoeducation text | `content/psychoed/items.yaml` | 5 | pending | Each item has source and reading level |
| CR-14 | Companion constraints (praise, advice, dependency lists) | `content/companion/*.yaml` | 6 | pending | |
| CR-15 | Socratic question bank | `content/guard/socratic_bank.yaml` | 7 | pending | |
| CR-16 | Distortion categories and guard markers | `content/guard/*.yaml` | 7 | pending | Burns's categories |
| CR-17 | Trend-change flag (baseline sessions K, z threshold) and feature selection | `content/tracking/config.yaml` | 8 | pending | Labelled non-clinical in UI |
| CR-18 | Templated fallback replies | `content/templates/*.yaml` | 1+ | pending | |

## Change log

| Date | Change | By |
|---|---|---|
| 2026-10-07 | Register created with seed items | Smriti |
