# OASIS

**A lightweight, explainable, safety-first mental health support chatbot.**

OASIS offers evidence-based conversational support (CBT, DBT, mindfulness), standard screening (PHQ-9, GAD-7) when the conversation warrants it, and a warm listening mode — while staying transparent about *why* it responds the way it does. A rule-based decision plane plans each reply; a small local language model only phrases it. Safety checks run before the model, and every failure falls back to a vetted templated reply.

> ### Important
> OASIS is a **subclinical support and screening tool, not a diagnostic system and not an emergency service.** It complements, and never replaces, a qualified clinician.
> **If you are in danger or thinking about ending your life, contact your local emergency number or a crisis line now.**

## Why

A review of 97 studies (16,620 participants) on mental health chatbots identified ten recurring limitations: black-box reasoning, repetitive or sycophantic replies, WEIRD-dominated data, cost and access barriers, unclear privacy, lack of user control, implementation cost, output bias, low engagement, and glitches at critical moments. OASIS addresses each with a testable feature — see [docs/PRD.md](docs/PRD.md).

## Key properties

- **Safety first** — pure-Python crisis detection runs before anything else; crisis handoff makes zero model calls. "Need help now?" works with no script and no server, and opens the country chosen in Settings, or else the computer's time zone, first.
- **Explainable** — every reply has a "Why this reply?" panel: the signals that drove its strategy, with exact SHAP values and the router's weighted sum.
- **Private** — nothing leaves the computer. A data notice comes first; each conversation is either saved in a local file or kept in memory only, and Settings exports or deletes everything (deleted text is overwritten on disk). No name, email or phone number.
- **Your style** — Settings sets how direct and how formal replies are; it changes the wording only, never what OASIS does, and is never guessed from how you write.
- **Free to run** — quantised open model on a CPU laptop; no paid API.

## Install

> Development only. The safety content, clinical wording and data notice await clinician and legal review ([docs/clinical_review.md](docs/clinical_review.md)). Use test messages only.

### What you need

| | Minimum | Measured on |
|---|---|---|
| Computer | Any 64-bit Windows, macOS or Linux laptop; no GPU | AMD Ryzen 5 5500U (6 cores), Windows 11 |
| Memory | 8 GB RAM for the real model; 6 GB works with no other large app open, but slowly | 5.8 GB |
| Disk | 3.2 GB: model 2.7 GB, Python and packages about 0.4 GB | |
| Network | Only to install; OASIS makes no network request while it runs | |
| Cost | Nothing: free software and an open model, no account, no paid API | |

Measured cost and speed: [docs/reports/phase-14.md](docs/reports/phase-14.md).

### 1. Install the tools

[uv](https://docs.astral.sh/uv/) installs Python 3.12 and every package. Install [Git](https://git-scm.com/downloads) too if it is missing.

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards so `uv` is on the path.

### 2. Get OASIS and run it with the stand-in model

```bash
git clone https://github.com/smritisingh-0401/OASIS.git
```

```bash
cd OASIS
```

```bash
uv sync
```

```bash
cp .env.example .env
```

```bash
uv run uvicorn oasis.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000, read the data notice and choose **Save on this computer** or **Start without saving**. With `OASIS_LLM_BACKEND=fake` (the `.env.example` default), replies come from a deterministic stand-in model, so everything except the wording of replies works without the model.

Saved conversations live in `data/oasis.db` (`OASIS_DB_PATH`); the browser keeps only the session key, so anyone using the same browser can reopen a saved conversation. Unsaved conversations stay in memory and are forgotten after two hours idle or on restart. Export and delete are under the gear icon (Settings).

### 3. Add the real model

Install llama.cpp (built and tested with build 11552, commit `23b0202a1`):

```bash
winget install ggml.llamacpp
```

On macOS or Linux, `brew install llama.cpp` instead. Then start the model server in its own terminal. The first start downloads the model (2.7 GB) from Hugging Face; later starts use the copy on disk:

```bash
llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096 -np 1 -ngl 0 --host 127.0.0.1 --port 8080
```

`-ngl 0` keeps the model on the CPU; integrated graphics on small laptops run out of memory loading it. In `.env`, set `OASIS_LLM_BACKEND=llama_server`, restart OASIS, and check the model with:

```bash
uv run python scripts/model_smoke_test.py
```

A reply takes about 5-10 s with the model warm, and about 20 s for the first one after the model has been idle or other apps have pushed it out of memory. Close large apps such as a web browser with many tabs for the best speed.

### Developer checks

Run every check (lint, types, import rules, security scan, dependency audit, tests with coverage):

```bash
uv run python scripts/verify.py
```

Compare candidate models with `scripts/model_bakeoff.py`. `scripts/bias_eval.py` runs the bias evaluation (`--fake` for the decision plane only). `scripts/load_test.py` measures speed and concurrency. `scripts/licences.py` regenerates [docs/licences.md](docs/licences.md); `scripts/export_diagrams.py` exports the diagrams for reports (needs Node.js).

## Limitations

- **Not a clinical tool.** No diagnosis, no medication advice, not an emergency service. The safety patterns, crisis policy and clinical wording await review by a qualified clinician ([docs/clinical_review.md](docs/clinical_review.md)); the data notice awaits legal review.
- **English only.** Safety patterns, questionnaires, exercises and prompts are English. Crisis detection is tested on English varieties (British, AAVE, Indian English, Nigerian Pidgin, Hinglish, Spanglish, Taglish), but a crisis written in another language is not detected.
- **No fine-tuning.** OASIS uses an off-the-shelf model. Its style setting changes how replies are framed, not what the model learnt.
- **WEIRD-data caveat.** The techniques, questionnaires, detector word lists and the model's training data come mostly from Western, educated, industrialised, rich, democratic populations. The style setting adjusts directness and formality only, and the bias evaluation checks that decisions do not change with dialect, names or identity ([docs/reports/bias_eval.md](docs/reports/bias_eval.md)); neither makes OASIS culturally validated anywhere.
- **One person at a time.** It is built for one person on their own laptop. On the reference laptop two or three people at once still get every reply, but slowly; beyond that, messages time out and get a templated reply ([docs/reports/phase-14.md](docs/reports/phase-14.md)).
- **Crisis numbers** were verified in October 2026 and need re-checking before any real use.
- **Saved conversations** are as private as the computer: anyone using the same browser can reopen one, and full-disk encryption is recommended.

## Project status

| Phase | Status |
|---|---|
| Step A — project documents | Approved |
| 1 — Core chat loop | Approved |
| 2 — Safety layer | Approved |
| 3 — Assessment (PHQ-9 / GAD-7) | Approved |
| 4 — Therapy router | Approved |
| 5 — Psychoeducation | Approved |
| 6 — Companion mode | Approved |
| 7 — Hypercompliance guard | Approved |
| 8 — Sentiment tracking | Approved |
| 9 — Explainability | Approved |
| 10 — Privacy and autonomy | Approved ([report](docs/reports/phase-10.md)) |
| 11 — Cultural adaptation | Approved ([report](docs/reports/phase-11.md)) |
| 12 — Bias evaluation | Approved ([report](docs/reports/phase-12.md)) |
| 13 — Engagement and reliability | Approved ([report](docs/reports/phase-13.md)) |
| 14 — Cost and access | Approved ([report](docs/reports/phase-14.md)) |

See [docs/phases.md](docs/phases.md) and [docs/memory.md](docs/memory.md).

## Documentation

| Document | Purpose |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/architecture.md](docs/architecture.md) | Architecture, data flow, stack, storage |
| [docs/design.md](docs/design.md) | Algorithms, data model, API, prompts, UI |
| [docs/rules.md](docs/rules.md) | Engineering rules |
| [docs/phases.md](docs/phases.md) | Build plan |
| [docs/memory.md](docs/memory.md) | Project memory and decision log |
| [docs/clinical_review.md](docs/clinical_review.md) | Items awaiting clinician review |
| [docs/reports/](docs/reports/) | Per-phase reports: design, evaluation, measured results, known limits |
| [docs/licences.md](docs/licences.md) | Licences of everything OASIS runs |

## Licence

MIT ([LICENSE](LICENSE)). The licence covers the code; it does not make OASIS fit for clinical use (see Limitations).
