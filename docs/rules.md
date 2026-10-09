# OASIS — Engineering Rules

These rules apply to every phase of the build. They are binding: a change that breaks a rule is not merged. To change a rule, edit this file first and add a dated entry to the decision log in [memory.md](memory.md).

**Start of every working session:** read [memory.md](memory.md) and this file, then continue from the current status.

---

## 1. Safety rules

| ID | Rule |
|---|---|
| S1 | **Safety runs first.** Every user message passes `oasis.safety` before any storage read, planning, prompt building or LLM call. |
| S2 | **Safety runs before storage.** A storage failure must never block or delay the crisis handoff. The audit entry is written *after* the reply is built, in saved mode only, and its failure is swallowed (logged without content). |
| S3 | **Zero LLM calls on crisis.** The handoff path never touches `oasis.llm`. A test injects a `FakeLLM` that fails the test if called. |
| S4 | **No routing, companion or guard logic on crisis.** The handoff reply is fixed text plus verified resources. |
| S5 | **Fails closed.** Any exception inside the safety layer produces a crisis verdict. Invalid or missing pattern files stop the app at startup. |
| S6 | **Never suppressed by negation.** "I'm not going to kill myself" still triggers. The only false-positive reduction is a short allow-list of unambiguous idioms, each with its own test. |
| S7 | **Add-only classifier.** An optional classifier may raise alerts but never clear a rule-based match. (No classifier in v1.) |
| S8 | **Pure Python, isolated.** `oasis.safety` imports nothing from `llm`, `storage`, `api`, `core`, or any network/database module (import-linter + AST test). |
| S9 | **Changed only with tests and review.** Any change to patterns, allow-list, handoff text, resources or post-crisis policy requires: new/updated tests, a passing held-out recall run, and an entry in [clinical_review.md](clinical_review.md). |
| S10 | **Post-crisis policy (provisional).** Every later message still passes the gate first; the bot stays in minimal supportive mode until the user explicitly says they want to continue. |
| S11 | **Item-9 escalation.** Any PHQ-9 item-9 answer ≥ 1 triggers the crisis protocol regardless of total. |
| S12 | **Static help always works.** The "Need help now?" button shows resources from content inlined in the page; it makes no network request. |
| S13 | **Tripwire.** Until Phase 2 is approved, the app refuses to start with the safety stub unless `OASIS_DEV_MODE=1`, and the UI shows a development banner. (Retired in Phase 2 with the stub; the prototype banner was removed from the UI at the owner's request on 2026-10-09.) |
| S14 | **Resources verified.** Crisis numbers are verified against the official source at build time; the verification date and source URL are stored next to each entry. |

## 2. Clinical rules

| ID | Rule |
|---|---|
| CL1 | PHQ-9 and GAD-7 only, with standard published items, answer options and scoring bands. No substitutions, no invented items or thresholds. |
| CL2 | No LLM paraphrase of items and no LLM scoring. Items are fixed text with fixed 0–3 buttons. |
| CL3 | Incomplete questionnaires are never scored. The functional-difficulty item is recorded, not scored. |
| CL4 | No diagnosis and no medication advice in any reply — enforced by the guard and by templates review. |
| CL5 | Every result is shown with the statement that this is a screening tool, not a diagnosis. |
| CL6 | Any clinical logic beyond standard scoring (weights, thresholds, cooldowns, scripts, psychoeducation text, question bank) is tagged `review_status: needs_clinician_review` in its data file and listed in [clinical_review.md](clinical_review.md). |
| CL7 | v1 technique scripts are low-risk skills only — no cold exposure, breath-holding or intense exercise. |

## 3. Privacy rules

| ID | Rule |
|---|---|
| P1 | **Logs never contain message text or session IDs.** A logging filter scrubs known fields; a test greps captured logs for a marker message and a known session ID. |
| P2 | **The per-turn trace never holds user text** — only IDs, scores, modes, timings and reason codes. |
| P3 | **Session ID travels in a header** (`X-OASIS-Session`), never in a URL or query string. |
| P4 | **Ephemeral mode writes nothing to disk** — no DB rows, no temp files, no log lines with content (filesystem-diff test). |
| P5 | **Every query is scoped to the user.** Every repository method takes `user_id`; a contract test proves cross-user isolation. |
| P6 | **Security headers on every response:** `Cache-Control: no-store`, `Content-Security-Policy: default-src 'self'` (no inline script), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy` denying camera/mic/geolocation. |
| P7 | **No real user data before Phase 10** (privacy controls). Development uses synthetic text. |
| P8 | **Pseudonymous accounts only.** No email, phone or real name fields. |
| P9 | **Export and delete are complete.** Export contains every stored record for the user; delete leaves zero rows (schema-crawl test) and no marker bytes in `.db`/`-wal`. |

## 4. Code rules

| ID | Rule |
|---|---|
| CD1 | Python 3.12. Type hints everywhere; `mypy --strict` clean; `ruff check` and `ruff format --check` clean. |
| CD2 | Decision-plane code is small pure functions over frozen dataclasses / Pydantic models. No I/O inside the decision plane. |
| CD3 | No global mutable state. Dependencies are passed in (constructor injection); FastAPI wiring happens in one `create_app(settings)` factory. |
| CD4 | Configuration through one typed settings object (`pydantic-settings`, `OASIS_` env prefix). No magic constants scattered in code; thresholds and weights live in versioned YAML. |
| CD5 | No secrets in code or in the repo. `.env` is git-ignored; `.env.example` documents variables. |
| CD6 | Dependencies pinned via the `uv` lockfile. No new dependency without a one-line reason in the PR and a decision-log entry. |
| CD7 | Errors are typed (`LLMFailure`, `StorageUnavailable`, `StorageBusy`, …). No bare `except:`; broad `except Exception` only at documented fail-soft/fail-closed boundaries, each with a comment explaining why. |
| CD8 | Comments explain *why*, in the voice of a normal engineering project. |
| CD9 | `bandit` clean (no `# nosec` without a justification comment); `pip-audit` clean or each finding documented. |
| CD10 | Module dependency rules in [architecture.md §8](architecture.md) are enforced by import-linter. |

## 5. Testing rules

| ID | Rule |
|---|---|
| T1 | **Tests first** for safety, assessment, router, guard and privacy: the failing test is written and committed (or shown) before the implementation. |
| T2 | **Hypothesis property tests** for scoring (band monotonicity, total = sum of items, totals within range, incomplete never scored) and for router contribution additivity. |
| T3 | **Contract tests** for every storage backend: one parametrised suite run against `MemoryRepository` and `SQLiteRepository` (and Postgres if added). |
| T4 | **Fault-injection tests:** LLM down/slow/empty/think-only, queue full, guard rejects twice, DB locked/unavailable, explainability error, safety internal error. Each asserts a reply within the timeout and the correct fallback. |
| T5 | **Coverage thresholds** (configured in `pyproject.toml`, enforced by CI): ≥ 95% line+branch on `oasis.safety`, `oasis.assessment`, `oasis.router`; ≥ 85% overall. |
| T6 | **Never mark a phase done** with a failing, skipped or `xfail` test. Tests that need the real model live in `scripts/` and are labelled "not verified here", not skipped in the suite. |
| T7 | Tests are deterministic: fixed seeds, `FakeLLM`, frozen clock where time matters. No network in the test suite. |
| T8 | Every safety pattern and every allow-list idiom has at least one named test. Held-out recall phrases are never used to tune patterns. |
| T9 | `make verify` runs: ruff, ruff format check, mypy, import-linter, bandit, pip-audit, pytest with coverage. Its real output is shown at the end of every phase. |

## 6. Front-end rules

| ID | Rule |
|---|---|
| F1 | No external requests: no CDNs, externally hosted web fonts, analytics or third-party scripts. Fonts may only be self-hosted from the app's own origin (`font-src 'self'`). CSP enforces it. |
| F2 | The static "Need help now?" button works with the backend down (content inlined in HTML). |
| F3 | Accessible: full keyboard operation, visible focus, WCAG 2.2 AA contrast, ARIA labels, `aria-live="polite"` for new messages, respects `prefers-reduced-motion`. |
| F4 | No `innerHTML` with any server or user text — `textContent` only (prevents XSS). |
| F5 | No browser storage of message content. `sessionStorage` may hold the session ID only. |
| F6 | Calm, text-only design; no gamification, streaks or guilt-inducing prompts. |

## 7. Git rules

| ID | Rule |
|---|---|
| G1 | All commits authored as Smriti. Before the first commit, ask for the git name and email and set them with `git config user.name` / `git config user.email` **in this repository**. |
| G2 | **No AI attribution anywhere in the repository or its history.** No `Co-Authored-By` trailers, no "Generated with…" lines, no tool names or links in commit messages, PR descriptions, code comments, docstrings, docs, README or changelog. Automatic attribution is disabled in tool settings and checked before the first commit; attribution lines are not added even if a default suggests them. |
| G3 | Assistant-specific config files and folders stay out of git. They are excluded through the local, uncommitted `.git/info/exclude`, so their names do not appear anywhere in the repository. Before each commit, `git status` is checked to confirm none are staged. Project knowledge goes in `docs/`. |
| G4 | Comments, docs and messages read like a normal engineering project — no "as requested", "here's the updated version", "I've added". |
| G5 | Conventional Commits (`feat(safety): …`, `test(assessment): …`, `docs: …`, `chore: …`, `fix: …`); small, focused commits. |
| G6 | One branch per phase (`phase-01-core-chat-loop`, `phase-02-safety-layer`, …), merged to `main` only after Smriti's approval. |
| G7 | Before every push: run `git log --format='%an %ae%n%B'` and an attribution-string grep over the tree, and show the clean result. |
| G8 | Never force-push or rewrite `main` without asking. |

Attribution grep used for G7:

```bash
git grep -n -i -E "co-authored-by|generated with|claude|anthropic|chatgpt|copilot|ai-generated" -- . ':!docs/rules.md' ':!.gitignore'
```

(`docs/rules.md` and `.gitignore` are excluded because they name the strings they forbid or ignore. Broader terms such as "OpenAI" or "cursor" are not in the pattern because they have legitimate technical meanings here — llama-server's OpenAI-compatible endpoint, the CSS `cursor` property.)

## 8. Process rules

| ID | Rule |
|---|---|
| PR1 | Each phase follows the loop: goal + done-when → plan → tests first → implement → `make verify` with real output → code walkthrough → report write-up → update `memory.md` → commit. |
| PR2 | Never start the next phase until the current one is approved. |
| PR3 | Decisions in this prompt are not re-opened. A real problem (bug, contradiction, security issue) is raised as a short note with evidence and waits for an answer. |
| PR4 | Anything needing the real model or the reference laptop is a one-command script and stays "not verified here" until results are reported. |
