# OASIS — Project Memory

Handover log so any session can resume without re-explaining. Neutral engineering log; keep it concise and current. Update at the end of every phase and every working session.

**Start of every session:** read this file and [rules.md](rules.md), then continue from *Current status*.

---

## Current status

| | |
|---|---|
| Current phase | **Phase 1 — core chat loop** (starting) |
| Done | Step A approved 2026-10-07: PRD, architecture, rules, phases, design, memory, clinical review, README, `.gitignore`, diagram PNGs |
| In progress | Phase 1 on branch `phase-01-core-chat-loop` |
| Next | Phase 1 review |
| Blocked on | Python 3.12 and `uv` on the development machine |

### Environment notes (development machine, 2026-10-07)
- Windows 11; Python **3.11.9** installed — Python **3.12** required (CD1), install before Phase 1.
- `uv` not installed — install before Phase 1.
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
| 2026-10-07 | Crisis resources cover India, Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Myanmar, China, South Korea, Japan, Thailand, Maldives, Vietnam, Hong Kong, Taiwan, Cambodia, Malaysia, Singapore, Russia; country chosen by the user (optional), never inferred | Target user regions; consistent with no-nationality inference | Single configured region; locale/IP inference |
| 2026-10-07 | Assistant config files excluded via `.git/info/exclude` instead of `.gitignore` | Keeps them out of git without naming them in the repository | Listing them in `.gitignore` |
| 2026-10-07 | Git: commits authored as Smriti; no assistant attribution anywhere; assistant config files git-ignored; Conventional Commits; one branch per phase | Authorship and repository hygiene | — |

---

## Open items / questions for Smriti

1. **Region list** — confirm it is complete (the list ended with a trailing comma) and that "Korea" means South Korea.
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
| Real-model tone (companion, guard, bias quality) | Not verified here |
| Qwen3.5 thinking-disable mechanism and sampling settings | To be re-verified against the current model card in Phase 1 |
| Model licences (Qwen3.5, Gemma 4, Phi-4-mini) | To be re-verified in Phase 1 |
| PHQ-9 / GAD-7 item wording | To be verified against the published source in Phase 3 |
| Crisis resource numbers | To be verified in Phase 2 |
| Post-crisis flag after an app restart with storage down | Falls back to normal mode (documented, clinician review) |
| English-only; no fine-tuning; WEIRD-data caveat | By design for v1 |

---

## Measured results

_None yet._

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
