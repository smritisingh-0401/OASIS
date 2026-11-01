# OASIS

A lightweight, explainable, safety-first mental health support chatbot that runs on your own laptop.

OASIS offers a warm listening mode, short exercises from CBT, DBT and mindfulness, and the standard PHQ-9 and GAD-7 questionnaires when a conversation calls for them. A rule-based decision plane decides what each reply does, and a small local language model only puts that decision into words. Safety checks run before the model, and every failure falls back to a vetted reply written in advance.

> OASIS is a subclinical support and screening tool. It is not a diagnostic system or an emergency service, and it does not replace a qualified clinician.
> If you are in danger or thinking about ending your life, contact your local emergency number or a crisis line now.

## Why

A review of the literature on mental health chatbots identified ten recurring limitations: opaque reasoning, repetitive or over-agreeable replies, data drawn from narrow (WEIRD) populations, cost and access barriers, unclear privacy, little user control, implementation cost, output bias, low engagement, and faults at critical moments. OASIS addresses each one with a feature that a test can check ([docs/PRD.md](docs/PRD.md)).

## What it does

- Safety first. Pure-Python crisis detection runs before anything else, and the crisis handoff makes no model call. The "Need help now?" card works with no script and no server, and opens first on the country chosen in Settings or the computer's time zone.
- Explainable. The "Why replies" page explains every reply: the signals behind its strategy, with exact SHAP values and the router's weighted sum.
- Private. Nothing leaves the computer. A data notice comes first; each conversation is either saved in a local file or kept in memory only, and Settings exports or deletes everything, overwriting deleted text on disk. OASIS asks for no name, email or phone number.
- Your style. Settings controls how direct and how formal replies are. The setting changes wording only, never what OASIS does, and OASIS never guesses it from how you write.
- Free to run. A quantised open model runs on a laptop processor, with no paid API.

## Install

> For development only. The safety content, clinical wording and data notice await clinician and legal review ([docs/clinical_review.md](docs/clinical_review.md)). Use test messages only.

### Requirements

| | Minimum | Measured on |
|---|---|---|
| Computer | Any 64-bit Windows, macOS or Linux laptop; no GPU | AMD Ryzen 5 5500U (6 cores), Windows 11 |
| Memory | 8 GB RAM for the real model; 6 GB works slowly with no other large app open | 5.8 GB |
| Disk | 3.2 GB: model 2.7 GB, Python and packages about 0.4 GB | |
| Network | Only to install; OASIS makes no network request while it runs | |
| Cost | Nothing: free software and an open model, no account, no paid API | |

Measured cost and speed are in [docs/reports.md](docs/reports.md).

### 1. Install the tools

[uv](https://docs.astral.sh/uv/) installs Python 3.12 and every package. Install [Git](https://git-scm.com/downloads) as well if it is missing.

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards so that `uv` is on the path.

### 2. Run OASIS with the stand-in model

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

Open http://127.0.0.1:8000, read the data notice and choose Save on this computer or Start without saving. With `OASIS_LLM_BACKEND=fake` (the `.env.example` default), replies come from a deterministic stand-in model, so everything except the wording of replies works without the real model.

Saved conversations live in `data/oasis.db` (`OASIS_DB_PATH`). The browser keeps only the session key, so anyone using the same browser can reopen a saved conversation. Unsaved conversations stay in memory and are forgotten after two hours idle or on restart. Export and delete are under the gear icon (Settings).

### 3. Add the real model

Install llama.cpp (built and tested with build 11552, commit `23b0202a1`):

```bash
winget install ggml.llamacpp
```

On macOS or Linux, use `brew install llama.cpp` instead. Start the model server in its own terminal. The first start downloads the 2.7 GB model from Hugging Face; later starts use the copy on disk:

```bash
llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096 -np 1 -ngl 0 --host 127.0.0.1 --port 8080
```

`-ngl 0` keeps the model on the processor, because integrated graphics on small laptops run out of memory loading it. In `.env`, set `OASIS_LLM_BACKEND=llama_server`, restart OASIS, and check the model with:

```bash
uv run python scripts/model_smoke_test.py
```

A reply takes about 5 to 10 seconds with the model warm, and about 20 seconds for the first reply after the model has been idle or pushed out of memory by other applications. Closing large applications, such as a browser with many tabs, gives the best speed.

### Optional ML models

Four small models add to the rules without replacing them. Each can only add an alert, an emotion, a rejection or an item, and each has a fallback:

- an add-only crisis classifier for misspellings, which raises held-out typo recall from 51% to 80%;
- learned emotion scorers trained on GoEmotions, which raise ROC-AUC from 0.54-0.67 to 0.82-0.93;
- an NLI check in the guard that catches reworded agreement;
- semantic psychoeducation retrieval, which finds the right item for 24 of 33 reworded questions, against 3 before.

The first two need nothing extra. For the last two, run `uv sync --extra ml` and then `uv run python ml/fetch_models.py`. Data, training, metrics and limits are in [docs/ml_models.md](docs/ml_models.md).

### Share a test version by link

You can run OASIS with the real model on one computer and give testers a link through a Cloudflare tunnel, in demo mode (memory only, a test-version notice and banner, made-up messages only). See [docs/demo_host.md](docs/demo_host.md).

### Developer checks

Run every check (lint, types, import rules, security scan, dependency audit, and tests with coverage):

```bash
uv run python scripts/verify.py
```

Other scripts: `scripts/safety_eval.py` measures crisis detection, `scripts/bias_eval.py` runs the bias evaluation (`--fake` for the decision plane only), `scripts/load_test.py` measures speed and concurrency, `scripts/model_bakeoff.py` compares candidate models, `scripts/licences.py` regenerates [docs/licences.md](docs/licences.md), and `scripts/export_diagrams.py` exports the diagrams (needs Node.js).

## Limitations

- Not a clinical tool. OASIS gives no diagnosis or medication advice and is not an emergency service. The crisis rules, post-crisis policy and clinical wording await review by a qualified clinician ([docs/clinical_review.md](docs/clinical_review.md)), and the data notice awaits legal review.
- English only. Crisis detection is tested on several English varieties (British, AAVE, Indian English, Nigerian Pidgin, Hinglish, Spanglish, Taglish), but a crisis written in another language is not detected.
- No fine-tuning of the language model. The style setting changes how replies are framed, not what the model learned.
- WEIRD-data caveat. The techniques, questionnaires, word lists and model training data come mostly from Western, educated, industrialised, rich and democratic populations. The bias evaluation checks that decisions do not change with dialect, names or identity, but OASIS is not culturally validated anywhere.
- One person at a time. On the reference laptop, two people at once still get every reply, slowly; beyond that, extra messages get a "busy" reply.
- Crisis numbers were verified in October 2026 and need re-checking before any real use.
- Saved conversations are only as private as the computer. Anyone using the same browser can reopen one, and full-disk encryption is recommended.

## Project status

The fourteen-phase build is complete, with changes from demo testing and the optional ML models. Each phase's design, evaluation, results and known limits are summarised in [docs/reports.md](docs/reports.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/architecture.md](docs/architecture.md) | Architecture, data flow, stack and storage |
| [docs/design.md](docs/design.md) | Algorithms, data model, API, prompts and interface |
| [docs/rules.md](docs/rules.md) | Engineering rules |
| [docs/reports.md](docs/reports.md) | Build and evaluation report for every phase |
| [docs/ml_models.md](docs/ml_models.md) | ML models: data, training, evaluation and limits |
| [docs/memory.md](docs/memory.md) | Key decisions, open items and unverified results |
| [docs/clinical_review.md](docs/clinical_review.md) | Items awaiting clinician review |
| [docs/demo_host.md](docs/demo_host.md) | Sharing a test version by link |
| [docs/licences.md](docs/licences.md) | Licences of everything OASIS runs |

## Licence

MIT ([LICENSE](LICENSE)). The licence covers the code; it does not make OASIS fit for clinical use.
