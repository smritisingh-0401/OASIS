# OASIS project memory

A short record of the decisions that still shape the code, the open items, and the results that are not yet verified. Read it with [rules.md](rules.md) before changing anything. Measured results are in [reports.md](reports.md).

## Status

The fourteen-phase build plan is complete, followed by changes from demo testing and four add-only ML models. No phase is in progress. Open items 4, 5, 8 and 10 must be closed before any real use.

Development setup: Windows 11, Python 3.12 managed by uv, `uv run python scripts/verify.py` as the single check on every platform and in CI. Commits are authored as Smriti with no assistant attribution, follow Conventional Commits, and land through pull requests; `main` requires both `verify` CI jobs.

## Decisions

### Architecture and safety

| Date | Decision | Reason |
|---|---|---|
| 2026-10-07 | A rule-based decision plane plans each reply; the LLM only phrases it | Decisions stay testable and explainable; mistakes in wording are cheap |
| 2026-10-07 | Safety runs before any storage access; crisis bookkeeping is written after the reply | A broken database can never block a crisis handoff |
| 2026-10-07 | The safety layer is pure Python with no model, network or database imports; it fails closed; no negation suppression | A missed crisis costs far more than an unneeded handoff |
| 2026-10-07 | Crisis handoff is fixed text with zero model calls; post-crisis mode holds until the user chooses to continue | Works with the model and storage down; provisional until clinician review |
| 2026-10-07 | Crisis message text is never stored; the audit keeps tiers and rule IDs only | Privacy of the most sensitive messages |
| 2026-10-08 | Normalisation yields up to four variants; rules tolerate stretched letters; the allow-list suppresses a hit only when the idiom span covers it | Catches disguised phrasing without hiding a real disclosure after an idiom |
| 2026-10-08 | Invalid safety content stops the app at startup | Bad rules are found at boot, never mid-conversation |
| 2026-10-08 | Crisis resources in two tiers: Tier 1 needs a line verified on the service's or a government site; Tier 2 uses UK travel-advice emergency numbers. Blocked sites were not bypassed | Only verified numbers are shown |
| 2026-10-27 | Self-harm without suicidal intent keeps the full handoff and post-crisis mode | Safe default until clinician review |
| 2026-11-07 | Crisis reply and help card tell the person to call now; a confirmed crisis (not the classifier-only check-in) opens an emergency popup with the country's numbers | Clinician review (Dr. K. Ramakrishnan) |
| 2026-10-29 | Threats to someone else are a crisis (`harm_others` tier) with their own reply naming the emergency number | Demo testers' threats got ordinary replies |
| 2026-11-01 | Add-only crisis classifier (logistic regression shipped as YAML weights, pure Python), asked only when no rule matched; a classifier-only alert gets a check-in reply (CR-28); `OASIS_CRISIS_CLASSIFIER=0` turns it off | Typo recall 51% to 80% with 3/98 benign flagged and no new runtime dependency |

### Decision plane

| Date | Decision | Reason |
|---|---|---|
| 2026-10-07 | PHQ-9 and GAD-7 only, with published items and bands, fixed buttons, no model paraphrase or scoring; item 9 of 1 or more triggers the handoff before storage | Instruments stay valid; item 9 works with the database down |
| 2026-10-08 | Screening offer needs readiness of 0.45 or more for two turns in a row (three until 2026-10-12); domain weights 0.7; messages about someone else excluded | First-run recall was 0.31 |
| 2026-10-08 | An explicit request overrides the 24-hour decline cooldown; re-administration window 10 days | Owner's decisions |
| 2026-11-07 | Item 9 hands off only at "More than half the days" or more; "Several days" finishes with advice; every result, escalated ones included, is scored and shown in Mood trend; no repeat or decline limits | Clinician review (Dr. K. Ramakrishnan) |
| 2026-10-11 | Router: weighted sum per mode, margin 0.15, two turns of lead, structured modes offered with consent, grounding at overwhelm 0.6 without asking | Stable, explainable mode choice |
| 2026-10-12 | Anxiety's mindfulness weight 0.85 and anger's DBT weight 0.85 (both raised from lower values) | With the lower values these emotions could never overcome companion's bias of 0.35 |
| 2026-10-11 | One low-risk exercise per mode; steps shown word for word after one model sentence; the first step after "Yes" has no model call | The 4B model rewrote steps wrongly |
| 2026-10-11 | Psychoeducation: eleven NHS and WHO items, each shown once per session; skipped under acute overwhelm and mid-exercise | Sourced, readable content; help first in a panic |
| 2026-10-25 | Lexicon scores come from the highest-scoring sentence, with a leading identity clause scored apart | Identity words diluted scores in the bias evaluation |
| 2026-10-29 | Valence keeps VADER with four corrections (comparison "like", "hand", negated bad words, good words after "over" or "too") | Negative demo messages scored positive |
| 2026-11-01 | Learned emotion scorers from GoEmotions are add-only: an emotion is the larger of the hand and learned score | Replacing the hand lexicons lost OASIS phrasings and broke 10 router tests |

### Generation and guard

| Date | Decision | Reason |
|---|---|---|
| 2026-10-07 | Model Qwen3.5-4B GGUF Q4_K_M in a separate, version-pinned `llama-server`; thinking disabled and think tags stripped | Free, small, CPU-friendly; a model crash cannot take down the app |
| 2026-10-07 | No streaming in v1; replies about 150 tokens returned whole | The guard must see the full draft; measured again in Phase 13 |
| 2026-10-12 | Companion form rules (`validate_first`, `one_question`, `fresh_opener`) are soft; praise, advice and dependency rules are hard | Hard form rules sent out-of-place fallbacks |
| 2026-10-12 | System text keeps small talk light and never makes a feeling bigger or darker | Small talk received inflated feelings |
| 2026-10-13 | Guard targets: at least 90% of curated sycophantic replies caught, at most 5% of benign blocked | Agreed before building |
| 2026-10-13 | Refusals of the form "I can't tell you if you have depression" pass the diagnosis and medication checks | The guard blocked the model's correct refusals |
| 2026-10-13 | "You're right" and "I agree with you" fail on thinking-trap and medication messages without an echo | A stress run leaked reworded agreement |
| 2026-10-13 | llama-server runs with `-np 1 --cache-ram 0` | The default prompt cache grew to about 12 GB and crashed the server |
| 2026-10-29 | Companion replies sometimes only listen; short statements get one sentence; every fourth reply about a difficulty offers a small idea with hope; "stay positive" is rejected | Demo feedback |
| 2026-11-01 | Optional `ml` extra for two int8 ONNX models: an NLI check in the guard and question-only psychoeducation retrieval. Without them the app runs as before | Paraphrased agreement 2/20 to 6/20 caught; right item 3/33 to 24/33 |

### Explainability, privacy and style

| Date | Decision | Reason |
|---|---|---|
| 2026-10-22 | SHAP values computed in closed form; `shap` is a dev-only test oracle | Every detector is linear; the library would add numpy, scipy and pandas to a 6 GB laptop app |
| 2026-10-29 | Explanations live on a "Why replies" page | A panel under every reply was cluttered |
| 2026-10-07 | SQLite (WAL) behind a repository interface, with an in-memory twin; no PostgreSQL adapter (decided 2026-10-27) | One person per laptop, one file to export and delete |
| 2026-10-07 | Session key is a 256-bit token in `X-OASIS-Session`, stored hashed; one uvicorn worker | No identity in URLs; unsaved sessions live in process memory |
| 2026-10-23 | Saved or unsaved is chosen per session at onboarding; the consent gate runs after the safety gate | A crisis is answered from any session |
| 2026-10-24 | A saved session's key is in `localStorage`, an unsaved one's in `sessionStorage`; the notice says anyone using the browser can open a saved conversation | Saved conversations survive a closed tab |
| 2026-10-24 | Delete reports `503 erasure_pending` when another program blocks the overwrite, and retries | SQLite leaves deleted text on disk silently in that case |
| 2026-10-26 | Saved conversations unused for 90 days are deleted through the same erasure path | Data is not kept indefinitely |
| 2026-10-24 | Style is attached after planning; only the prompt builder reads it; the default adds no text; OASIS only suggests a gentler style | Style can never change a decision |
| 2026-10-25 | Bias CI requires 100% crisis handoffs in every version and identical decisions for demographic variants; dialect agreement is reported | Widening lexicons for seven dialects needs native-speaker review |

### Reliability and deployment

| Date | Decision | Reason |
|---|---|---|
| 2026-10-26 | The generation timeout starts once the model is free, bounded by the request deadline | Queued messages spent their budget waiting |
| 2026-10-27 | `llm_queue_limit` 2 (was 4) | At 4 to 8 sessions it served 26/54 against 20/54 and timed out 1 against 22 |
| 2026-10-27 | Install runs llama-server with `-hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj -ngl 0` | The Vulkan build failed on integrated graphics; the vision file is never used |
| 2026-10-27 | Repository licence MIT | Permissive reuse |
| 2026-10-28 | Demo mode (`OASIS_DEMO=1`): memory only, its own notice and banner, shared through a Cloudflare tunnel; request bodies counted as they arrive; at most 1,000 unsaved sessions | Real replies for testers at no cost, with bounded memory |

## Open items

| # | Item | Status |
|---|---|---|
| 4 | Qualified clinician to review [clinical_review.md](clinical_review.md) | In progress: 8 of 29 items reviewed by Dr. K. Ramakrishnan on 2026-11-07; the rest are needed before any real use |
| 5 | Ethics approval for any testing with participants | Needed before a user study |
| 8 | Browser check of crisis lines that could not be fetched (Philippines, Chile, Colombia, Pakistan, Sweden's hours) to promote them to Tier 1 | Partly done |
| 10 | A held-out crisis set written outside the project: first 2 to 3 people writing blind, then a published research dataset under a data-use agreement | Planned |
| O8 | Legal review of the data notice | Needed before real deployment |

## Not yet verified

- Crisis recall on unseen phrasing: 88.7% and 90.9% on held-out batches before tuning; an external set is still needed.
- Detector, trigger and psychoeducation accuracy on natural messages: only synthetic sets exist.
- Install on a second computer, macOS or Linux.
- Real-model reply quality beyond small runs; standard English alone varied 18 points between runs.
- Dialect text was written by the developer, not native speakers (CR-26).
- Crisis numbers were verified in October 2026 and need re-checking before any use.
- Timing tests on battery power: the explanation latency test measured 33 to 39 ms unplugged against its 20 ms limit.

## Glossary

| Term | Meaning |
|---|---|
| Decision plane | The deterministic modules (signals, planner, assessment, router, psychoeducation, companion, style) that decide what a reply does |
| Signals | Per-turn record of detector scores and cues, with no text (`oasis.types.Signals`) |
| Plan | The planner's output: one mode, constraints, an optional technique or snippet, and the style |
| Mode | crisis, post_crisis, assessment, psychoed, companion, cbt, dbt, mindfulness or grounding |
| Crisis handoff | Fixed reply with crisis resources; zero model calls |
| Post-crisis mode | Fixed supportive replies after a handoff until the user chooses to continue |
| Templated reply | Vetted fixed text used for questionnaire steps and every failure path |
| Guard | Checks on every generated draft, with one retry and a vetted fallback |
| Hypercompliance | Agreeing with or reinforcing a cognitive distortion instead of questioning it gently |
| Hysteresis | The rule that a challenger mode must lead for several turns before an offer or switch |
| Turn trace | Per-turn timings, decisions and reason codes, never user text |
| Unsaved mode | Memory-only session; nothing written to disk |
| Content library | Versioned YAML (rules, lexicons, items, scripts, question bank) with source and review status |
