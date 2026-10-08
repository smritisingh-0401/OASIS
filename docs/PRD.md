# OASIS — Product Requirements Document

| Field | Value |
|---|---|
| Product | OASIS — lightweight, explainable, safety-first mental health chatbot |
| Document owner | Smriti |
| Status | Draft for approval (Step A) |
| Last updated | 2026-10-07 |
| Related docs | [architecture.md](architecture.md), [design.md](design.md), [rules.md](rules.md), [phases.md](phases.md), [memory.md](memory.md), [clinical_review.md](clinical_review.md) |

---

## 1. Problem statement

Mental health chatbots (MHCs) such as Woebot, Leora, Emohaa, Fido and ChatPal have shown that conversational agents can deliver structured psychological support at scale. A literature review of **97 papers covering 16,620 participants** identified ten recurring limitations in these systems (section 4). They cluster into four themes:

1. **Trust** — the reasoning behind a reply is opaque (black box), and replies are either canned (repetitive scripting) or over-agreeable (sycophancy / hypercompliance).
2. **Fairness** — training data is dominated by WEIRD (Western, Educated, Industrialised, Rich, Democratic) populations, and outputs may be biased against groups.
3. **Access and cost** — paid APIs and heavy infrastructure exclude users and deploying organisations.
4. **Experience and control** — unclear data practices, little user control over data, low engagement, and technical glitches at the moments users most need the system to work.

General-purpose LLM chatbots solve fluency but make most of these worse: they are black boxes, generic and sycophantic, culturally narrow, costly to deploy at scale, and prone to failure modes that are unacceptable during an acute moment.

## 2. Positioning

> **OASIS is the lightweight, explainable, low-cost, safety-first alternative.**

**Core design principle:** *a rule-based decision plane plans each reply; the LLM only phrases it.* Safety decides before the LLM ever runs, and any failure falls back to a templated reply.

| Property | General-purpose LLM chatbot | OASIS |
|---|---|---|
| Who decides what the reply does | The LLM, implicitly | A deterministic, inspectable planner |
| Crisis detection | Inside the model, unauditable | Pure-Python rules that run first, with zero LLM calls on crisis |
| Explanation | None | Per-reply signal contributions (SHAP / exact linear decomposition) |
| Sycophancy | Common | Explicit hypercompliance guard |
| Cost | Paid API or GPU | Quantised open model on a CPU laptop |
| Failure behaviour | Hang or error | Templated reply within a hard timeout |

## 3. Users, context and clinical boundary

### 3.1 Target users
- **Primary:** adults (18+) experiencing everyday, subclinical distress — stress, low mood, worry, loneliness — who want a private, low-friction space to talk and learn coping skills.
- **Secondary:** researchers and clinicians who need to inspect *why* the system chose a response strategy (debug view, exportable summary that the user chooses to share).

### 3.2 Use context
- Single user on their own device, through a web browser, talking to a locally hosted backend.
- English text only (v1).
- Sessions are short and irregular; the system must answer quickly and remember context between sessions (unless the user chose ephemeral mode).

### 3.3 Clinical boundary (shown in the product, not only in docs)
- OASIS is a **subclinical support and screening tool, not a diagnostic system**. It complements and never replaces a clinician.
- This statement appears in onboarding, in the persistent footer of the chat page, alongside every assessment result, and in the README.
- PHQ-9 and GAD-7 use their **standard published items and scoring bands only**. No other instrument, threshold or clinical rule is invented.
- Any clinical logic beyond standard PHQ-9/GAD-7 scoring (crisis phrases, post-crisis policy, router weights, technique scripts, trigger thresholds, etc.) is flagged **"needs review by a qualified clinician"** and tracked in [clinical_review.md](clinical_review.md).
- No reply may contain a diagnosis or medication advice.

## 4. The ten limitations → feature requirements

Each row is a feature with an acceptance criterion that an automated test (or, where marked **[manual]**, a scripted manual check) can verify.

| # | Limitation | Feature requirement | Acceptance criterion | Phase |
|---|---|---|---|---|
| L1 | Black box | Every reply carries an explanation of *why the response strategy was chosen*: ranked signal contributions from detectors (SHAP `LinearExplainer`, LIME only for black-box parts) and from the router (exact weighted-sum decomposition). Exposed via `GET /explanations/{id}`, a "why this reply" panel and a debug view. | (a) 100% of non-crisis replies return an `explanation_id` that resolves; (b) SHAP additivity holds: `base_value + Σ contributions == model_output` within 1e-6; (c) identical input ⇒ byte-identical explanation; (d) explanation overhead within the latency budget (§7.1). | 9 |
| L2 | Repetitive scripting & sycophancy | Context-conditioned generation (plan + history window + one vetted snippet) and a hypercompliance guard that detects validation of a cognitive distortion and reroutes to "validate the feeling, then one Socratic question". | On the curated distortion + sycophantic-reply set: detection rate reported and ≥ the target agreed in Phase 7; false-block rate on a benign set reported; every reroute output contains exactly one question; guard active on therapy and companion paths (tested). | 7 |
| L3 | WEIRD data dominance | User-set communication-style profile (directness, formality) that adjusts framing only; non-Western data used where licensable, and its absence documented honestly. | (a) Same input under different style profiles yields different framing (prompt diff test); (b) crisis verdict, plan mode and triggers are identical across all styles (invariance tests, 100%); (c) the system never infers ethnicity or nationality (code review + test that no such field exists). | 11 |
| L4 | Access disparity | Quantised open-source LLM (Qwen3.5-4B GGUF Q4_K_M by default) served locally by `llama-server`; no paid API. | No outbound network call except to the configured local LLM endpoint (test with network sockets blocked); dependency licences listed. | 1, 14 |
| L5 | Ambiguous privacy | Plain-language data-use disclosure at first use; an explicit, documented policy for self-harm disclosures (what is stored, for how long, who can see it). | API rejects chat with `403 consent_required` until consent is recorded; disclosure text and self-harm policy present in UI and docs (snapshot test). | 10 |
| L6 | Lack of autonomy | Export all of my data; delete account and data; ephemeral (session-only) mode. | (a) Export → import into a fresh store reproduces the same records; (b) after delete, an automated crawl of every table finds zero rows for the user and a marker string is absent from the DB and WAL files; (c) ephemeral session creates no files on disk (filesystem diff test). | 10 |
| L7 | High implementation cost | Runs on one mid-range CPU laptop; measured and documented cost profile (RAM, latency, concurrency). | Fresh-machine install from README succeeds **[manual]**; measured RAM, p50/p95 latency and max concurrency recorded in `docs/reports/`. | 13, 14 |
| L8 | Access bias | Offline bias-evaluation suite over demographic, dialect and cultural variants of identical scenarios. | One command runs the suite; decision-plane outputs (crisis flag, mode, triggers) match exactly across variants (100%); tone/length/resource-surfacing disparities computed and flagged against thresholds; report committed. | 12 |
| L9 | Low engagement | Fast replies, session continuity, warm companion/listening mode. | Companion replies follow "validate, then one gentle question" (automated checks); history restored after restart; latency targets met on the reference laptop **[manual measurement]**. | 1, 6, 13 |
| L10 | Technical & usability glitches | Graceful degradation: every request ends in a real or fallback reply within a hard timeout; safety survives any pipeline failure; usability checklist. | Fault-injection matrix (LLM down/slow/empty, guard rejects twice, DB locked/unavailable, explainability error) passes: every request answers within the timeout, crisis handoff works with LLM killed and storage broken; static help button works with the backend down. | 2, 13 |

## 5. Functional requirements

Requirement IDs are referenced by tests (`# covers: FR-SAF-3`).

### 5.1 Safety (FR-SAF)
| ID | Requirement |
|---|---|
| FR-SAF-1 | Every user message passes the safety layer **before** any storage access, planning or LLM call. |
| FR-SAF-2 | The safety layer normalises text (Unicode NFKC, case-fold, stretched letters, spacing/punctuation tricks, common leetspeak) then matches tiered phrase patterns from versioned data files: explicit intent, passive ideation, plan/method references, burden statements. |
| FR-SAF-3 | Any match triggers the crisis handoff. There is **no negation-based suppression**. The only false-positive reduction is a short allow-list of unambiguous idioms, each with its own test. |
| FR-SAF-4 | An optional classifier may only *add* alerts, never remove them. |
| FR-SAF-5 | The crisis handoff returns a fixed reply with verified crisis/human-help resources, makes **zero LLM calls**, and runs no routing, companion or guard logic. |
| FR-SAF-6 | The safety layer fails closed: an internal error is treated as a crisis verdict. |
| FR-SAF-7 | The handoff works with the LLM process killed and the database unavailable. The audit entry is written afterwards, in saved mode only, and its failure never affects the reply. |
| FR-SAF-8 | Post-crisis (provisional, clinician review): every later message still passes the safety gate first; the bot stays in minimal supportive mode until the user says they want to continue. |
| FR-SAF-9 | A positive answer (≥ 1) to PHQ-9 item 9 triggers the crisis protocol regardless of the total. |
| FR-SAF-10 | A static "Need help now?" button on every page shows crisis resources without any backend call. |
| FR-SAF-11 | Until Phase 2 passes, a startup tripwire refuses to start with the safety stub unless a development flag is set, and the UI shows a development banner. (Retired in Phase 2 with the stub.) |

### 5.2 Symptom screening — PHQ-9 / GAD-7 (FR-ASM)
| ID | Requirement |
|---|---|
| FR-ASM-1 | Official item wording and answer options stored in data files, verified against the published source in Phase 3. |
| FR-ASM-2 | Offered only when the conversation warrants it (screening-readiness score sustained above threshold, or an explicit request) and guards pass (not in crisis, not mid-exercise, not recently declined, cooldown since last administration). Never on a schedule. |
| FR-ASM-3 | Always an offer the user can decline; the reason for offering is stored. |
| FR-ASM-4 | Items asked one at a time with fixed 0–3 answer buttons; no LLM paraphrase, no LLM scoring. User may pause, resume or abort. |
| FR-ASM-5 | PHQ-9 bands: 0–4 minimal, 5–9 mild, 10–14 moderate, 15–19 moderately severe, 20–27 severe. GAD-7 bands: 0–4 minimal, 5–9 mild, 10–14 moderate, 15–21 severe. |
| FR-ASM-6 | The functional-difficulty question is recorded, not scored. Incomplete questionnaires are never scored. |
| FR-ASM-7 | Results are shown in plain language with the non-diagnostic statement, and fed to the planner and router. |

### 5.3 Therapy router — CBT / DBT / mindfulness (FR-RTR)
| ID | Requirement |
|---|---|
| FR-RTR-1 | A first-class, deterministic component: signals object in, mode decision + ranked per-signal contributions out. |
| FR-RTR-2 | Default mode is companion. A structured mode is *offered*, with consent, only when it leads the runner-up by a configured margin. |
| FR-RTR-3 | Hysteresis: a challenger mode must lead for N consecutive turns before a switch; acute overwhelm goes straight to a grounding exercise; no switch mid-exercise unless the user opts out. |
| FR-RTR-4 | Runs with no LLM present. |

### 5.4 Psychoeducation (FR-PSY)
| ID | Requirement |
|---|---|
| FR-PSY-1 | Separate module and content path from therapy delivery. |
| FR-PSY-2 | Triggered by stigma cues, symptom misunderstanding and "what's wrong with me"-type questions; silent on ordinary talk. |
| FR-PSY-3 | Every content item carries `source`, `reading_level`, `version` and `review_status`. |

### 5.5 Companion / active listening (FR-CMP)
| ID | Requirement |
|---|---|
| FR-CMP-1 | Reply pattern: validate the feeling, then one gentle question. |
| FR-CMP-2 | Automated checks reject over-praise, unprompted advice and dependency-fostering language ("I'm all you need", "you don't need anyone else"). |
| FR-CMP-3 | Subject to the hypercompliance guard: validating feelings is allowed, validating distortions is not. |

### 5.6 Hypercompliance guard (FR-GRD)
| ID | Requirement |
|---|---|
| FR-GRD-1 | Input-side distortion detector over Burns's categories. |
| FR-GRD-2 | Output-side checks: agreement markers beside an echo of the distorted claim; a restated global self-label; advice that presupposes the distortion; diagnosis or medication advice. |
| FR-GRD-3 | On failure: one constrained regeneration, then a fallback from a vetted Socratic question bank. No second LLM call beyond the single retry. |
| FR-GRD-4 | Same guard function on therapy and companion replies. |

### 5.7 Sentiment & behaviour tracking (FR-TRK)
| ID | Requirement |
|---|---|
| FR-TRK-1 | Text-only per-turn features: valence, emotion scores, first-person pronoun rate, absolutist-word rate, message length, within-session reply latency (capped), time of day. |
| FR-TRK-2 | Aggregation: per-session mean and variance, exponentially weighted trend, change flag against the user's own baseline once enough sessions exist. |
| FR-TRK-3 | Viewable, exportable, deletable; labelled **"language-based mood trend, not a clinical measure."** |
| FR-TRK-4 | Each feature carries a citation (checked in Phase 8) or is labelled exploratory. |

### 5.8 Explainability (FR-XAI)
| ID | Requirement |
|---|---|
| FR-XAI-1 | Every reply has an explanation built after decisions are final; generation of the explanation fails soft (reply still returned, explanation marked unavailable). |
| FR-XAI-2 | The explanation states it explains the *response strategy*, not the LLM's word choice. |
| FR-XAI-3 | Plain-language "why this reply" panel (fetched on demand) and a debug view with raw contributions. |

### 5.9 Privacy & autonomy (FR-PRV)
| ID | Requirement |
|---|---|
| FR-PRV-1 | First-use disclosure and consent gate the chat API. |
| FR-PRV-2 | Export (JSON) of everything stored about the user. |
| FR-PRV-3 | Delete account and data with `secure_delete` and WAL truncation. |
| FR-PRV-4 | Ephemeral mode: memory-only storage, nothing written to disk. |
| FR-PRV-5 | Pseudonymous accounts: no email, phone or real name collected. |
| FR-PRV-6 | Logs and per-turn traces never contain message text or session IDs. |

### 5.10 Cultural adaptation (FR-CUL)
| ID | Requirement |
|---|---|
| FR-CUL-1 | User-editable style profile: directness (direct / balanced / indirect), formality (casual / neutral / formal). |
| FR-CUL-2 | The system may *suggest* a change when it notices indirect phrasing; it never switches silently and never infers ethnicity or nationality. |
| FR-CUL-3 | Style changes framing only — never routing, triggers or safety (invariance tests). |

## 6. Non-functional requirements

### 6.1 Performance (measured on the reference laptop, targets not promises)
| Metric | Target |
|---|---|
| Safety gate latency | < 10 ms p99 |
| Everything except the LLM | < 150 ms p95 |
| End-to-end | Every request ends in a real or fallback reply inside a hard timeout (default 30 s, configurable) |
| Reply length | ~150 tokens cap; returned whole, not streamed (guard must see the full draft) |
| Prompt | Token-budgeted (system text, plan, short history, one snippet) |
| Concurrency | Measured and published in Phase 14 |

### 6.2 Reliability
- No silent hang: every failure path maps to a defined user-facing message ([design.md §12](design.md)).
- Safety never depends on the LLM or the database.
- LLM in a separate process with connect/read timeouts and a bounded request queue with a "busy" fallback.

### 6.3 Privacy and security
- Session ID in a header, never in URLs. Security headers and `Cache-Control: no-store` on every response.
- No external requests from the front end (no CDNs, fonts, analytics).
- Data-protection principles followed (consent, purpose limitation, access, erasure); wording requires legal review before real deployment.
- Disk encryption recommended in docs; the app cannot guarantee erasure from the physical device.

### 6.4 Accessibility
- Keyboard operable; visible focus; WCAG 2.2 AA contrast; ARIA labels and live regions for new messages; respects `prefers-reduced-motion`.

### 6.5 Cost
- Zero recurring cost: no paid API, no cloud dependency at runtime. Runs on one CPU laptop.

### 6.6 Maintainability
- Python 3.12, mypy strict, ruff, import-linter dependency rules, coverage ≥ 95% on safety/assessment/router and ≥ 85% overall.

## 7. Non-goals (v1)
- No voice, avatars or images.
- No diagnostic claims.
- No physiological or wearable signals.
- No full model retraining or fine-tuning. Runtime cultural adaptation is the priority; the WEIRD-data caveat is documented.
- No multilingual support (documented limitation).
- No live multi-user clinician access; "clinician view" = per-user debug panel + an exportable summary the user chooses to share.
- No streaming replies.
- No use with human participants inside this build (requires institutional ethics approval).

## 8. Assumptions
1. English-only text in v1.
2. Mid-range laptop, CPU-only inference; Colab only for heavy offline experiments.
3. Replies returned whole, capped at ~150 tokens; Phase 13 measures whether sentence-by-sentence streaming is worth it.
4. Clinician view as in §7.
5. Pseudonymous accounts (no email/phone).
6. Crisis policy as in FR-SAF-5..9, provisional pending clinician review.

## 9. Ground rules
- Nobody uses the bot — not even friends — until Phase 2 (safety) passes.
- No real user data is collected until Phase 10 (privacy controls) exists.
- Testing with human participants needs institutional ethics approval and is outside this build.

## 10. Success metrics
| Area | Metric | Target / reporting |
|---|---|---|
| Safety | Recall on held-out crisis phrases (incl. typos, dialect, code-mixed) | Reported; any miss is triaged as a defect |
| Safety | False-positive rate on benign set | Reported |
| Screening trigger | Precision / recall on labelled sample conversations | Reported |
| Guard | Detection rate / false-block rate | Reported |
| Bias | Decision-plane invariance | 100% |
| Explainability | Additivity check / determinism | 100% pass |
| Reliability | Fault-injection matrix | 100% of requests answered within timeout |
| Performance | Latency targets in §6.1 | Measured on reference laptop |
| Quality | Coverage | ≥ 95% safety/assessment/router; ≥ 85% overall |

## 11. Open items
| # | Item | Owner | Needed by |
|---|---|---|---|
| O1 | Open-source licence choice for the repository | Smriti | Before first public push |
| O2 | Crisis resource list — two tiers decided 2026-10-07; built in Phase 2 as 40 Tier 1 countries with a verified crisis line and 184 Tier 2 countries and territories with the emergency number (target was 64 Tier 1; the rest could not be verified on an official site); originally India, Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Myanmar, China, South Korea, Japan, Thailand, Maldives, Vietnam, Hong Kong, Taiwan, Cambodia, Malaysia, Singapore, Russia); numbers verified against official sources at build time | Build | Phase 2 |
| O3 | Qualified clinician reviewer for [clinical_review.md](clinical_review.md) | Smriti | Before any real use |
| O4 | Institutional ethics approval for any human-participant testing | Smriti | Before usability testing with participants |
| O5 | Optional PostgreSQL adapter | Smriti decides | Phase 14, only if requested |
| O6 | Report-ready diagram exports (SVG/PNG from Mermaid) | Build | Phase 14 |
| O7 | Model facts (Qwen3.5-4B, Gemma 4 E4B-it, Phi-4-mini) re-verified against current model cards and licences | Build | Phase 1 |
| O8 | Legal review of disclosure wording | Smriti | Before real deployment |
