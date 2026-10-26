# Phase 13 — Engagement and reliability

**Goal.** Prove graceful degradation and measure responsiveness (PRD L7, L9, L10).

**Report topic.** Reliability engineering for acute-moment use.

## 1. Design

| Component | File | Role |
|---|---|---|
| Fault-injection matrix | `tests/fault_injection/test_matrix.py` | One test per row of design §16, over HTTP. Each checks the reply, the request timeout and the trace code. Model failures use the real llama-server client against a local stub server |
| Continuity | `tests/integration/test_continuity.py` | Restart OASIS between turns: an open questionnaire, an exercise step, post-crisis mode and the chosen style carry on; an unsaved conversation does not |
| Saved-conversation expiry | `storage/*.idle_users`, `api/app.py expire_idle`, notice version 3 | A saved conversation with no message for 90 days is deleted at startup and once a day, through the same erasure as the Delete button (Smriti, 2026-10-26) |
| Queue and timeout | `llm/client.py BoundedLLM`, `core/engine.py` | The generation timeout starts once the model is free; the wait is bounded by the request deadline |
| Load and latency | `scripts/load_test.py`, `docs/reports/reliability.md` | Latency of everything except the model; concurrent sessions against the real model; what sentence streaming would gain |
| Usability | `docs/usability_checklist.md`, `scripts/contrast_check.py`, `tests/unit/test_contrast.py`, `tests/unit/test_web_ui.py` | Nielsen's heuristics and WCAG 2.2 AA in the browser; contrast checked from the stylesheet in CI |

**Fault-injection matrix.** Every row of design §16 is now a test. The model rows go through `LlamaServerClient` to a real socket: no listener, a stall, a stream of single bytes, empty content, think-only, HTTP 500, malformed JSON and no choices. The "trickle" row matters. Each byte arrives inside the read timeout, so only the engine's generation deadline ends the request. A fake model raising an exception would never show that. The storage rows hold a real SQLite write lock from a second connection. A healthy stub is the control row, and two combined rows add a stalled model with a locked database, and a stalled model with dead storage.

**What the matrix found.**
1. **A refused model connection was reported as a timeout.** On Windows a connection to a closed port is retried for about two seconds, so the 1 s connect timeout fires first. The reply was right (the templated reply); the trace code was wrong. `httpx.ConnectTimeout` is now `llm.down` too.
2. **Crisis bookkeeping could wait forever.** The audit entry, post-crisis flag and placeholder are written after the handoff is sent. With storage that never answers, that task never ended. It is now bounded by the request timeout. The handoff itself was never delayed.

**What the load test found.** With one model slot, the first run timed out most requests from two sessions at once, every one at 20 s, which is the generation timeout. A message queued behind another reply spent its budget waiting for the model. The generation timeout now starts when the model is free, and the wait is bounded by the request deadline (30 s). On the busy desktop, two sessions at once went from 5/6 served to 6/6, three from 3/9 to 8/9, and four from 2/12 to 9/12. Cancelling a request also stops llama-server's generation; checked with a 2 s client against a 400-token request.

**Memory decides latency on this laptop.** llama-server commits 4.1 GB. The first runs had 0.2 GB of 5.8 GB free, with Chrome (2.5 GB), a desktop assistant app (2.2 GB) and WebView (1.3 GB) open, and Windows kept only 0.0-0.25 GB of llama-server in RAM. The reported runs close Chrome (Smriti). With Chrome closed, Windows still kept only 0.25 GB of llama-server in RAM, with about 0.5 GB free: a 6 GB laptop cannot keep this model resident next to a desktop app. A cold model (just after the apps were closed) took 20 s per reply for a single session; warm, 8.8 s. The same 5 s replies seen in earlier phases came back once the model was warm and prompts were short (the streaming run).

**Usability review** (`docs/usability_checklist.md`). Five fixes, each with a test:
- **Help card off-screen on phones.** At 375 px the help card ran 55 px off the left edge, cutting off the start of every crisis line. It now spans the header.
- **Enter while a reply was pending.** It sent a second message, which was answered without the first in its history (a Phase 11 known limit). Enter now waits.
- **Escape on the help card.** It did not close the card.
- **Contrast.** Seven text colours fell below AA over the darkest orb under the clear chat glass (Phase 11).
- **Target size.** "Why this reply?" and the short phone numbers were under 24 px.

**Departures from the phase plan.**
- **Detector errors.** They have no separate trace code: signals are computed inside the planner, so a detector bug is `planner.error`. Per-detector isolation would add code for a failure with no known cause (design §16.1).
- **Streaming.** It is measured, not built (PRD §7: no streaming in v1).
- **Report files.** `reliability.md` holds the generated measurements; this report holds the rest.

## 2. Evaluation method

- **Matrix:** `pytest tests/fault_injection` (also in CI); per-row time limits, with the request timeout at 5 s in tests.
- **Continuity:** a SQLite file shared by two app instances; expiry by back-dating `last_seen_at` in the file, then restarting.
- **Load:** `uv run python scripts/load_test.py load`: 1, 2, 3, 4, 6 and 8 sessions at once, 3 messages each, over HTTP through the whole app with a fresh SQLite file, against llama-server (Qwen3.5-4B Q4_K_M). Served means the model's reply, or a guard fallback, inside the timeout.
- **Everything except the model:** `scripts/load_test.py profile`: 600 requests, fake model, SQLite on disk.
- **Streaming:** `scripts/load_test.py stream`: 20 messages through the full pipeline with the model streaming; first token, first sentence and whole reply timed; first drafts the guard rejected counted.
- **Usability:** browser (desktop and 375 px), keyboard only, server stopped; contrast script; DOM checks for names, headings, live regions and target sizes.
- **Mutation spot-check:** deliberate faults in the new code, each run against the matrix, continuity, contract and UI tests.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass (ruff, format, mypy strict, import-linter, bandit, pip-audit, pytest with coverage, critical coverage), on mains power. On battery the explanation latency test (20 ms) measured 33-39 ms, on `main` too |
| Tests / coverage | 1619 passed, 0 skipped (1536 at the Phase 12 merge); 98.42% overall; `oasis.safety` 97.7%, `oasis.assessment` 97.8%, `oasis.router` 100% |
| Done-when: fault matrix passes, every request answered within the timeout | **Yes**: every row of design §16, plus the healthy control and two combined rows, in CI (`reliability.md` §4) |
| Done-when: session continuity | **Yes**, across a restart: an open questionnaire (item 3 → 4), an exercise step, post-crisis mode and the chosen style carry on; an unsaved conversation is gone (401). A saved conversation unused for 91 days is deleted at startup, 89 days is kept |
| Done-when: load and latency measured on the reference laptop | **Yes** (`reliability.md`). Everything except the model: 10 / 12 / 18 ms (p50 / p95 / p99), target 150 ms p95. Real model, quiet machine: **3 sessions at once** with every request served when the model is warm (slowest 26 s), 2 when cold. One session: 8.8 s median warm, 20 s cold |
| Queue fix (busy desktop) | Served with 2 / 3 / 4 sessions at once: 5/6 → 6/6, 3/9 → 8/9, 2/12 → 9/12 |
| Memory | llama-server commits 4.1 GB; Windows kept 0.25 GB of it in RAM with 0.4-0.6 GB of 5.8 GB free. The app: 23-64 MB |
| Streaming (measured, not built) | First sentence 2.7 s against the whole reply 5.1 s (median): 2.0 s sooner. 4 of 20 first drafts were rejected by the guard and would already have been on screen. **Not worth building in v1** |
| Done-when: usability checklist passes | **Yes** (`docs/usability_checklist.md`): 10 Nielsen heuristics and 9 WCAG 2.2 AA checks, after five fixes. Contrast 33/33 pairs (26/33 before) |
| Mutation spot-check | 14/15 at first. Missed: the engine no longer wrapping a bare model client in `BoundedLLM`, because the app always passed one already wrapped. The app now passes the bare client, so the matrix exercises the engine's own wrapping (refactor, no new test). **Now 15/15** |

## 4. Known limits

- **Memory, not CPU, sets the speed on the reference laptop.** With 5.8 GB and a desktop app open, the 4.1 GB model is never resident; a cold reply takes about 20 s. Recommend 8 GB or more, or running OASIS with no other large app open (Phase 14 deployment notes).
- **The queue is deeper than the deadline allows.** One warm reply takes about 9 s, so a fourth waiting message cannot finish inside 27 s; at 4 or more sessions most extra messages wait and then get the templated reply instead of "busy" at once. A queue limit of 2 would fail faster. Not changed here: it needs a second load run to confirm (Phase 14).
- **Three sessions at once means up to 26 s waits.** That is inside the timeout, not a good experience. On one laptop the usual case is one person at a time: a 9 s median reply when the model is warm.
- **Small samples.** 3 messages per session per level, 20 messages for streaming, one run each; the cold and warm runs differ by 2×. Treat the limits as orders of magnitude.
- **Usability without people.** No participants (O4: ethics approval first) and no screen-reader walkthrough; names, roles and live regions were checked in the DOM. Contrast is computed from the stylesheet without the blur.
- **Detector errors have no code of their own** (`planner.error`, design §16.1).
