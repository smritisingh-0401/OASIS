# OASIS

**A lightweight, explainable, safety-first mental health support chatbot.**

OASIS offers evidence-based conversational support (CBT, DBT, mindfulness), standard screening (PHQ-9, GAD-7) when the conversation warrants it, and a warm listening mode — while staying transparent about *why* it responds the way it does. A rule-based decision plane plans each reply; a small local language model only phrases it. Safety checks run before the model, and every failure falls back to a vetted templated reply.

> ### Important
> OASIS is a **subclinical support and screening tool, not a diagnostic system and not an emergency service.** It complements, and never replaces, a qualified clinician.
> **If you are in danger or thinking about ending your life, contact your local emergency number or a crisis line now.**

## Why

A review of 97 studies (16,620 participants) on mental health chatbots identified ten recurring limitations: black-box reasoning, repetitive or sycophantic replies, WEIRD-dominated data, cost and access barriers, unclear privacy, lack of user control, implementation cost, output bias, low engagement, and glitches at critical moments. OASIS addresses each with a testable feature — see [docs/PRD.md](docs/PRD.md).

## Key properties

- **Safety first** — pure-Python crisis detection runs before anything else; crisis handoff makes zero model calls.
- **Explainable** — every reply links to an explanation of the signals that drove its strategy.
- **Private** — local-only, pseudonymous, ephemeral mode, export and delete.
- **Free to run** — quantised open model on a CPU laptop; no paid API.

## Quick start

_To be written in Phase 1 and verified on a fresh machine in Phase 14._

## Project status

| Phase | Status |
|---|---|
| Step A — project documents | In review |
| 1–14 | Not started |

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

## Licence

_To be decided._
