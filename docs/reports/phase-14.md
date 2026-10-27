# Phase 14 — Cost and access

**Goal.** Anyone can install and run OASIS on a modest laptop; costs are measured and published (PRD L4, L7).

**Report topic.** Cost and access profile of a local-first mental health chatbot.

## 1. Design

| Item | File | Role |
|---|---|---|
| Install guide | `README.md` | What you need, then three steps: tools, OASIS with the stand-in model, the real model. A limitations section |
| Queue limit 4 → 2 | `settings.py`, `architecture.md` §4.1 | A second load run confirmed the Phase 13 known limit (§3.2); Smriti, 2026-10-27 |
| Licences | `scripts/licences.py`, `docs/licences.md` | Every package OASIS needs to run, from each package's own metadata, plus llama.cpp and the model |
| Diagram exports | `scripts/export_diagrams.py`, `docs/images/*-*.svg`, `*.png` | The four Mermaid diagrams as SVG and PNG, rendered by a pinned mermaid-cli (11.17.0, through `npx`) with the Chrome or Edge already installed |

**Install path.** One command each: install uv, `git clone`, `uv sync`, copy `.env`, run. uv brings Python 3.12, so nothing else needs installing for the stand-in model. For the real model, `winget install ggml.llamacpp` (or `brew install llama.cpp`) and one `llama-server -hf …` line that downloads the model on first start.

**What the install check changed in the guide.**
1. **`-ngl 0`.** The winget build of llama.cpp uses Vulkan. On the reference laptop it failed to load the model ("ErrorOutOfDeviceMemory" on the integrated graphics) with 0.3 GB of RAM free. `-ngl 0` keeps the model on the CPU, which is what the cost profile assumes.
2. **`--no-mmproj`.** `-hf` also downloaded and loaded the model's 0.68 GB vision projector (`mmproj-BF16.gguf`). OASIS sends text only, so the flag saves a download and the memory.

**Departures from the phase plan.**
- **PostgreSQL adapter.** Not built (Smriti, 2026-10-27): one person per laptop, one process, one SQLite file to export and delete.
- **Fresh machine.** The check ran on the reference laptop with an empty uv cache, an empty Python folder and a new clone from GitHub, not on a second computer (§4).
- **No new Python dependency.** mermaid-cli is a Node tool run through `npx` at a pinned version, for the docs only; the app and CI never run it.

## 2. Evaluation method

- **Install:** the README commands in order, in an empty folder, with `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` pointing at empty folders and `UV_PYTHON_PREFERENCE=only-managed`, so Python 3.12 and every package were downloaded. Then the app was started, the page checked for its security headers, one message sent through the browser (stand-in model), and `scripts/verify.py` run inside the clone.
- **Real model:** the README's `llama-server` line, then `scripts/model_smoke_test.py`.
- **Queue limit:** `scripts/load_test.py load --levels 1,2,3,4,6,8`, three messages per session, run once with `OASIS_LLM_QUEUE_LIMIT=4` and once with `2`, straight after each other with Chrome and other large apps closed (the desktop assistant app stayed open). Model on the CPU (`-ngl 0`).
- **Licences:** `scripts/licences.py`; the model and llama.cpp from the Hugging Face card and the GitHub repository.

## 3. Results

### 3.1 Install

| Step | Result |
|---|---|
| `git clone` | 15 s |
| `uv sync` (Python 3.12.15 and 88 packages, development tools included, nothing cached) | 295 s; most of it downloading, so it depends on the connection |
| Disk | Packages 352 MB, Python 68 MB, source 4 MB; model 2.74 GB |
| App start, page | 200, with `Cache-Control: no-store`, CSP `default-src 'self'` and the other P6 headers |
| One message (stand-in model, unsaved session) | Reply and "Why this reply?" shown |
| `scripts/verify.py` in the clone | All 8 steps pass; 1619 tests passed, 98% coverage |
| Real model: `llama-server -hf … --no-mmproj -ngl 0` | Model loaded from the Hugging Face cache in 8 s |
| `scripts/model_smoke_test.py` | PASS: 3 replies, 21 / 13 / 11 s (model cold) |

### 3.2 Concurrency: queue limit 4 against 2

One generation at a time; the queue limit is how many more may wait. Served means the model's reply or a guard fallback inside the 30 s request timeout.

| Sessions at once | Requests | Queue 4: served / busy / timed out | Queue 2: served / busy / timed out |
|---|---|---|---|
| 1 | 3 | 1 / 0 / 2 | 3 / 0 / 0 |
| 2 | 6 | 6 / 0 / 0 | 6 / 0 / 0 |
| 3 | 9 | 9 / 0 / 0 | 8 / 0 / 1 |
| 4 | 12 | 8 / 0 / 4 | 8 / 3 / 1 |
| 6 | 18 | 4 / 3 / 11 | 9 / 9 / 0 |
| 8 | 24 | 8 / 9 / 7 | 9 / 15 / 0 |
| **4-8 together** | 54 | **20 / 12 / 22** | **26 / 27 / 1** |

At 4 or more sessions, a queue of 2 served more requests (26 against 20) and timed out 1 instead of 22. The extra messages got "busy, please send that again" at once (median 0.1 s) instead of a templated reply after 27 s. Up to 3 sessions the two are the same within noise. The queue 4 run lost 2 of 3 single-session requests while the model was being paged in (free RAM touched 0.00 GB), so its first row is a cold start, not a queue effect. The default is now 2.

Full tables, with latency and memory per level: §5.

### 3.3 Cost and access profile

| | Measured on the reference laptop (Ryzen 5 5500U, 5.8 GB, Windows 11, CPU only) |
|---|---|
| Money | Nothing to run: no paid API, no account, no cloud. Runtime licences: MIT, BSD, Apache-2.0, MPL-2.0 and PSF only (`docs/licences.md`); model Apache-2.0, llama.cpp MIT |
| Network | Install only (about 0.4 GB of Python and packages, 2.7 GB model). None while running |
| Disk | 3.2 GB in total |
| Memory | llama-server commits 4.1 GB. With 5.8 GB and a desktop app open, Windows kept only 0.24-0.42 GB of it in RAM; the app used 22-51 MB. 8 GB is the practical minimum for the model to stay in memory |
| Everything except the model | 10 / 12 / 18 ms p50 / p95 / p99 (Phase 13) |
| One reply, one person | About 8-9 s median with the model warm; 11-21 s cold |
| People at once | 2 with every message served (both runs), 3 in one of the two; beyond that "busy" at once |
| Energy (estimate, not measured) | At the CPU's 15 W rated power, a 9 s reply is about 0.04 Wh: about 25 000 replies per kWh |

## 4. Known limits

- **Not a second computer.** The install check started from an empty uv cache, an empty Python folder and a new clone, on the same laptop. Git, Node.js, llama.cpp and the model were already there, and the Windows path was the only one run. macOS and Linux commands are the projects' own install lines, not verified here.
- **Small samples.** Three messages per session per level, one run per queue limit. The two runs differ at 1 and 3 sessions by one or two requests; read the limits as orders of magnitude.
- **Memory decides the speed.** On 5.8 GB the model is paged in and out as it runs, so the same laptop gives 8 s or 20 s replies depending on what else is open. 8 GB or more is recommended.
- **CPU only.** `-ngl 0` was needed here. A laptop whose graphics can hold the model may be faster without it; not measured.
- **Energy is an estimate** from rated power, not a meter reading.
- **One person per laptop.** One process; multi-user deployment would need a shared session store (architecture §4) and is out of scope.

## 5. Load runs (generated)

### Queue limit 4

Model qwen3.5-4b-q4_k_m at http://127.0.0.1:8080; 6 cores / 12 threads, 5.8 GB RAM. One generation at a time (`llm_max_concurrency` 1), 4 waiting at most, request timeout 30 s. Each session sends 3 messages one after another.

| Sessions at once | Requests | Served | Busy | Timed out | Guard fallback | Latency p50 / p95 (s) | Slowest (s) | llama-server in RAM / committed (GB) | App RAM (MB) | System RAM free, lowest (GB) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 1 | 0 | 2 | 0 | 20.2 / 20.7 | 20.7 | 0.42 / 4.15 | 22 | 0.00 |
| 2 | 6 | 6 | 0 | 0 | 0 | 12.0 / 27.1 | 27.1 | 0.35 / 4.15 | 24 | 0.40 |
| 3 | 9 | 9 | 0 | 0 | 0 | 22.9 / 27.1 | 27.1 | 0.25 / 4.10 | 23 | 0.46 |
| 4 | 12 | 8 | 0 | 4 | 0 | 24.7 / 27.1 | 27.1 | 0.25 / 4.10 | 23 | 0.55 |
| 6 | 18 | 4 | 3 | 11 | 0 | 27.0 / 27.2 | 27.4 | 0.24 / 4.10 | 24 | 0.43 |
| 8 | 24 | 8 | 9 | 7 | 0 | 19.7 / 27.1 | 27.2 | 0.24 / 4.10 | 49 | 0.54 |

**Largest number of sessions at once with every request served: 3.**

### Queue limit 2

Model qwen3.5-4b-q4_k_m at http://127.0.0.1:8080; 6 cores / 12 threads, 5.8 GB RAM. One generation at a time (`llm_max_concurrency` 1), 2 waiting at most, request timeout 30 s. Each session sends 3 messages one after another.

| Sessions at once | Requests | Served | Busy | Timed out | Guard fallback | Latency p50 / p95 (s) | Slowest (s) | llama-server in RAM / committed (GB) | App RAM (MB) | System RAM free, lowest (GB) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0 | 0 | 0 | 8.2 / 16.4 | 16.4 | 0.24 / 4.10 | 51 | 0.49 |
| 2 | 6 | 6 | 0 | 0 | 0 | 12.0 / 27.1 | 27.1 | 0.25 / 4.10 | 35 | 0.59 |
| 3 | 9 | 8 | 0 | 1 | 0 | 21.8 / 27.1 | 27.1 | 0.25 / 4.10 | 36 | 0.43 |
| 4 | 12 | 8 | 3 | 1 | 0 | 19.5 / 24.3 | 27.0 | 0.25 / 4.10 | 36 | 0.42 |
| 6 | 18 | 9 | 9 | 0 | 1 | 0.1 / 25.0 | 25.2 | 0.24 / 4.10 | 30 | 0.16 |
| 8 | 24 | 9 | 15 | 0 | 1 | 0.1 / 23.9 | 26.9 | 0.25 / 4.10 | 49 | 0.24 |

**Largest number of sessions at once with every request served: 2.**
