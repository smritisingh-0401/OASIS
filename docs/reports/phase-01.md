# Phase 1 — Core chat loop

**Report topic:** architecture skeleton and failure-first design — process isolation, deadlines, templated fallback, repository contract.

## 1. Design

Phase 1 builds the complete request path of the v2 architecture with every decision component present as a **hook**, so later phases fill in behaviour without changing the flow:

| Stage | Phase 1 implementation | Replaced / extended in |
|---|---|---|
| Safety gate | `StubSafetyGate` behind `check_fail_closed`; startup tripwire | Phase 2 |
| Load state | `Repository.get_session` + `recent_turns` | Phases 3, 8, 10 |
| Planner | `plan_turn` → companion (pass-through) | Phases 3–6 |
| Generation | `build_messages` → `BoundedLLM` → `FakeLLM` / `LlamaServerClient` → `clean_reply` | Phases 4–7 |
| Guard | `pass_guard` hook with the full retry/fallback flow already wired | Phase 7 |
| Record | Two turn rows; trace JSON (no text) on the assistant row | Phases 8–9 |

Key mechanisms:

- **Ordering as a safety property.** `ChatEngine.handle_turn` calls the safety gate before any repository method. A crisis verdict returns the fixed handoff immediately: no storage, planning or LLM call. Because session lookup happens *after* safety, a crisis message is answered even from an unknown session.
- **Fail closed vs. fail soft.** The safety wrapper converts any exception into a crisis verdict (fail closed). Every other stage fails soft: a storage error gives a stateless reply marked `persisted=false`; a planner error gives a templated reply; an LLM error gives a templated reply; an unexpected exception is caught at the API boundary and still produces a templated reply with HTTP 200.
- **Deadline propagation.** The engine fixes a deadline (90% of `request_timeout_s`, the rest reserved for recording) and gives each LLM call only the remaining budget. The API wraps the engine in a hard timeout as a last line of defence. A hung model therefore cannot hang a request.
- **Bounded queue.** `BoundedLLM` allows `llm_max_concurrency` in-flight generations plus `llm_queue_limit` waiters; beyond that it fails fast with `busy`, which maps to a "please send that again" template rather than a long wait.
- **No reasoning text reaches the user.** The llama-server client sends `chat_template_kwargs.enable_thinking=false`, ignores any `reasoning_content` field, and every draft from every client passes `clean_reply`, which removes complete `<think>` blocks, anything before an orphan `</think>`, and anything after an unterminated `<think>`. Output that is empty after cleaning is an LLM failure.
- **Repository contract.** One `Repository` protocol; `MemoryRepository` and `SQLiteRepository` pass the same parametrised contract suite, including cross-user isolation. SQLite runs in WAL mode with `foreign_keys`, `secure_delete`, a busy timeout, STRICT tables and CHECK constraints, and numbered migrations recorded in `schema_migrations`.
- **Privacy envelope (Phase 1 part).** Session token: 256-bit, sent only in `X-OASIS-Session`, stored only as a SHA-256 hash. Logs carry exception *types* only; the per-turn trace carries IDs, timings and codes only. Validation errors return field names, never the submitted text. Every response carries `Cache-Control: no-store`, a strict CSP and the other security headers.
- **UI.** Plain HTML/CSS/JS, no external requests, `textContent` only. The "Need help now?" card is a native `<details>` element, so it opens with no JavaScript and no server.

## 2. Evaluation method

- **Tests first** for the critical logic: safety stub/tripwire, LLM failure mapping and reasoning stripping, queue limit, repository contract, engine ordering and every fallback, API contract, log privacy, fault injection.
- **Property-based tests** (Hypothesis) for `clean_reply`: for arbitrary text, the output never contains a think tag, and a marker placed inside a think block never appears in the output.
- **Mutation spot-check:** five critical behaviours were deliberately broken one at a time to confirm the suite detects each.
- **Live check** in a browser against the running server.
- **DB micro-benchmark** (`scripts/db_benchmark.py`).

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass: ruff lint, ruff format, mypy strict, import-linter (5/5 contracts kept), bandit, pip-audit (no known vulnerabilities), pytest + coverage, critical-package coverage |
| Tests | 121 passed, 0 skipped |
| Coverage | 98.73% overall (branch coverage on); `oasis.safety` 100% |
| Mutation spot-check | 5/5 caught: storage read moved before safety; safety failing open; unterminated `<think>` not removed; queue limit off by one; user scoping removed from the SQLite read |
| Live check | Multi-turn chat via Enter and Send; history restored after page reload **and after server restart**; help card opens with the server stopped; offline message shown and the unsent text returned to the input; `/health` reports llm/storage up; security headers present; no message text in server logs |
| SQLite benchmark (dev machine, 1 000 turns) | Turn pair write p50 0.55 ms / p95 0.94 ms / p99 1.80 ms; last-6-turns read p50 0.22 ms / p95 0.40 ms / p99 0.50 ms |

The storage cost per turn (~1 ms) is negligible against the 150 ms non-LLM budget, which supports the SQLite decision.

## 4. Known limits

- **Not verified here:** anything that needs the real model — `scripts/model_smoke_test.py` and `scripts/model_bakeoff.py` are ready to run on the reference laptop. The thinking-disable flag and sampling values follow the model-card guidance gathered mid-2026 and must be re-verified on the first real run; the llama.cpp build is pinned from that run.
- **Safety is a stub.** The tripwire refuses to start without `OASIS_DEV_MODE=1`, and the UI shows a development banner. Nobody may use the bot until Phase 2 is approved.
- **Prompt budget** uses a character estimate (~3.5 characters per token); the token-exact budget arrives with real prompts.
- **Body-size limit** trusts `Content-Length`; chunked bodies rely on server limits plus the 2 000-character schema cap.
- **Deferred by design:** `/history` pagination (`before`), per-session ephemeral mode (Phase 10), debug view (Phase 9), templates in the content library (Phase 2).
