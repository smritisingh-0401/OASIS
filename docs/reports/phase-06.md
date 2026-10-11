# Phase 6 — Companion mode

**Goal.** Warm active listening without sycophancy. A companion reply recognises the feeling, then asks one gentle question. It never over-praises, gives advice nobody asked for, or encourages the user to depend on OASIS (FR-CMP-1, FR-CMP-2).

## 1. Design

| Component | File | Role |
|---|---|---|
| Reply checks | `guard/checks.py`, `content/companion/checks.yaml` | `check(draft, plan)` is the engine's default guard (it replaces the Phase 4 pass-through). Each failed check returns the name of the rule it broke |
| Advice cue | `content/lexicons/cues.yaml` (`asks_advice`), `core/signals.py` | "what should I do", "any tips", "how do I deal with", "should I…" swap `no_advice` for `offer_ideas` ("offer one or two gentle, practical suggestions") for that turn |
| Companion plan | `core/planner.py` | Rules `validate_first, one_question, no_advice, no_praise` on every companion reply the LLM writes: routed turns, the first turn after a crisis is cleared, and typing during a questionnaire |
| Prompt | `llm/prompt.py` | The "must" line and a retry's "broke these rules" note use plain sentences ("Ask exactly one gentle, open question, at the end."), not rule names. A system line forbids encouraging reliance on OASIS |
| Tone check | `scripts/tone_check.py` | Sends 12 sample messages to the real model through the full engine and writes every draft, the rules it broke and the final reply to `docs/reports/phase-06-tone-check.md`. `--fake` checks the plumbing |

**The checks.** They are matched on the safety normaliser's form of the reply.

| Rule | Fails when | Applies to |
|---|---|---|
| `validate_first` | No validating phrase ("that sounds", "it makes sense", "I'm sorry", "no wonder", "I can hear"…) before the question | Companion |
| `one_question` | Not exactly one "?", or the reply doesn't end with it | Companion |
| `no_praise` | Flattery ("you're so brave", "I'm proud of you", "well done"…) | Companion |
| `no_advice` | Advice phrasing ("you should", "have you tried", "I suggest", "it might help to", "try to", a sentence opening with "Try" or "Consider"…) | Companion, unless advice was asked for |
| `no_dependency` | "always here for you", "you don't need anyone else", "only I understand you", "talk to me instead"… | Every generated reply, in every mode |

Smriti chose companion-only scope: CBT and DBT replies carry similar rules in their prompts but are not checked for them until the Phase 7 guard.

**On failure.** This uses the existing engine flow:
1. One retry, naming the broken rules in plain words.
2. Then the `guard_fallback` template, which passes the companion checks itself. Phase 7 replaces this fallback with the Socratic question bank.

**Tuned on the first real-model run** (2026-10-11):
1. The first run gave 11/12 first-draft passes, but showed three problems. Each fix has a test:
   - **Every reply opened with "It makes sense…".** The `validate_first` rule text ("…showing it makes sense") was being copied. It now reads "reflecting their feeling back in your own words".
   - **Advice requests got only a question.** The prompt never said suggestions were allowed. An advice request now carries `offer_ideas`, placed before `one_question` so suggestions come before the closing question.
   - **One false rejection:** "try to" inside a question.
2. Later runs found three more false rejections, each now a passing example in `good_replies.yaml`:
   - "it feels like…" and "it feels really disappointing…": validation phrasings missing from the list.
   - "what you have to do": not advice.

**Departures from the phase plan's file list.**
- No `companion/plan.py`: the companion plan is one dictionary entry in the planner.
- The checks live in `guard/checks.py`, because design §8.2 lists the C-* checks as guard checks and the engine's guard hook is where every draft passes.
- One `content/companion/checks.yaml` instead of two files.
- The pass-through `guard/hook.py` is removed.

## 2. Evaluation method

- **Curated replies** (`tests/data/companion/`, written before the phrase lists):
  - 12 good companion replies must pass.
  - 21 bad replies must fail with exactly the labelled rules: 4 validation, 3 question-count, 4 praise, 6 advice, 4 dependency. Some bad replies break two rules.
- **Scope:** a reply that breaks every companion rule must pass in CBT, DBT, mindfulness, grounding and psychoeducation modes. Dependency language must fail in all six modes.
- **Self-consistency:** the `guard_fallback` template and every canned fake-model reply must pass, so the fake-model demo never falls back.
- **Advice cue:** 6 requests fire; 4 ordinary messages, including "my mum always tells me what I should do", don't.
- **Planner:** the companion rules on routed, post-crisis and questionnaire free-text turns; `no_advice` dropped when advice is asked for.
- **Engine:**
  - A flattering, dependency-laden first draft is retried, and the retry prompt names "Do not praise or flatter".
  - Two failing drafts end in the fallback.
- **Content:** each kind of invalid checks file is rejected.
- **Mutation spot-check:** 11 deliberate faults across checks, planner, signals, prompt, fake model and engine wiring.
- **Script demo:** `scripts/tone_check.py --fake`.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass |
| Tests | 956 passed, 0 skipped |
| Coverage | 98.2% overall; `oasis.guard` 100%, `oasis.router` 100%, `oasis.assessment` 98.6%, `oasis.safety` 97.1% |
| Curated replies | 12/12 good pass; 21/21 bad fail with exactly their labelled rules |
| Advice cue | 6/6 requests fire; 0/4 ordinary messages |
| Mutation spot-check | 10/11 caught at first. The miss was a non-validating canned fake reply, because the engine test's three messages never selected it; the test was replaced by a direct check of every canned reply. Now 11/11 |
| Tone check, fake model | 12/12 first drafts pass; transcript format confirmed |
| Tone check, real model (Qwen3.5-4B Q4_K_M, `unsloth/Qwen3.5-4B-GGUF`, llama.cpp b11552) | Final run: 10/12 first drafts pass, and both rejections are genuine (no question; two questions plus unrequested advice), fixed by the retry; 0/12 fallbacks. 0 fallbacks across all runs. Smoke test: thinking disabled, 4.7–6 s per reply after a 15.7 s first reply. Transcript: `phase-06-tone-check.md` |

## 4. Known limits

- **Same opener.** The 4B model opens almost every reply with "It sounds like" (it was "It makes sense…" before the rule wording stopped priming it). Within one conversation this will read as scripted; a multi-turn tone check is needed.
- **Warmth on good news** ("I am really happy to hear that you accomplished…") passes; it is not flattery of the person, but it is close to the line (CR-14).
- **Twelve samples, one model, single turns.** The pass rate is indicative only.
- **The phrase lists are hand-written,** and the same author wrote the curated sets. Expect misses:
  - Praise without the listed words ("what courage that took") gets through.
  - Validation in unlisted words ("ugh, that's rough") fails, costing a retry.
  - Imperative advice outside the listed openers gets through.
- **"Exactly one question" counts question marks.** A question phrased without "?" fails, and a rhetorical "?" counts.
- **Advice suggestions are not checked** for safety beyond the dependency list until Phase 7 (diagnosis and medication checks).
- **The advice cue is a phrase list:** "I don't know what to do" does not count as asking.
- **CBT and DBT replies** are only checked for dependency language until Phase 7.
- English only; all phrase lists await clinician review (CR-14).
