# OASIS — Project Memory

Handover log so any session can resume without re-explaining. Neutral engineering log; keep it concise and current. Update at the end of every phase and every working session.

**Start of every session:** read this file and [rules.md](rules.md), then continue from *Current status*.

---

## Current status

| | |
|---|---|
| Current phase | **Phase 2 — safety layer** (complete, awaiting review) |
| Done | Step A and Phase 1 (approved and merged 2026-10-07). Phase 2 on branch `phase-02-safety-layer`: normaliser, 34 crisis patterns in 5 tiers, idiom allow-list, fail-closed gate, 224-country help card, post-crisis mode, crisis audit; `scripts/verify.py` all green; report in `docs/reports/phase-02.md` |
| In progress | Review of Phase 2 by Smriti |
| Next | Merge Phase 2 to `main` after approval → Phase 3 (PHQ-9/GAD-7) on `phase-03-assessment` |
| Blocked on | Phase 2 approval; browser check of 5 crisis lines (open item 8) |

### Environment notes (development machine, 2026-10-07)
- Windows 11. Python 3.12.15 managed by uv (system Python 3.11.9 is not used); uv 0.12.23 installed with `python -m pip install --user uv` and invoked as `python -m uv`.
- No `make` on Windows: `uv run python scripts/verify.py` is the verify command; the Makefile is a thin wrapper for CI/Linux/macOS.
- Local dev server: copy `.env.example` to `.env`, then `uv run uvicorn oasis.api.app:create_app --factory`.
- Git identity: the global config (`smritisingh-0401`) is used, as approved 2026-10-07.
- Assistant config files are excluded through `.git/info/exclude` (local, uncommitted).

---

## Decision log

| Date | Decision | Reason | Alternatives rejected |
|---|---|---|---|
| 2026-10-07 | Architecture **v2**: layered components inside a privacy envelope; rule-based decision plane plans, LLM only phrases | Explainability, safety, testability; LLM failure cannot change *what* the reply does | LLM-as-agent deciding strategy; end-to-end fine-tuned model |
| 2026-10-07 | **Safety before storage**: safety check runs before any DB read; crisis audit written after reply, saved mode only | A storage failure must never block the crisis handoff | Load state first (original data-flow PNG) |
| 2026-10-07 | Safety layer is pure Python rules, no LLM/network/DB imports, fails closed, no negation suppression; only an idiom allow-list | Deterministic, auditable, fast (< 10 ms); negation handling causes missed detections | LLM-based risk classification; negation-aware suppression |
| 2026-10-07 | Crisis handoff: fixed reply, zero LLM calls, no routing/guard; provisional post-crisis minimal supportive mode until the user opts to continue | Predictability at the highest-risk moment | Generated crisis replies |
| 2026-10-07 | Crisis message text is not written to history (recorder does not run on crisis); audit holds pattern IDs and tiers only | Follows "nothing else runs" on crisis; minimises stored sensitive text | Store crisis text in turns |
| 2026-10-07 | PHQ-9/GAD-7 only, standard items and bands, fixed buttons, no LLM paraphrase/scoring; item 9 ≥ 1 → crisis | Free, short, most validated; avoids licensed instruments | BDI-II and other licensed instruments |
| 2026-10-07 | Planner fixed precedence: (post-crisis) → assessment in progress → psychoeducation → assessment offer → router/companion | One mode per turn; predictable, testable | Learned mode selection |
| 2026-10-07 | Router = weighted sum per mode with margin + hysteresis; acute overwhelm overrides; default companion | Exact per-signal contributions; stability | Classifier-based routing |
| 2026-10-07 | Guard after LLM: prompt steering → check → one constrained retry → vetted Socratic fallback | Bounded latency; no sycophancy reaches the user | Unlimited regeneration; LLM-as-judge |
| 2026-10-07 | **SQLite (WAL)** via stdlib `sqlite3` behind a repository interface; in-memory twin for ephemeral mode; PostgreSQL optional later | One process, few writes per multi-second turn; one file to export/delete; no server | PostgreSQL in v1; ORM; JSON files |
| 2026-10-07 | LLM runtime: llama.cpp `llama-server` as a separate, version-pinned process | Crash/hang isolation; supports the hybrid architecture; CPU-friendly | Ollama (bundled runtime reported too old); in-process bindings |
| 2026-10-07 | Default model **Qwen3.5-4B GGUF Q4_K_M**; challenger Gemma 4 E4B-it; low-RAM fallback Phi-4-mini; bake-off decides; model is a config line | Free licence, small, multilingual; must pass tone checks | Paid APIs; larger models |
| 2026-10-07 | Thinking disabled; think-tags stripped; think-only output treated as empty | No reasoning text may reach the user | Relying on template defaults |
| 2026-10-07 | Explainability: SHAP `LinearExplainer` on linear detectors, exact decomposition for router; LIME only for black-box parts | Exact, deterministic explanations | LIME everywhere; attention-based explanations |
| 2026-10-07 | Explanations describe the response strategy, not LLM wording | Honest scope | — |
| 2026-10-07 | Front end: plain HTML/CSS/JS, no build step, no external requests | Nothing extra to break; privacy | React/Vue SPA; CDN assets |
| 2026-10-07 | **No streaming in v1**; replies ~150 tokens returned whole | Guard must see the full draft; Phase 13 measures streaming | Token streaming |
| 2026-10-07 | Detectors: hand-weighted YAML lexicons, scikit-learn linear models, VADER baseline; fine-tuned transformer as later ablation | Transparent, instant on CPU | Transformer classifiers in v1 |
| 2026-10-07 | Style profile (directness, formality) is user-set, framing only; never infers ethnicity/nationality | Cultural adaptation without demographic inference | Automatic style switching |
| 2026-10-07 | Bias evaluation is an offline harness, not a runtime component | Keeps runtime simple | Runtime bias monitoring |
| 2026-10-07 | Quality toolchain: pytest, Hypothesis, pytest-cov, ruff, mypy strict, bandit, pip-audit, import-linter, pre-commit, GitHub Actions; uv lockfile; `make verify` | Each catches a different bug class; reproducible | — |
| 2026-10-07 | Coverage ≥ 95% on safety/assessment/router; ≥ 85% overall | Safety-critical code held to a higher bar | — |
| 2026-10-07 | Session ID is a 256-bit bearer token in `X-OASIS-Session`, stored hashed; single uvicorn worker | Never in URLs; ephemeral store and SQLite writer need one process | Cookies; multi-worker |
| 2026-10-07 | Assessment answers and consents are structured actions on `POST /chat` | Every turn passes the same engine and safety ordering | Separate assessment endpoint |
| 2026-10-07 | Shared types in top-level `oasis.types` | Lets `oasis.safety` stay isolated from `oasis.core` | Types inside `oasis.core` |
| 2026-10-07 | Crisis resources extended to two tiers: Tier 1 (verified crisis line + emergency number) targeted at 64 countries across all inhabited regions (built as 40; see 2026-10-08); Tier 2 (emergency number only) for every other country | World coverage while keeping the set of crisis lines that must be re-verified manageable; v1 is English-only, so English-speaking countries were prioritised | Full entries for every country; Asia-only list |
| 2026-10-07 | (superseded) Crisis resources cover India, Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Myanmar, China, South Korea, Japan, Thailand, Maldives, Vietnam, Hong Kong, Taiwan, Cambodia, Malaysia, Singapore, Russia; country chosen by the user (optional), never inferred | Target user regions; consistent with no-nationality inference | Single configured region; locale/IP inference |
| 2026-10-07 | Assistant config files excluded via `.git/info/exclude` instead of `.gitignore` | Keeps them out of git without naming them in the repository | Listing them in `.gitignore` |
| 2026-10-07 | Phase 1: turn recording lives in `ChatEngine` (no separate `core/recorder.py`) | One call site; a separate module would be a one-function wrapper | Separate recorder module |
| 2026-10-07 | Phase 1: fallback templates are Python constants until the Phase 2 content loader | Avoids adding YAML loading before it has a second user | YAML now |
| 2026-10-07 | Phase 1: storage backend chosen by settings; `POST /session` has no body; per-session ephemeral mode deferred to Phase 10 | Ephemeral end-to-end is Phase 10 scope | Per-session ephemeral now |
| 2026-10-07 | Phase 1: `/history` supports `limit` only; `before` pagination deferred | No caller needs it yet | Implement now |
| 2026-10-07 | Help card uses a native `<details>` element | Opens with no JavaScript and no server (S12, F2) | JS dialog |
| 2026-10-07 | Pytest ignores Starlette's "use httpx2" TestClient deprecation (message-specific filter; all other warnings stay errors) | Avoids adopting a new package only for tests | Add httpx2 |
| 2026-10-07 | pip-audit runs on `uv export` output with hashes and `--disable-pip` | Audits exactly the lockfile; uv venvs have no pip | Auditing the live environment |
| 2026-10-07 | Dev dependency `psutil` (+ `types-psutil`) | Cross-platform RSS measurement in the model bake-off | Manual Task Manager readings |
| 2026-10-08 | Normalisation produces up to 4 variants (base, leetspeak, unspaced, both); patterns are made tolerant of repeated letters by a load-time rewrite | Catches obfuscation without hand-writing letter repeats in every pattern | One normalised string; hand-written `ki{1,2}ll` patterns |
| 2026-10-08 | New `self_harm` tier: non-suicidal self-injury gets the full handoff | Self-injury disclosures need the same human support signposting (CR-01, to confirm) | Treat as non-crisis |
| 2026-10-08 | Allow-list suppresses a hit only when the idiom span covers the hit span | "dying to see it, I want to kill myself" must still trigger | Message-level suppression |
| 2026-10-08 | Invalid safety content stops the app at startup (validation plus example self-check) | Bad content fails at boot, never at turn time | Skip bad patterns with a warning |
| 2026-10-08 | Help card rendered on the server into `index.html` as nested `<details>`; no JavaScript or fetch | Works with the backend down after page load (S12, F2) | JSON endpoint plus client rendering |
| 2026-10-08 | Crisis resources: Tier 1 needs a line verified on the service's own or a government site; Tier 2 uses UK FCDO travel advice emergency numbers | One consistent, citable standard; no unverified numbers | Aggregator sites; unverified lists |
| 2026-10-08 | Sites that blocked the fetcher were not bypassed (no user-agent spoofing or disabled certificate checks); those countries are Tier 2 until checked in a browser | Verification must be honest | Bypassing blocks |
| 2026-10-08 | Crisis audit, post-crisis flag and history placeholder written by a background task after the response | Storage can never delay or block the handoff (S2) | Writing before responding |
| 2026-10-08 | Post-crisis state: in-memory set plus persisted flag; cleared only by an explicit continue phrase or the "Continue talking" button | Holds when storage is down; never inferred | Time-based expiry |
| 2026-10-08 | Templates stay Python constants (CR-18) | The Phase 2 content files are safety data with their own loaders; templates have no second user yet | YAML template loader now |
| 2026-10-08 | No classifier hook in the gate until a classifier exists (S7 still applies to any future one) | No speculative interface | Pluggable classifier parameter |
| 2026-10-07 | Git: commits authored as Smriti; no assistant attribution anywhere; assistant config files git-ignored; Conventional Commits; one branch per phase | Authorship and repository hygiene | — |

---

## Open items / questions for Smriti

8. **Browser check of crisis lines** that could not be fetched here, to promote them to Tier 1: Philippines NCMH 1553, Chile *4141, Colombia 192 option 4, Pakistan Umang, and Sweden's Mind line hours.
9. **Confirm the `self_harm` tier** (CR-01).
10. **A fresh external held-out phrase set**: the Phase 2 held-out set was used for tuning and is now consumed.
2. **Python 3.12 and uv** need installing on the development machine.
3. **Repository licence** (e.g. MIT, Apache-2.0).
4. **Clinician reviewer** for `clinical_review.md`.
5. **Ethics approval** route for any future usability testing with participants.
6. **Optional PostgreSQL adapter** (Phase 14) — only if requested.
7. **Reference laptop specs** (CPU, RAM, OS) for performance targets.

---

## Known limitations and "not verified here"

| Item | Status |
|---|---|
| Real-model speed (first-token time, tokens/sec, RAM) | Not verified here — `scripts/model_bakeoff.py` to be run on the reference laptop |
| Real-model reply + thinking disabled | Not verified here — `scripts/model_smoke_test.py` |
| llama.cpp build pin | Pending the first bake-off run (record `llama-server --version`) |
| Real-model tone (companion, guard, bias quality) | Not verified here |
| Qwen3.5 thinking-disable mechanism and sampling settings | To be re-verified against the current model card in Phase 1 |
| Model licences (Qwen3.5, Gemma 4, Phi-4-mini) | To be re-verified in Phase 1 |
| PHQ-9 / GAD-7 item wording | To be verified against the published source in Phase 3 |
| Crisis resource numbers | Verified 2026-10-08 against official sources (Tier 1) and FCDO (Tier 2); re-verify before any participant use |
| Post-crisis flag after an app restart with storage down | Falls back to normal mode (documented, CR-05) |
| Gate latency on dense 2 000-character input | 10–35 ms on battery, over the 10 ms target; realistic messages p99 0.55 ms; combined pre-filter is the upgrade path |
| Crisis detection recall on unseen phrasing | 88.7% on the held-out set before tuning; needs a fresh external set |
| English-only; no fine-tuning; WEIRD-data caveat | By design for v1 |

---

## Measured results

| Date | Phase | Measure | Result |
|---|---|---|---|
| 2026-10-07 | 1 | Tests | 121 passed, 0 skipped |
| 2026-10-07 | 1 | Coverage | 98.73% overall; `oasis.safety` 100% |
| 2026-10-07 | 1 | Mutation spot-check | 5/5 deliberate faults caught |
| 2026-10-07 | 1 | SQLite turn-pair write (dev machine) | p50 0.55 ms, p95 0.94 ms, p99 1.80 ms |
| 2026-10-07 | 1 | SQLite last-6-turns read (dev machine) | p50 0.22 ms, p95 0.40 ms, p99 0.50 ms |
| 2026-10-07 | 2 | Held-out crisis recall (before tuning) | 63/71 = 88.7% |
| 2026-10-08 | 2 | Tests | 481 passed, 0 skipped |
| 2026-10-08 | 2 | Benign false positives | everyday 0/50; idioms 0/30; third-party mentions 4/5 (by design) |
| 2026-10-08 | 2 | Gate latency (battery) | realistic p99 0.55 ms; 2 000-char stress inputs 10–35 ms |
| 2026-10-08 | 2 | Mutation spot-check | 12/12 caught after adding the help card escaping test (11/12 before) |
| 2026-10-08 | 2 | Coverage | 98.09% overall; `oasis.safety` 97.13% |

---

## Glossary

| Term | Meaning |
|---|---|
| **Decision plane** | The deterministic modules (signals, planner, assessment, router, psychoeducation, companion, style) that decide what a reply should do |
| **Signals object** | Frozen per-turn record of detector outputs and behavioural features (`oasis.types.Signals`) |
| **Plan** | The planner's output: one mode, constraints, optional technique/snippet/assessment step, style; the LLM only phrases it |
| **Mode** | One of crisis, post_crisis, assessment, psychoed, companion, cbt, dbt, mindfulness, grounding |
| **Safety layer / gate** | Pure-Python crisis detector that runs first on every message |
| **Crisis handoff** | Fixed reply with verified resources; zero LLM calls |
| **Post-crisis mode** | Minimal supportive templated mode after a handoff until the user opts to continue |
| **Templated reply** | Vetted fixed text used for assessment turns and every failure path |
| **Guard** | Post-generation checks (hypercompliance, diagnosis/medication, companion constraints) with one retry and a Socratic fallback |
| **Hypercompliance / sycophancy** | Agreeing with or reinforcing a cognitive distortion instead of gently examining it |
| **Socratic fallback** | A vetted question from the question bank used when the guard rejects twice |
| **Hysteresis** | Router rule that a challenger mode must lead for N consecutive turns before switching |
| **Screening-readiness score** | Sliding-window evidence score that governs when an assessment is offered |
| **Turn trace** | Per-turn timings, decisions and reason codes — never user text |
| **Ephemeral mode** | Session-only, memory-only storage; nothing written to disk |
| **Privacy envelope** | Consent gate, ephemeral mode, export and delete wrapping the whole system |
| **Content library** | Versioned read-only YAML (patterns, lexicons, items, scripts, question bank) with provenance |
| **Not verified here** | A result that needs the real model or reference laptop and awaits Smriti's local run |
