# OASIS — 14-Phase Build Plan

Each phase runs on its own branch (`phase-NN-short-name`) and merges to `main` only after approval. Phases are strictly sequential.

## How every phase runs

1. State the goal and the done-when checklist (from this file).
2. Explain the plan: files, classes/functions, and why.
3. Write tests first for critical logic (safety, scoring, routing, guard, privacy).
4. Implement.
5. Run `make verify` and show the real output.
6. Walk through the code module by module.
7. Write the report section (`docs/reports/phase-NN.md`): design, evaluation, results, known limits.
8. Update [memory.md](memory.md) and commit.

### Shared "done" checklist (every phase)
- [ ] Tests green (no failing, skipped or xfail tests)
- [ ] Lint, format, types, import rules, bandit, pip-audit clean
- [ ] Coverage thresholds met (≥ 95% safety/assessment/router; ≥ 85% overall)
- [ ] Docs and [clinical_review.md](clinical_review.md) updated
- [ ] A demo (UI walkthrough or script output)
- [ ] [memory.md](memory.md) updated
- [ ] Smriti's approval

### Two deliberate departures from strict order
These are **skeletons, not features**:
- **Interfaces and the per-turn trace** are created in Phase 1 (LLM client, repository, safety gate hook, planner hook, guard hook, trace object).
- **A pass-through guard hook** exists from Phase 4 so Phase 7 plugs in without refactoring.

**Signal extraction** is built in Phase 4 alongside the router and reused in Phases 5–8.

---

## Phase overview

| # | Phase | Branch | Done when |
|---|---|---|---|
| 1 | Core chat loop | `phase-01-core-chat-loop` | Multi-turn chat works in the UI against a fake LLM; history survives restart; LLM timeout returns a fallback, never a hang; one command runs lint, types and tests |
| 2 | Safety layer | `phase-02-safety-layer` | Every known trigger phrase (explicit, passive, typos, dialect) caught; false-positive rate on a benign set reported; handoff makes zero LLM calls (tested); still answers with the LLM killed and storage broken; static help button works offline |
| 3 | Assessment | `phase-03-assessment` | Boundary tests at every band edge; item-9 escalation tested; consent, pause and abort tested; trigger heuristic scored on labelled sample conversations (precision/recall reported) |
| 4 | Therapy router | `phase-04-therapy-router` | Scenario table (signals → expected mode) passes; no flip-flopping on noisy sequences; acute override works; every decision returns ranked contributions; runs without an LLM |
| 5 | Psychoeducation | `phase-05-psychoeducation` | Triggers fire on stigma and "what's wrong with me" cues and stay quiet on ordinary talk; each content item carries source, reading level and review status |
| 6 | Companion mode | `phase-06-companion` | Replies follow "validate the feeling, then a gentle question"; automated checks for over-praise, unprompted advice and dependency language pass; Smriti reviews sample transcripts |
| 7 | Hypercompliance guard | `phase-07-guard` | Curated distortion + sycophantic-reply set caught at a reported rate; benign replies not blocked (false-block rate reported); reroute yields a Socratic question; active in therapy and companion paths |
| 8 | Sentiment tracking | `phase-08-tracking` | Golden tests on feature extraction; correct aggregation on synthetic timelines; trend view labelled non-clinical; ephemeral mode stores nothing |
| 9 | Explainability | `phase-09-explainability` | Every reply has an explanation; SHAP additivity check passes; deterministic output; plain-language "why this reply" panel and debug view work; latency overhead within budget |
| 10 | Privacy & autonomy | `phase-10-privacy` | First-use disclosure gates the API; export round-trips; delete leaves zero rows (automated schema crawl) and no content in logs; ephemeral mode leaves no files on disk |
| 11 | Cultural adaptation | `phase-11-style` | Same input under different styles gives different framing; safety and mode invariance tests pass; user can change style |
| 12 | Bias evaluation | `phase-12-bias-eval` | One command runs the suite; decision-plane invariance 100%; quality disparities flagged against thresholds; report committed |
| 13 | Engagement & reliability | `phase-13-reliability` | Fault-injection matrix passes (every request answers within the timeout); session continuity works; load and latency measured on the reference laptop; usability checklist passed |
| 14 | Cost & access docs | `phase-14-cost-access` | Fresh-machine install from README works; measured RAM, latency and concurrency recorded; limitations stated (English-only, no fine-tuning, WEIRD-data caveat) |

---

## Phase 1 — Core chat loop

**Goal.** A working, well-tested skeleton: the full request path with pass-through hooks, a fake LLM, durable history, and the quality toolchain.

**Scope.**
- Project tooling: `pyproject.toml` (uv), `uv.lock`, `Makefile` (`make verify`, `make run`, `make test`), `.pre-commit-config.yaml`, `.importlinter`, `.github/workflows/ci.yml`, `.env.example`.
- API: `POST /chat`, `GET /history`, `GET /health`; session ID in `X-OASIS-Session` header; security headers; `Cache-Control: no-store`; request size limit.
- Engine: `ChatEngine.handle_turn()` with pass-through hooks for safety gate, planner and guard; deadline propagation; per-turn trace without user text; content-free logging.
- LLM: `LLMClient` protocol, `FakeLLM` (deterministic), `LlamaServerClient` (thinking off, think-tags stripped), templated fallback for errors/timeouts/empty output, concurrency limiter with queue limit and "busy" fallback.
- Storage: `Repository` protocol; `SQLiteRepository` (WAL, FKs, STRICT, migrations `0001_init.sql`) and `MemoryRepository`; one contract suite.
- Safety stub: fails closed on error; startup tripwire refuses to run it without `OASIS_DEV_MODE=1`.
- UI: calm text-only chat page, no external requests, static "Need help now?" button, visible development banner.
- Scripts: `scripts/db_benchmark.py`, `scripts/model_smoke_test.py`, `scripts/model_bakeoff.py` (RAM, first-token time, tokens/sec).

**Files/modules.** `src/oasis/{types.py, settings.py}`, `api/{app.py, routes.py, schemas.py, middleware.py}`, `core/{engine.py, trace.py, templates.py, recorder.py, planner.py (pass-through)}`, `safety/{gate.py (stub)}`, `llm/{client.py, fake.py, llama_server.py, prompt.py, fallback.py, limiter.py}`, `storage/{repository.py, sqlite.py, memory.py, migrations/0001_init.sql}`, `web/{index.html, app.js, styles.css, debug.html}`.

**Tests first.**
- `tests/contract/test_repository_contract.py` (parametrised over both backends): create/read session, append/read turns in order, user scoping, restart persistence (SQLite).
- `tests/unit/test_llm_fallback.py`: timeout, connect error, HTTP 500, empty output, think-only output, unterminated `<think>` → templated reply; think-tags never reach output.
- `tests/unit/test_limiter.py`: queue full → busy fallback immediately.
- `tests/unit/test_safety_stub.py`: stub exception → crisis verdict (fail closed); tripwire refuses start without dev flag.
- `tests/integration/test_chat_api.py`: multi-turn chat; session header required; history endpoint; security headers present; `no-store`.
- `tests/unit/test_logging_privacy.py`: logs contain no marker message text or session ID; trace has no text fields.
- `tests/fault_injection/test_llm_hang.py`: slow fake LLM → reply within `request_timeout_s`.

**Done when.** Multi-turn chat works in the UI against `FakeLLM`; history survives restart; LLM timeout returns a fallback, never a hang; `make verify` runs lint, types, import rules, security scan and tests with coverage.

**Report topic.** Architecture skeleton and failure-first design: process isolation, deadlines, templated fallback, repository contract.

---

## Phase 2 — Safety layer

**Goal.** Replace the stub with the real rule-based crisis detector and handoff.

**Scope.** Normaliser; tiered pattern matcher; allow-list; add-only classifier hook (interface only); crisis handoff with verified resources; post-crisis state; audit entry after reply (saved mode); static help card with real resources; held-out recall set and benign set; `docs/clinical_review.md` entries.

**Files.** `safety/{normalize.py, patterns.py, matcher.py, gate.py, handoff.py}`, `content/safety/{patterns.yaml, allowlist.yaml, resources.yaml}`, `tests/data/safety/{train_phrases.yaml, heldout_phrases.yaml, benign.yaml}`, `scripts/safety_eval.py`.

**Tests first.**
- Normaliser golden tests (Unicode confusables, case, stretched letters `kiiiill`, spacing `k i l l`, punctuation `k.i.l.l`, leetspeak `k1ll`).
- One test per pattern and per allow-list idiom; negation does not suppress (`"I'm not going to kill myself"` triggers).
- Handoff makes zero LLM calls (spy LLM fails the test on call); zero storage calls before reply.
- Fault injection: LLM killed + repository raising on every call → crisis reply still returned.
- Gate exception → crisis verdict; invalid pattern file → startup refusal.
- Performance: gate < 10 ms p99 over 10 000 messages (local measurement).
- Static help card: page served with backend stopped (file test) shows resources; no network request in `app.js` for the card.

**Done when.** See overview row. Recall on held-out set and FPR on benign set reported in `docs/reports/phase-02.md`. Tripwire removed.

**Report topic.** Rule-based crisis detection: normalisation, tiering, fail-closed design, recall/FPR methodology.

---

## Phase 3 — Assessment (PHQ-9 / GAD-7)

**Goal.** Standard screening with a conversation-aware offer.

**Scope.** Item data files verified against the published source; state machine (offer → consent/decline → items → functional question → score → plain-language result); pause/resume/abort; item-9 escalation; screening-readiness score over a sliding window with guards (not in crisis, not mid-exercise, not recently declined, cooldown 14 days); reason-for-offer stored; assessment card UI with 0–3 buttons.

**Files.** `assessment/{instruments.py, scoring.py, state_machine.py, trigger.py}`, `content/assessment/{phq9.yaml, gad7.yaml, result_text.yaml}`, `storage/migrations/0002_assessments.sql`, `tests/data/assessment/labelled_conversations.yaml`.

**Tests first.**
- Hypothesis: total = sum of answers; total ∈ [0, 27] / [0, 21]; band is monotone in total; every total maps to exactly one band; incomplete never scored.
- Boundary table at every band edge (4/5, 9/10, 14/15, 19/20 for PHQ-9; 4/5, 9/10, 14/15 for GAD-7).
- Item 9 = 1, 2, 3 → crisis protocol regardless of total; item 9 = 0 → no escalation.
- Consent decline stored with reason; pause/resume keeps state across turns; abort discards without scoring.
- Trigger guards: crisis, mid-exercise, recently declined, cooldown each block the offer.
- CHECK constraint rejects answer 4 at the DB level.

**Done when.** See overview row; precision/recall of the trigger on labelled conversations reported.

**Report topic.** Standardised screening inside a conversational agent; consent-first offer design; trigger evaluation.

---

## Phase 4 — Therapy router (+ signal extraction, guard hook)

**Goal.** Deterministic, explainable mode selection.

**Scope.** Signals object and detectors (lexicon scorers in YAML, VADER valence baseline); router weighted sum; margin; hysteresis; acute-overwhelm override; no mid-exercise switch; consent before entering a structured mode; pass-through guard hook; planner precedence wired.

**Files.** `core/signals.py`, `core/detectors/{lexicon.py, valence.py}`, `router/{weights.py, router.py, hysteresis.py}`, `content/router/weights.yaml`, `content/lexicons/*.yaml`, `guard/hook.py`.

**Tests first.**
- Scenario table (≥ 30 rows): signals → expected mode.
- Noisy sequences (alternating weak cues) → no flip-flopping within N turns.
- Acute overwhelm → immediate grounding even mid-hysteresis.
- Mid-exercise → no switch unless opt-out.
- Hypothesis: `bias + Σ contributions == score` for every mode; contributions sorted by |value|.
- Router imports no `oasis.llm` (import-linter).

**Done when.** See overview row.

**Report topic.** Transparent policy for therapeutic mode selection; hysteresis as a stability mechanism.

---

## Phase 5 — Psychoeducation

**Goal.** Contextual, stigma-reducing explanations from vetted content.

**Scope.** Cue detector (stigma, symptom misunderstanding, "what's wrong with me"); content selector; content items with `source`, `reading_level`, `version`, `review_status`; planner precedence slot.

**Files.** `psychoed/{cues.py, selector.py}`, `content/psychoed/items.yaml`, `scripts/readability.py`.

**Tests first.** Trigger set fires; ordinary-talk set stays quiet (FPR reported); schema test that every item has the four fields; reading level computed and ≤ target grade.

**Done when.** See overview row.

**Report topic.** Psychoeducation as a separate content path; stigma cue detection.

---

## Phase 6 — Companion mode

**Goal.** Warm active listening without sycophancy.

**Scope.** Companion plan; prompt template; output checks (one question, validation phrase present, no over-praise, no unprompted advice, no dependency language); sample transcripts for review; first real-model tone check (script).

**Files.** `companion/{plan.py, checks.py}`, `content/companion/{validation_phrases.yaml, banned_patterns.yaml}`, `scripts/tone_check.py`.

**Tests first.** Checks catch curated bad replies; accept curated good replies; exactly one question mark-terminated sentence; templated fallback passes its own checks.

**Done when.** See overview row; transcripts reviewed by Smriti ("not verified here" until real-model run).

**Report topic.** Warmth vs sycophancy: designing an active-listening mode with explicit constraints.

---

## Phase 7 — Hypercompliance guard

**Goal.** Detect and reroute replies that validate a cognitive distortion.

**Scope.** Input-side distortion detector (Burns's categories); output checks (agreement marker + claim echo, restated global self-label, presupposing advice, diagnosis/medication); one constrained retry; vetted Socratic fallback bank; active in therapy and companion paths.

**Files.** `guard/{distortions.py, checks.py, guard.py}`, `content/guard/{distortions.yaml, agreement_markers.yaml, socratic_bank.yaml}`, `tests/data/guard/{sycophantic.yaml, benign_replies.yaml}`.

**Tests first.** Curated sycophantic replies rejected; benign replies pass (false-block rate); retry carries constraints; second rejection → Socratic fallback with exactly one question; diagnosis/medication phrases rejected; guard invoked on both paths (spy).

**Done when.** See overview row.

**Report topic.** A rule-based hypercompliance guard for LLM replies; evaluation on curated sets.

---

## Phase 8 — Sentiment tracking

**Goal.** Language-based mood trend, honestly labelled.

**Scope.** Per-turn features; aggregation (session mean/variance, EWMA trend, change flag vs own baseline after ≥ K sessions); trend view; export/delete inclusion; citations per feature or "exploratory" label.

**Files.** `tracking/{features.py, aggregate.py}`, `storage/migrations/0003_signals.sql`, `web/trends.html`.

**Tests first.** Golden feature tests; aggregation on synthetic timelines (known mean/variance/EWMA); change flag fires only after baseline exists; latency capped; ephemeral stores nothing.

**Done when.** See overview row.

**Report topic.** Text-derived behavioural signals and their limits.

---

## Phase 9 — Explainability

**Goal.** Every reply explains why its strategy was chosen.

**Scope.** Spike: confirm `shap` installs cleanly on Python 3.12 (Windows + Linux CI). `LinearExplainer` for linear detectors; exact router decomposition; LIME only for black-box parts; explanation record; plain-language panel; debug view; fail-soft.

**Files.** `explain/{shap_explainer.py, router_explainer.py, builder.py, plain_language.py}`, `api/routes_explain.py`, `web/{why.js, debug.html}`, `storage/migrations/0004_explanations.sql`.

**Tests first.** Additivity (`base + Σφ == output`, tol 1e-6); determinism (same input → identical JSON); every reply has an explanation or `unavailable` with reason; explainability error does not affect reply; overhead within budget.

**Done when.** See overview row.

**Report topic.** Explaining response strategy, not words: SHAP on a hybrid rule/LLM system.

---

## Phase 10 — Privacy & autonomy

**Goal.** User control over data and a first-use disclosure.

**Scope.** Disclosure + consent screen gating the API; self-harm disclosure policy; export (JSON); delete with `secure_delete` + WAL truncate; ephemeral mode end to end; pseudonymous accounts.

**Files.** `api/routes_privacy.py`, `storage/{export.py, delete.py}`, `web/{onboarding.html, settings.html}`, `content/privacy/disclosure.md`.

**Tests first.** 403 before consent; export round-trip; schema crawl → zero rows after delete; marker absent from `.db`/`-wal`; logs contain no content; ephemeral → filesystem diff empty.

**Done when.** See overview row.

**Report topic.** Privacy by design for a sensitive-data chatbot; verifiable erasure.

---

## Phase 11 — Cultural adaptation

**Goal.** User-controlled communication style that changes framing only.

**Scope.** Style profile (directness, formality) in settings UI; framing instructions in prompt builder; indirect-phrasing suggestion (never automatic); no ethnicity/nationality inference.

**Files.** `style/{profile.py, framing.py, suggest.py}`, `content/style/framing.yaml`.

**Tests first.** Different style → different prompt framing; crisis verdict, plan mode and triggers invariant across all style combinations (property test); suggestion never changes the profile.

**Done when.** See overview row.

**Report topic.** Runtime cultural adaptation without demographic inference.

---

## Phase 12 — Bias evaluation

**Goal.** Measure decision-plane invariance and output disparities across framings.

**Scope.** Scenario templates with demographic, dialect and cultural variants (including dialect and code-mixed crisis phrasing); decision-plane invariance check; tone/length/resource-surfacing statistics with thresholds; committed report.

**Files.** `scripts/bias_eval.py`, `tests/bias/{scenarios.yaml, variants.yaml}`, `docs/reports/bias_eval.md`.

**Tests first.** Invariance (100%) runs in CI with `FakeLLM`; quality comparison runs with the real model (script, "not verified here").

**Done when.** See overview row.

**Report topic.** Counterfactual bias evaluation of a hybrid chatbot.

---

## Phase 13 — Engagement & reliability

**Goal.** Prove graceful degradation and measure responsiveness.

**Scope.** Full fault-injection matrix; session continuity (resume after restart); load test (concurrent sessions) and latency profile on the reference laptop; usability checklist (heuristic review); streaming feasibility measurement.

**Files.** `tests/fault_injection/*`, `scripts/load_test.py`, `docs/reports/reliability.md`, `docs/usability_checklist.md`.

**Done when.** See overview row.

**Report topic.** Reliability engineering for acute-moment use.

---

## Phase 14 — Cost & access docs

**Goal.** Anyone can install and run OASIS on a modest laptop; costs are measured and published.

**Scope.** README install guide verified on a fresh machine; measured RAM, latency, concurrency; limitations section; report-ready diagram exports; optional PostgreSQL adapter only if requested.

**Done when.** See overview row.

**Report topic.** Cost and access profile of a local-first mental health chatbot.
