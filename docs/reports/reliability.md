# Reliability measurements (Phase 13)

Measured on the reference laptop (decision 2026-10-26): AMD Ryzen 5 5500U, 6 cores / 12 threads, 5.8 GB RAM, Windows 11. Model Qwen3.5-4B Q4_K_M in llama.cpp `llama-server`. OASIS settings as shipped: one generation at a time (`llm_max_concurrency` 1), at most 4 waiting (`llm_queue_limit`), generation timeout 20 s, request timeout 30 s.

Every request goes over HTTP through the whole app in one process, with a fresh SQLite file per run (`scripts/load_test.py`). The reported runs were made with Chrome closed and nothing else working (Smriti, 2026-10-26); one desktop assistant app (about 2.2 GB) stayed open.

## 1. Everything except the model

`load_test.py profile`: 600 requests, one at a time, fake model, SQLite on disk. Run on 2026-10-26 after every Phase 13 change.

| Measure | p50 / p95 / p99 (ms) |
|---|---|
| Whole request | 10 / 12 / 18 |
| Stage: safety | 0 / 0 / 0 |
| Stage: load_state | 1 / 2 / 2 |
| Stage: plan | 2 / 3 / 3 |
| Stage: generate (fake model) | 0 / 0 / 1 |
| Stage: explain | 1 / 1 / 1 |
| Stage: record | 2 / 4 / 11 |

Target (PRD §6.1): under 150 ms p95 for everything except the model. **Met**, by more than ten times. The model is the whole of the wait.

## 2. Concurrent sessions against the real model

`load_test.py load`: N sessions at once, each sending 3 messages one after another, the way people type. **Served** means the model's reply, or a guard fallback, inside the request timeout; a "busy" reply or a timeout is not served. The limit is the largest N with every request served.

**Reported run: quiet machine, model warm** (llama-server already answering before the run).

| Sessions at once | Requests | Served | Busy | Timed out | Latency p50 / p95 (s) | Slowest (s) | Lowest free RAM (GB) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0 | 0 | 8.8 / 16.7 | 16.7 | 0.57 |
| 2 | 6 | 6 | 0 | 0 | 12.8 / 23.6 | 23.6 | 0.58 |
| 3 | 9 | 9 | 0 | 0 | 21.6 / 26.4 | 26.4 | 0.58 |

**Limit: 3 sessions at once**, with the slowest reply at 26 s, inside the 30 s request timeout but a long wait.

**Quiet machine, model cold** (run straight after the other apps were closed):

| Sessions at once | Requests | Served | Busy | Timed out | Latency p50 / p95 (s) | Slowest (s) | Lowest free RAM (GB) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0 | 0 | 20.1 / 22.3 | 22.3 | 0.42 |
| 2 | 6 | 6 | 0 | 0 | 21.3 / 27.1 | 27.1 | 0.45 |
| 3 | 9 | 8 | 0 | 1 | 23.2 / 27.1 | 27.1 | 0.01 |
| 4 | 12 | 3 | 0 | 9 | 27.1 / 27.1 | 27.1 | 0.44 |
| 6 | 18 | 4 | 3 | 11 | 27.1 / 27.1 | 27.1 | 0.50 |
| 8 | 24 | 7 | 9 | 8 | 22.6 / 27.1 | 27.1 | 0.53 |

Limit: 2. Above it, most requests wait in the queue until the 27 s deadline (0.9 × 30 s) and get the templated reply; "busy" comes only when five requests are already in flight (one generating, four waiting).

**Context, not reported: busy desktop** (Chrome, the desktop assistant app and WebView open, about 0.2 GB free), before and after the queue fix of Phase 13 (the generation timeout now starts when the model is free):

| Sessions at once | Served, before the fix | Served, after the fix |
|---|---|---|
| 1 | 3/3 | 3/3 |
| 2 | 5/6 | 6/6 |
| 3 | 3/9 | 8/9 |
| 4 | 2/12 | 9/12 |
| 6 | 2/18 | 5/18 |
| 8 | 3/24 | 4/24 |

Before the fix, every timeout was at 20 s: a message queued behind another reply spent its generation budget waiting for the model.

**Memory.** llama-server commits 4.10 GB, but Windows kept only 0.24-0.27 GB of it in RAM in every run, with 0.4-0.6 GB of the 5.8 GB free and the desktop assistant app open. The model is paged in as it runs, so a cold model replies in about 20 s and a warm one in about 9 s for a single session. The app itself used 23-64 MB. On this laptop the model cannot stay resident next to a desktop app; 8 GB of RAM or more is the practical minimum (for Phase 14's cost and deployment notes).

## 3. Sentence streaming (measured, not built)

`load_test.py stream`: 20 single messages through the full pipeline, model warm, with the model asked to stream; 24 generations including retries.

| Measure | p50 / p95 (s) |
|---|---|
| First token | 0.8 / 3.8 |
| First sentence complete | 2.7 / 5.8 |
| Whole reply (what the user waits for today) | 5.1 / 8.1 |

Showing the first sentence as soon as it is complete would save **2.0 s** at the median. But the guard rejected **4 of 20** first drafts, and it judges the whole reply (one question, no advice, no sycophancy, thinking-trap echoes). With streaming those drafts would already be on screen before the guard saw them, and then be replaced. **Not worth it in v1** (PRD §7 already rules it out): a 2 s gain against showing text the guard would reject one time in five. The status line covers the wait instead: "OASIS is thinking…", then "Still working — this can take a few seconds on this computer."

## 4. Fault-injection matrix

Every row of design §16 (as built: §16.1) is a test in `tests/fault_injection/test_matrix.py`, run in CI. Each asserts a reply, an answer inside the request timeout, and the trace code.

| Fault | Reply | Trace code |
|---|---|---|
| Model process down (refused or connect timeout) | Templated reply within about 1 s | `llm.down` |
| Model stalls, or trickles one byte at a time | Templated reply at the generation deadline | `llm.timeout` |
| Empty or think-only content | Templated reply | `llm.empty` |
| HTTP 500 | Templated reply | `llm.http_error` |
| Malformed JSON, or no choices | Templated reply | `llm.bad_response` |
| Queue full | "Busy" reply at once | `llm.busy` |
| Waiting for the model | Both queued messages get a generated reply | none |
| Guard rejects twice | Vetted fallback | `guard.fallback` |
| No time left for a retry | Vetted fallback | `guard.no_budget` |
| Database locked | Reply, marked "may not have been saved" | `storage.busy` |
| Database dead | Reply, not saved | `storage.down` |
| Safety gate raises | Crisis handoff, no model call | fail-closed |
| Explanation builder raises | Reply; the panel says no explanation is available | `explain.error` |
| Planner (or a detector) raises | Companion template; a crisis is still handed off | `planner.error` |
| Storage never answers | Templated reply at the request deadline; a crisis is still handed off | `request.deadline` |
| Crisis bookkeeping with storage that never answers | Ends at the request timeout | logged by type |
| Invalid safety content | OASIS refuses to start | `SafetyConfigError` |
| Model stalled and storage dead together | Crisis handoff in under 1 s; an ordinary message refused at once | — |
| Model stalled and database locked together | Templated reply inside the timeout | `llm.timeout`, `storage.busy` |

A healthy stub server is the control row: it gets a generated reply through the same client.

## Reproduce

```bash
uv run python scripts/load_test.py profile
```

```bash
uv run python scripts/load_test.py load --levels 1,2,3,4,6,8
```

```bash
uv run python scripts/load_test.py stream
```

`load` and `stream` need llama-server running (`scripts/model_smoke_test.py`). Close other large apps first, and send one message through OASIS beforehand so the model is warm.
