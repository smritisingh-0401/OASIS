# OASIS — Project Memory

Handover log so any session can resume without re-explaining. Neutral engineering log; keep it concise and current. Update at the end of every phase and every working session.

**Start of every session:** read this file and [rules.md](rules.md), then continue from *Current status*.

---

## Current status

| | |
|---|---|
| Current phase | **Build plan complete** (Phases 1-14) |
| Done | Step A and Phases 1-4. 2026-10-09: glassmorphism UI redesign, questionnaire flow fixes and the post-crisis explicit-request rule merged to `main` (PR #1); manual CI trigger (PR #2); `main` protected (both `verify` checks required). 2026-10-11: Phase 4 approved and merged (PR #3). 2026-10-12: Phase 5 merged (PR #4). 2026-10-13: Phase 6 approved by Smriti, including the manual-testing changes of 2026-10-12 (tone, crisis wording, screening and router timing); merged (PR #5). 2026-10-13: Phase 7 approved by Smriti, including the manual-testing changes (DBT anger, exact exercise steps, companion after an exercise) and the closed known limits; merged (PR #6). 2026-10-22: Phase 8 approved by Smriti; merged (PR #7). 2026-10-23: Phase 9 approved by Smriti; merged (PR #8). 2026-10-24: Phase 10 approved by Smriti; merged (PR #9). 2026-10-25: Phase 11 approved by Smriti; merged (PR #10). 2026-10-26: Phase 12 approved by Smriti; merged (PR #11). 2026-10-26: Phase 13 merged (PR #12). 2026-10-27: Phase 14 approved by Smriti; merged (PR #13) |
| In progress | Nothing |
| Next | No phase planned; open items 3-5 and 8-10 before any real use |
| Blocked on | Nothing; open items 3-5 and 8-10 need Smriti before any real use |

### Environment notes (development machine, 2026-10-07)
- Windows 11. Python 3.12.15 managed by uv (system Python 3.11.9 is not used); uv 0.12.23 installed with `python -m pip install --user uv` and invoked as `python -m uv`.
- Verify command on every platform (and in CI): `uv run python scripts/verify.py`. The Makefile wrapper was removed 2026-10-12.
- Local dev server: copy `.env.example` to `.env`, then `uv run uvicorn oasis.api.app:create_app --factory`.
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
| 2026-10-07 | Crisis resources extended to two tiers: Tier 1 (verified crisis line + emergency number) targeted at 64 countries across all inhabited regions (built as 40; see 2026-10-08); Tier 2 (emergency number only) for every other country | World coverage while keeping the set of crisis lines that must be re-verified manageable; v1 is English-only, so English-speaking countries were prioritised | Full entries for every country; Asia-only list |
| 2026-10-07 | (superseded) Crisis resources cover India, Pakistan, Bangladesh, Sri Lanka, Nepal, Bhutan, Myanmar, China, South Korea, Japan, Thailand, Maldives, Vietnam, Hong Kong, Taiwan, Cambodia, Malaysia, Singapore, Russia; country chosen by the user (optional), never inferred | Target user regions; consistent with no-nationality inference | Single configured region; locale/IP inference |
| 2026-10-07 | Assistant config files excluded via `.git/info/exclude` instead of `.gitignore` | Keeps them out of git without naming them in the repository | Listing them in `.gitignore` |
| 2026-10-07 | Phase 1: turn recording lives in `ChatEngine` (no separate `core/recorder.py`) | One call site; a separate module would be a one-function wrapper | Separate recorder module |
| 2026-10-07 | Phase 1: fallback templates are Python constants until the Phase 2 content loader | Avoids adding YAML loading before it has a second user | YAML now |
| 2026-10-07 | Phase 1: storage backend chosen by settings; `POST /session` has no body; per-session ephemeral mode deferred to Phase 10 | Ephemeral end-to-end is Phase 10 scope | Per-session ephemeral now |
| 2026-10-07 | Phase 1: `/history` supports `limit` only; `before` pagination deferred | No caller needs it yet | Implement now |
| 2026-10-07 | Help card uses a native `<details>` element | Opens with no JavaScript and no server (S12, F2) | JS dialog |
| 2026-10-07 | Pytest ignores Starlette's "use httpx2" TestClient deprecation (message-specific filter; all other warnings stay errors) | Avoids adopting a new package only for tests | Add httpx2 |
| 2026-10-07 | pip-audit runs on `uv export` output with hashes and `--disable-pip` | Audits exactly the lockfile; uv venvs have no pip | Auditing the live environment |
| 2026-10-07 | Dev dependency `psutil` (+ `types-psutil`) | Cross-platform RSS measurement in the model bake-off | Manual Task Manager readings |
| 2026-10-08 | Normalisation produces up to 4 variants (base, leetspeak, unspaced, both); patterns are made tolerant of repeated letters by a load-time rewrite | Catches obfuscation without hand-writing letter repeats in every pattern | One normalised string; hand-written `ki{1,2}ll` patterns |
| 2026-10-08 | New `self_harm` tier: non-suicidal self-injury gets the full handoff | Self-injury disclosures need the same human support signposting (CR-01, to confirm) | Treat as non-crisis |
| 2026-10-08 | Allow-list suppresses a hit only when the idiom span covers the hit span | "dying to see it, I want to kill myself" must still trigger | Message-level suppression |
| 2026-10-08 | Invalid safety content stops the app at startup (validation plus example self-check) | Bad content fails at boot, never at turn time | Skip bad patterns with a warning |
| 2026-10-08 | Help card rendered on the server into `index.html` as nested `<details>`; no JavaScript or fetch | Works with the backend down after page load (S12, F2) | JSON endpoint plus client rendering |
| 2026-10-08 | Crisis resources: Tier 1 needs a line verified on the service's own or a government site; Tier 2 uses UK FCDO travel advice emergency numbers | One consistent, citable standard; no unverified numbers | Aggregator sites; unverified lists |
| 2026-10-08 | Sites that blocked the fetcher were not bypassed (no user-agent spoofing or disabled certificate checks); those countries are Tier 2 until checked in a browser | Verification must be honest | Bypassing blocks |
| 2026-10-08 | Crisis audit, post-crisis flag and history placeholder written by a background task after the response | Storage can never delay or block the handoff (S2) | Writing before responding |
| 2026-10-08 | Post-crisis state: in-memory set plus persisted flag; cleared only by an explicit continue phrase or the "Continue talking" button | Holds when storage is down; never inferred | Time-based expiry |
| 2026-10-08 | Templates stay Python constants (CR-18) | The Phase 2 content files are safety data with their own loaders; templates have no second user yet | YAML template loader now |
| 2026-10-08 | No classifier hook in the gate until a classifier exists (S7 still applies to any future one) | No speculative interface | Pluggable classifier parameter |
| 2026-10-08 | PHQ-9 and GAD-7 text verified against the official phqscreeners.com forms; GAD-7 asks no functional question because its published form has none | Rules CL1: published items only | Following the design diagram for both |
| 2026-10-08 | Assessment buttons send their label as the message plus a structured action | History stays readable and the safety gate still sees text; answers are never parsed from free text | Action-only requests |
| 2026-10-08 | PHQ-9 item 9 is checked on the action before storage | A database failure must never block the crisis handoff | Checking only after loading the questionnaire |
| 2026-10-08 | Trigger weights raised 0.5 → 0.7 after the first measurement; threshold kept at the design's 0.45; messages about someone else excluded | Recall 0.31 → 0.93 with no false positives on the labelled set | Lowering the threshold; first-person-only rule (missed elided subjects) |
| 2026-10-08 | Typing while an offer is open counts as "not now"; typing mid-questionnaire pauses it | Consent must be explicit; the user is never trapped in a questionnaire | Keeping the offer open |
| 2026-10-08 | An explicit request overrides the 24-hour decline cooldown (Smriti) | The cooldown exists to stop OASIS asking again, not to refuse a user who changes their mind | Cooldown blocks explicit requests too (design as first written) |
| 2026-10-08 | Paused questionnaires expire 24 h after they started and their answers are discarded | No separate pause timestamp needed; data minimisation | Storing a pause time |
| 2026-10-09 | An explicit screening request is allowed after a crisis earlier in the conversation, once post-crisis mode is cleared; unprompted offers stay blocked (Smriti, CR-19) | A user who asks is not refused; OASIS still never raises screening itself after a crisis | Crisis placeholder blocks explicit requests too |
| 2026-10-09 | UI redesign: soft-blue glassmorphism, light theme only (dark deferred); prototype banner removed; rule S13 updated (Smriti) | Owner's design direction; every text colour checked for WCAG AA over the darkest background orb | Keeping the original flat design |
| 2026-10-09 | Self-hosted Nunito font; CSP `font-src` from `'none'` to `'self'`; rule F1 reworded to allow self-hosted fonts only (Smriti) | A rounded font fits the theme and looks the same on every device; still no external requests | System fonts only (no rounded body font on Windows) |
| 2026-10-09 | The questionnaire instruction is its own message (`preface`, stored as a separate turn) before the first question and on resume; `/history` returns the open questionnaire's card | Clearer flow; a reload no longer loses the buttons | Instruction repeated on every card |
| 2026-10-11 | Runtime dependency `vaderSentiment` (MIT) for the valence baseline; its `requests`/`nltk` use is confined to the package's `__main__` demo, so nothing touches the network at import | Design §5 baseline; a maintained lexicon instead of a hand-made one | NLTK's VADER (needs a lexicon download); vendoring the lexicon |
| 2026-10-11 | Router consent: cbt, dbt and mindfulness ask once per session (Yes / Not now); Not now or typing over the offer resets the lead; grounding starts without asking (Smriti, CR-11) | Consent before structured modes; acute overwhelm needs immediate help | Entering structured modes silently |
| 2026-10-11 | One low-risk exercise per mode: Thought check, STOP skill, Notice the breath, 5-4-3-2-1 senses; one step per user message (Smriti, CR-12) | Small, reviewable set within rules CL7 | Several scripts per mode in v1 |
| 2026-10-11 | Exercise steps are phrased by the LLM from a `- script:` line and fall back to the step's own text; the fake LLM returns the step verbatim | Follows design §13.2 while keeping exercises working with the LLM down and visible without weights | Fixed-text steps only |
| 2026-10-11 | `distortion` = clipped sum of the Burns category scores; acute overwhelm is decided in the router from `overwhelm` and the weights file's threshold | A message with several distortions scores higher; one threshold to review (CR-11) | Maximum category score; separate acute signal |
| 2026-10-11 | Hysteresis inside `router/router.py`; exercise scripts in `router/exercise.py`; router memory as JSON in the existing `sessions.router_state` column; malformed memory loads as a fresh state | Fewer one-function modules; no migration; a bad row never breaks a turn | `router/hysteresis.py`, separate techniques package |
| 2026-10-11 | No screening offer while an exercise runs, even on explicit request | Design §3.2 guard ("not mid-exercise") | Interrupting the exercise |
| 2026-10-11 | Psychoeducation precedence: an explicit questionnaire request beats it, but a message that is both gets the item first as its own message, then the offer; psychoeducation beats an unprompted offer (Smriti) | The user asked for an action; a short explanation still helps | Psychoeducation first, offer on a later turn |
| 2026-10-11 | Each psychoeducation item is shown at most once per session; IDs kept in the router memory JSON | Venting "what's wrong with me" twice should not get the same explanation twice; no migration | Repeat every time; a new column |
| 2026-10-11 | Eleven psychoeducation items from NHS and WHO pages, each page checked; first matching item in file order wins, general item last | Small, reviewable set; deterministic and explainable | Scored topic matching |
| 2026-10-11 | No psychoeducation under acute overwhelm or mid-exercise | Grounding first; exercises are not interrupted | Explaining first |
| 2026-10-11 | Companion checks (validate first, one question ending the reply, no praise, no advice) apply to companion replies only; dependency language is checked on every generated reply (Smriti) | Keeps the change to companion mode; CBT/DBT get their checks with the Phase 7 guard | Checking every mode that carries the rule |
| 2026-10-11 | An explicit advice request swaps `no_advice` for `offer_ideas` for that turn via an `asks_advice` cue (Smriti); the real model ignored the request until the prompt said suggestions were wanted | FR-CMP-2 forbids *unprompted* advice | Never giving advice; only dropping `no_advice` |
| 2026-10-11 | Real model: `unsloth/Qwen3.5-4B-GGUF` Q4_K_M (Apache-2.0, 2.74 GB) on llama.cpp b11552 (winget `ggml.llamacpp`, Vulkan build), started with `llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096` (`-np 1` added 2026-10-12) | First real-model runs; official Qwen repo publishes no GGUF | Other quantisers |
| 2026-10-11 | Checks live in `guard/checks.py` as the engine's default guard (pass-through `guard/hook.py` removed); reason codes are rule names; no `companion/plan.py`; one checks file | Design §8.2 puts the C-* checks in the guard; the companion plan is one dictionary entry | Separate companion package; two YAML files |
| 2026-10-11 | Prompt "must" line and retry note use plain sentences per rule instead of rule names | A real model follows sentences, not snake_case | Rule names |
| 2026-10-12 | Simplification pass: one `load_yaml` / `require_review` in `oasis.content` for every non-safety content file; one best-effort storage-write helper in the engine; VADER `valence()` folded into `core/signals.py`; Makefile removed (`scripts/verify.py` is the only verify command) | Less repeated code; the safety loaders stay separate for isolation (rules S8) | Keeping the copies |
| 2026-10-12 | Varied openers: the last 3 companion openers go into the plan, the prompt and a `fresh_opener` check | The 4B model opened most replies the same way; a concrete "do not begin with" works where "vary your wording" does not | Prompt instruction only; higher sampling temperature |
| 2026-10-12 | `validate_first`, `one_question` and `fresh_opener` are soft rules: retried, then kept; praise, advice and dependency stay hard | A phrase list cannot know every way to validate; as a hard rule it sent 5/48 out-of-place fallbacks in the conversation tone check | Ever-longer phrase lists |
| 2026-10-12 | Companion fallback "I hear you. What feels most important to talk about right now?"; the Socratic `guard_fallback` stays for other modes. Warmth about good news allowed (Smriti) | The Socratic question does not fit companion talk, especially good news | One fallback for every mode; blocking "glad to hear" |
| 2026-10-12 | Companion tone: the goal and `validate_first` say "respond to / acknowledge what they said", and the system text says to keep small talk light and never make a feeling bigger or darker | "hi" and "this traffic is killing me" got worried, inflated replies; the signals were clean, the prompt forced a feeling | Gating on the signals ("my boss yelled at me" scores the same as "hi") |
| 2026-10-12 | Crisis reply and help card: "If you feel like talking to someone in person…" replaces "If you are in immediate danger, please call your local emergency number" and the card's "If you are in danger right now / Call your local emergency number" (CR-03) | Owner's decision on tone | Keeping a short danger line (recommended, since safe-messaging guidance favours a route to immediate help); flagged for the clinician |
| 2026-10-12 | Screening trigger: `k` lowered from 3 to 2 turns in a row, and an earlier crisis no longer blocks unprompted offers once post-crisis mode is cleared (CR-09, CR-19) | Owner's decision: offers came too late; the post-crisis hold still blocks every offer until the user says they want to keep talking | Keeping k = 3; keeping the crisis block on unprompted offers |
| 2026-10-12 | PHQ-9/GAD-7 re-administration window lowered from 14 to 10 days, for offers and requests (CR-10); the router's moderate-or-worse flag uses the same window | Owner's decision | Keeping 14 days, matching the instruments' two-week recall period |
| 2026-10-12 | Router: a mode must lead for 2 turns in a row (was 3) before its offer, for cbt, dbt and mindfulness; mindfulness's anxiety weight 0.5 -> 0.85; distortion, dysregulation, anger and anxiety phrases widened from manual testing (CR-11, CR-20) | Reworded self-criticism ("I always do something wrong", "burden of my failure") reset the streak, so CBT was never offered; anxiety alone could never lead to mindfulness | Raising the anger weight (would send anger alone to DBT); adding stress to overwhelm (would start grounding at once) |
| 2026-10-12 | llama-server runs with one slot (`-np 1`) | OASIS already sends one request at a time (`llm_max_concurrency = 1`), so it costs nothing. Measured: no speed gain. Qwen3.5's hybrid (linear-attention) layers mean llama.cpp re-reads the whole prompt every turn (201-378 tokens at ~55 tokens/s, 4-7 s), because the prompt changes near its start (the per-turn plan). Turns took 9-11 s, or ~22 s with a guard retry | Moving the plan to the end and keeping history append-only (the only way to get prefix reuse with this model; declined for now); a shorter history; a smaller model |
| 2026-10-13 | Phase 7 targets (PRD L2): at least 90% of the curated sycophantic replies caught, at most 5% of the curated benign replies blocked (Smriti) | Strict enough to matter, loose enough for a phrase-based guard without over-blocking | 95% / 10%; 80% / 2% |
| 2026-10-13 | Router: dbt's anger weight 0.35 -> 0.85; dysregulation phrases widened ("lose my temper", "snapped", "lashing out", "mood swings", "emotions are all over the place") (CR-11, CR-20; Smriti) | Manual testing: "angry, can't control it" -> "i am so mad" -> "going to explode" never got a DBT offer, because "so mad" alone led companion and reset the 2-turn streak. Reverses the 2026-10-12 choice; mild annoyance ("I'm so annoyed", "I hate my job") still misses the margin | Keeping 0.35 (anger alone never reaches DBT) |
| 2026-10-13 | The diagnosis and medication checks skip a clause in which the reply declines ("I cannot tell you if you have depression"); a diagnosis in another clause still fails (CR-16; Smriti) | Real-model tone check: both refusals to "do you think I have depression?" were blocked and the turn ended on the generic fallback | Keeping the list strict and accepting the fallback |
| 2026-10-13 | Exercise steps shown word for word: the LLM writes one acknowledging sentence (first sentence kept; no question, step or instruction of its own, guard rule `ack_only`), then the step text follows; the first step after "Yes" has no LLM call (Smriti) | Manual testing: rephrasing STOP, the 4B model wrote "N is for Name what you are feeling" and "T is for Take a breath", while the card showed the real step. Real-model rerun: 4/4 steps correct, every turn kept the model's sentence | Exact script only (no response to the user); keep rephrasing and check the step's opening |
| 2026-10-13 | When an exercise ends (last step, Stop button or typed opt-out) the mode goes back to companion; consent is kept (Smriti) | Manual testing: still in DBT after STOP, the next reply followed the DBT goal ("offer the named skill") and repeated "T is for Take a step back" | Staying in the mode until the router moves on (2 turns) |
| 2026-10-13 | The prompt history leaves out earlier "X is for…" step lines, and `no_exercise_step` (hard, every generated reply) rejects a made-up one | Manual testing: back in companion after STOP, "i think i can restart" got "R is for Reconnect with what feels safe"; with the guard alone both drafts invented a step ("Q is for Quietly check in") and the turn fell back. With the history change the real model wrote a normal reply | Guard only (generic fallback every time) |
| 2026-10-13 | Known limits closed (Smriti chose 1, 2, 3, 5, 6, 7): harsh labels scored with VADER on both sides (adjective <= -0.3 before a person word, or a harsh word); every verb form of starting or stopping medicine; refusals only in the "can't tell / say / know if or whether" form; praise of choices and thoughts, also before exercise steps; one- or two-word replies get the exercise step as written; a guard stress check (`tone_check.py --agreeable`). Also fixed: a draft failing only soft rules was dropped when its retry timed out | The held-out misses ("I'm a horrible person", "coming off your antidepressants") and the rerun tone check (refusal split at "and"; two kept drafts lost to a retry timeout; "That is a brave choice", "That is a good start") | A fresh held-out set by a second author (limit 4, still open); requiring loss-of-control words for DBT (limit 8, kept as chosen) |
| 2026-10-13 | llama-server runs with `--cache-ram 0`: `llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096 -np 1 --cache-ram 0 --host 127.0.0.1 --port 8080` | The prompt cache defaults to 8192 MiB, more than this laptop's 6 GB. After a day of runs the server held ~12 GB, swapped (6.7 tokens/s), timed out 20 of 70 tone-check turns and crashed ("bad allocation"). Qwen3.5's hybrid layers cannot reuse a cached prompt here anyway (2026-10-12 measurement), so the cache only cost memory | A smaller cache (e.g. 512 MiB) |
| 2026-10-13 | "You're right" / "I agree with you" fail `no_agreeing` on thinking-trap and medication messages without an echo (Smriti) | Guard stress check: the agreeable model reworded the claim ("fault" -> "responsibility") and agreed ("I agree with you that..."), and told someone asking about stopping antidepressants "you are right to want to..." | Blocking the phrases on every reply ("You're right, grey days drag" is fine in small talk) |
| 2026-10-20 | Phase 8 builds the cross-session trend and change flag as designed, proven on synthetic timelines, although every browser session is a new user today (Smriti) | Keeps FR-TRK-2 complete without adding a persistent identity before the Phase 10 consent, export and delete | A long-lived user token now; within-session tracking only |
| 2026-10-20 | First-person pronoun rate counts I, me, myself (and contractions), not my / mine | Tackman et al. (2019): the depression link holds for every first-person singular form except the possessive | The design's list with my / mine |
| 2026-10-20 | Mood features are recorded only for typed messages, never for button presses or crisis messages; recomputed aggregates, no running Welford state | A button label is not the user's words; nothing runs after a crisis verdict (S3); recomputing is simpler and exact | Recording every turn; incremental Welford updates |
| 2026-10-22 | Phase 9: SHAP values for the lexicon scorers are computed in closed form, `φ_i = w_i (x_i − E[x_i])`, `base = b + Σ w_i E[x_i]`; the `shap` package is a dev-only dependency used as a test oracle (Smriti) | Every detector is linear (no scikit-learn model was built, no black-box part in v1), so SHAP values are exact in closed form; a runtime `shap` would add numpy, scipy, pandas and scikit-learn to a low-RAM local app for one formula. Spike: shap 0.54.1 installs on Windows, Python 3.12.15 | `shap.LinearExplainer` at runtime (design §10.1 as written); LIME (no black-box part) |
| 2026-10-23 | The chosen-country setting for the help card (design §6, deferred to "the settings work in Phase 10") moves to Phase 11, with the style profile in the same `settings` table (Smriti) | Keeps Phase 10 to privacy; Phase 11 creates the settings table and page anyway | Building it in Phase 10 |
| 2026-10-24 | The help card opens the country of the computer's time zone first, with the full list folded under a "Not right? Choose another country" dropdown, open when there is no suggestion (Smriti); the card's "pick your country below" was dropped. Read in the browser, never sent or stored; map built from the IANA time zone database by `scripts/time_zones.py` (CR-24) | One tap fewer at a crisis moment, with no permission prompt and nothing leaving the computer. Supersedes "country chosen by the user, never inferred" (2026-10-07) for the suggestion only; the user still chooses | Browser geolocation (blocked by rules P6; desktop browsers ask an online location service; a prompt at a crisis moment); remembering the chosen country (still planned for Phase 11) |
| 2026-10-23 | Phase 10: saved or unsaved chosen per session at onboarding (`storage/split.py` routes each call); consent gate in the engine after the safety gate, remembered in memory for storage outages; notice versioned in YAML and rendered on the server | Ephemeral end to end (P4) without a second app; a crisis is always answered (architecture §3.3) | One app-wide storage setting; a gate in API middleware before the safety check |
| 2026-10-24 | Crisis bookkeeping (audit, post-crisis flag, placeholder) still runs for a session that has not consented (Smriti) | Safety record with no message text, deleted with the account; the UI cannot send a message before consent | Skipping it until consent |
| 2026-10-24 | Delete reports `503 erasure_pending` when another program blocks the overwrite, and the store retries without waiting after every later call and at startup; idle unsaved sessions expire on every request (Smriti) | SQLite reports a blocked checkpoint as busy, not as an error, and the old text stayed on disk (measured); expiry only on unsaved requests let idle data outlive 2 h | A check before deleting (misses a reader that started on an empty WAL); a timer task |
| 2026-10-24 | Rule F5 changed (Smriti, open item 11): a saved session's key is kept in `localStorage`, an unsaved session's in `sessionStorage`; notice raised to version 2 to say anyone using this browser can open a saved conversation | With `sessionStorage` only, closing the tab left a saved conversation on disk that OASIS could no longer open, export or delete | Saying so in the notice and waiting for Phase 13; `localStorage` for unsaved sessions too (they would reappear in a new tab) |
| 2026-10-24 | "See details" (the raw explanation record) and the scope note removed from the "Why this reply?" panel; a failed fetch now says OASIS could not be reached and retries on the next open; the mood trend's sources fold into a closed "What it is based on" dropdown (Smriti) | The raw JSON with regex patterns suits a developer, not a user; the record, with its scope note, is still served by `GET /explanations/{id}` and in the export. The page no longer shows FR-XAI-2's statement or FR-XAI-3's debug view. The trend label stays visible (FR-TRK-3) | Keeping the debug view in the panel |
| 2026-10-24 | Phase 10 squash-merged (PR #9) by request; Phase 11 branched from `main` (Smriti) | Same as Phases 4-9 | Branching from `phase-10-privacy` |
| 2026-10-24 | Phase 11: the engine attaches the style to the plan after planning; the planner never receives it and only the prompt builder reads it. `StyleProfile` in `oasis.types` (no `style/profile.py`); `UserSettings(style, country)` in the repository; `oasis.style` its own import layer under llm/storage/safety and in contract C2 | Invariance by construction, still property-tested end to end; the plan carries the type | `plan(signals, state, style)` as sketched in design §6 |
| 2026-10-24 | The default style (balanced, neutral) adds no framing; the loader refuses a default that adds text | Users who never open Settings get the prompt every tone check ran on | A framing sentence for every value |
| 2026-10-24 | Indirect-phrasing suggestion: a note "You can ask OASIS to word things more gently in Settings." with a link, once per tab, when this typed message and 2 of the last 3 are hedged (Smriti) | Never applied; one tap away without a button that changes settings from the chat | A one-tap "Use gentler wording" button (Smriti chose the note) |
| 2026-10-24 | The help card's country is chosen in Settings (same `settings` table); the chat page fetches it on load and the card opens it first, else the time-zone country; `PUT /settings` refused before consent (Smriti) | Planned move from Phase 10; the card itself still makes no request (S12); nothing stored before the notice is accepted | Leaving the country for later |
| 2026-10-24 | `validate_first` accepts formal and gentle acknowledgements ("I understand", "I acknowledge", "You mentioned", "I am glad to hear", "I hear that/how", "It is natural/common to", "It seems", "It might be that you feel", warmth about good news); `no_praise` no longer matches "That is wonderful news" (Smriti, CR-14) | Per-style tone check: formal first drafts failed `validate_first` 30/70 and 25/70 (13/70 default), costing a retry each; four good-news turns fell back. Re-scored drafts: 30 → 18, 25 → 13; every good-news block cleared; curated guard sets unchanged | Leaving the lists (slower formal replies, fallbacks on good news) |
| 2026-10-25 | Bias evaluation scope: CI requires 100% on crisis handoff for every dialect, typo and demographic version, no false handoffs, and identical decisions for every demographic and cultural variant; dialect agreement on non-crisis decisions is measured and reported, lexicons not widened (Smriti) | First run: dialect conversations miss the screening offer standard English gets; widening lexicons for seven dialects is clinical content work of its own | Widening trigger and emotion lexicons, tuned on half the variants |
| 2026-10-25 | Crisis misses in the variant set fixed under S9 (Smriti): "I don't want to live anymore" followed by anything; typos; British, AAVE, Indian English, Pidgin, Hinglish, Spanglish and Taglish phrasing (ruleset 2026.10.1, CR-01, CR-26) | First run: not_live missed whenever a name or sentence followed; Spanish and Tagalog 0/8, Hinglish 3/8, Pidgin 4/8, typos 5/8 | Reporting as defects only |
| 2026-10-25 | Lexicon scores come from the highest-scoring sentence, with a leading "As a ...," / "At 68," clause scored apart (Smriti); explanations decompose that sentence | Rates per word let identity, family and festival words dilute scores: 63 demographic turn mismatches (anger, overwhelm). Sentence scoring keeps one-sentence messages unchanged (full suite passed untouched); a comma split changed calibration and broke a router test | Comma-level clauses; a fixed denominator; reporting only |
| 2026-10-25 | Quality disparity thresholds (Smriti): words ±15% relative, VADER sentiment ±0.10, first drafts passing ±10 points, fallbacks ±5 points; help surfaced: any difference | Moderate: a 4B model's sampling noise alone moves these | Strict (±10%, ±0.05, ±5, ±2) |
| 2026-10-25 | The decision plane is evaluated on the fake model only; the real model runs only the quality groups (standard, 7 dialects, 2 variants per demographic group) | Decisions never read the model's wording; the full grid would take hours on the laptop | Running every variant on the real model |
| 2026-10-26 | Phase 12 squash-merged (PR #11) by request; Phase 13 branched from `main` (Smriti) | Same as Phases 4-11 | Branching from `phase-12-bias-eval` |
| 2026-10-26 | Reference laptop for Phase 13 measurements: the development machine, AMD Ryzen 5 5500U (6 cores / 12 threads), 5.8 GB RAM, Windows 11, CPU only (Smriti; closes open item 7) | Every earlier measurement was made here, so the numbers compare | A separate machine |
| 2026-10-26 | A saved conversation with no message for 90 days is deleted automatically through the existing erasure path; the notice says so (Smriti) | Bounds how long a conversation stranded by cleared site data stays on disk | A recovery code; documenting only |
| 2026-10-26 | Usability checklist: heuristic review (Nielsen's 10, WCAG 2.2 AA) in the browser, small failures fixed in Phase 13, larger ones listed; no participants (O4) (Smriti) | Ethics approval is needed for participant testing | Report only |
| 2026-10-26 | Load and latency are reported on the reference laptop with Chrome and other heavy apps closed (Smriti); the first runs with everything open had 0.2 GB free and the model paged to disk | A clean, repeatable figure for the cost profile | Reporting the busy desktop too |
| 2026-10-26 | The generation timeout starts once the model is free; the wait for it is bounded by the request deadline (`BoundedLLM`); the app passes the bare client and the engine always wraps it | Load test: with one model slot, a message queued behind another lost most of its 20 s budget waiting; two sessions at once timed out | Raising the generation timeout |
| 2026-10-26 | Sentence streaming stays out of v1 after measurement | First sentence 2.0 s sooner at the median, but the guard rejected 4 of 20 first drafts, which streaming would already have shown (`reliability.md`) | Streaming the first sentence |
| 2026-10-27 | Phase 13 squash-merged (PR #12); Phase 14 branched from `main` | Same as Phases 4-12 | Branching from `phase-13-reliability` |
| 2026-10-27 | No PostgreSQL adapter (Smriti; closes open item 6 and PRD O5) | One person per laptop, one process, one SQLite file to export and delete | Building it against the contract suite |
| 2026-10-27 | `llm_queue_limit` default 4 → 2 (Smriti) | Second load run: at 4-8 sessions, 26/54 served and 1 timeout against 20/54 and 22; the extra messages get "busy" at once instead of a 27 s wait (`docs/reports/phase-14.md`) | Keeping 4 |
| 2026-10-27 | Diagram exports by a pinned mermaid-cli (11.17.0) through `npx`, rendered with the installed Chrome or Edge; SVG and PNG committed in `docs/images/` (Smriti) | A docs-only Node tool, not a Python dependency; skipping puppeteer's browser download keeps it to the npm package | A Python renderer; a web rendering service (sends the diagrams out) |
| 2026-10-27 | Install guide runs llama-server with `-hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj -ngl 0` | `-hf` downloads the model in one line; without `--no-mmproj` it also fetches a 0.68 GB vision projector OASIS never uses; the Vulkan build failed to load the model on the integrated graphics | A separate download step; GPU offload |
| 2026-10-27 | Repository licence MIT, copyright Smriti Singh (Smriti; closes open item 3 and PRD O1) | Shortest permissive licence; reuse is the point of a public portfolio project | Apache-2.0 (patent grant, NOTICE); AGPL-3.0 |
| 2026-10-27 | Self-harm without suicidal intent keeps the full crisis handoff and post-crisis mode (Smriti; closes open item 9) | Safe default until clinician review: over-referring costs less than a miss | A softer self-harm reply without post-crisis mode |
| 2026-10-27 | Fresh held-out crisis set in two stages: phrases written blind by people outside the project, then a published research dataset under a data-use agreement and ethics approval (Smriti) | People are free and quick; a research dataset is more realistic but needs approvals | Waiting for the clinician |
| 2026-10-28 | A test version is shared by link from a 32 GB computer running the real model, through a Cloudflare quick tunnel, in demo mode: `OASIS_DEMO=1` keeps every conversation in memory (the server refuses to save), shows `disclosure_demo.yaml` and a "made-up messages only" banner on every page (Smriti) | Real replies at no cost; the tunnel needs no open port and OASIS stays on loopback | Render free (512 MB: stand-in model only); Hugging Face Docker Space (needs PRO, $9/month; a private Space cannot be opened by testers without accounts) |
| 2026-10-28 | Request bodies are counted as they arrive (`BodyLimit`), not only by `Content-Length`; unsaved conversations are capped at 1000 (`max_ephemeral_sessions`), beyond that "busy" | A public link: a chunked body or a flood of new sessions could otherwise grow memory without bound | Rate limiting per client (needs the client's address behind the tunnel) |
| 2026-10-29 | Threats to someone else are a crisis: new `harm_others` tier, same handoff path (no model call, post-crisis mode, help card opened) with its own reply that names the emergency number; reported speech triggers too (Smriti) | Demo testers wrote "i want to kill mess chef" and "Feeling to die" and got ordinary companion replies. A false alarm is safer than a miss (rules S6) | Treat it as an ordinary message; or show a warning and carry on the conversation |
| 2026-10-29 | Valence keeps VADER with four fixes: comparison "like" and "hand" score nothing, a negated bad word and a good word after "over"/"too" are neutral (Smriti) | Demo testers' negative messages showed as positive in the mood trend ("life is no horrible" +0.35, "feels like ... over enthusiastic" +0.80); the fix is in valence, so routing gets it too; bias evaluation output unchanged | Spelling correction: one-edit matching against VADER's word list misread real words (brother → bother, morning → mourning) without a dictionary, so dropped |
| 2026-10-29 | Companion replies sometimes only listen: when asked, after 2 question replies in a row, or after a 40+ word message; the engine strips question sentences instead of retrying (Smriti) | A demo tester: "When I am feeling sad you are asking me how much sad". Stripping keeps the model's reflection and costs no second model call (~5-25 s each on the host) | A fixed cadence only; a cue only; a guard retry (slower, and the 4B model kept asking) |
| 2026-10-29 | New chat: a button starts another session of the same user (`POST /session/new`); Mood trend graphs each conversation; earlier conversations are not reopened in the chat (Smriti) | Demo testers wanted a fresh conversation each day, with its own graph. One user, many sessions already fit the data model and the trend aggregation | A new chat every day automatically; a conversation list to reopen earlier ones (more UI and privacy questions; later if asked) |
| 2026-10-29 | Short acknowledgements: a statement of 5 words or fewer (not a question, not the first message) gets one sentence, no question (Smriti) | Testers answered "food", "MOTHER", "LIFE" and got a paragraph each time | A fixed cadence (every third reply short); short only when asked |
| 2026-10-29 | Every 4th reply to someone describing a difficulty offers one small idea with hopeful encouragement; "stay positive"-style phrases are rejected on every reply (Smriti) | Testers wanted suggestions and encouragement to keep a positive attitude; telling someone low to stay positive tends to read as dismissing them, so the encouragement is hope that leaves the feeling alone | Literal "keep a positive attitude"; ideas only when asked (the previous rule) |
| 2026-10-13 | A companion reply to a thinking-trap message that fails twice gets the Socratic bank question for that trap, not the companion fallback (Smriti) | The design's reroute: validate the feeling, then one Socratic question | Companion fallback in every companion turn |
| 2026-10-11 | Psychoeducation cue is a `psychoed` scorer in `cues.yaml` (no `psychoed/cues.py`); reading level is a stdlib Flesch-Kincaid check at startup (no `scripts/readability.py`) | Reuses the Phase 4 scorer; bad content fails at boot | Separate cue module; a printing script |
| 2026-10-09 | `main` branch protection: both `verify` CI jobs required; admins exempt; force-push and deletion blocked; auto-merge allowed | Nothing merges without CI; emergency direct pushes still possible | Required reviews (a solo owner cannot approve own PRs) |
| 2026-10-07 | Git: commits authored as Smriti; no assistant attribution anywhere; assistant config files git-ignored; Conventional Commits; one branch per phase | Authorship and repository hygiene | — |

---

## Open items / questions for Smriti

8. **Browser check of crisis lines** that could not be fetched here, to promote them to Tier 1: Philippines NCMH 1553, Chile *4141, Colombia 192 option 4, Pakistan Umang, and Sweden's Mind line hours. 2026-10-27: NCMH 1553, 24/7, confirmed on a DOH page (caro.doh.gov.ph), but as toll-free by landline, Luzon-wide; the nationwide and mobile numbers are on the NCMH contact page. Sweden: already Tier 1 (90 101); its hours, 24/7 every day, free apart from the operator's connection fee, confirmed on mind.se and added (resources 2026.10.1, CR-04). Chile *4141: minsal.cl blocks this network outright and gob.cl, pia.gov.ph and ncmh.gov.ph stay on a bot check, even in a normal Chrome; needs another network or someone in-country. Colombia 192 option 4: official sources only from 2020-21, current status unconfirmed. Umang: sources disagree on the number and umang.com.pk did not resolve; keep Tier 2.
9. ~~Confirm the `self_harm` tier~~: resolved 2026-10-27, kept: self-harm gets the full handoff; still flagged for the clinician (CR-01).
10. **A fresh external held-out phrase set**: the Phase 2 held-out set was used for tuning and is now consumed. Plan (2026-10-27): first, 2-3 people outside the project write crisis and everyday messages blind (about 100 each), run once and never tuned on; second, a published research dataset once a data-use agreement and ethics approval (item 5) allow it.
11. ~~Saved conversations after the tab closes~~: resolved 2026-10-24, the saved session's key is kept in `localStorage` (rules F5 changed).
2. **Python 3.12 and uv** need installing on the development machine.
3. ~~Repository licence~~: resolved 2026-10-27, MIT (`LICENSE`).
4. **Clinician reviewer** for `clinical_review.md`.
5. **Ethics approval** route for any future usability testing with participants.
6. ~~Optional PostgreSQL adapter~~: resolved 2026-10-27, not built.
7. ~~Reference laptop specs~~: resolved 2026-10-26, the development machine (Ryzen 5 5500U, 5.8 GB RAM).

---

## Known limitations and "not verified here"

| Item | Status |
|---|---|
| Real-model speed (first-token time, tokens/sec, RAM) | Measured 2026-10-26 on the reference laptop (`docs/reports/reliability.md`): one session 8.8 s median warm, 20 s cold; first token 0.8 s; llama-server commits 4.1 GB but only 0.25 GB stays in RAM next to a desktop app |
| Real-model reply + thinking disabled | Not verified here — `scripts/model_smoke_test.py` |
| llama.cpp build pin | Build 11552 (commit `23b0202a1`), winget, recorded 2026-10-27 |
| Real-model tone (companion, guard, bias quality) | Not verified here |
| Qwen3.5 thinking-disable mechanism and sampling settings | To be re-verified against the current model card in Phase 1 |
| Model licences (Qwen3.5, Gemma 4, Phi-4-mini) | Qwen3.5-4B (and the unsloth GGUF) Apache-2.0 on the Hugging Face card, 2026-10-27; Gemma 4 and Phi-4-mini not re-checked (not shipped) |
| PHQ-9 / GAD-7 item wording | Verified 2026-10-08 against the official phqscreeners.com forms and instruction manual |
| Router detector accuracy on natural messages | Not measured; scenario table and golden phrases only — needs a labelled set |
| Psychoeducation cue recall on unseen phrasing | Not measured; trigger set written by the same author as the cues — needs a fresh labelled set |
| Real-model phrasing of psychoeducation items | Not verified here (fake LLM returns the item verbatim) |
| Real-model companion tone | Measured 2026-10-11 on the dev machine (12 single-turn samples); transcript `docs/reports/phase-06-tone-check.md` awaits Smriti's review; multi-turn variety (same opener) not yet measured |
| Real-model phrasing of exercise steps | Not verified here (fake LLM returns steps verbatim) |
| Screening-offer trigger on unseen conversations | Precision 1.00 / recall 0.93 on the labelled set after tuning (0.80 / 0.31 before); needs a fresh labelled set |
| Crisis resource numbers | Verified 2026-10-08 against official sources (Tier 1) and FCDO (Tier 2); re-verify before any participant use |
| Post-crisis flag after an app restart with storage down | Falls back to normal mode (documented, CR-05) |
| Gate latency on dense 2 000-character input | 10–35 ms on battery, over the 10 ms target; realistic messages p99 0.55 ms; combined pre-filter is the upgrade path |
| Crisis detection recall on unseen phrasing | 88.7% on the held-out set before tuning; needs a fresh external set |
| English-only; no fine-tuning; WEIRD-data caveat | By design for v1; stated in the README's Limitations (Phase 14) |
| Install on a second computer, macOS, Linux | Not verified here: the Phase 14 check was a clean clone with empty uv caches on the reference laptop (Windows) |
| Explanations with real-model replies | Not verified here (browser check ran with llama-server down, so replies were fallbacks); the explanation does not read the reply text |
| Which words drove VADER valence | Not explained; valence enters the router explanation as one exact contribution |
| Saved conversation in the browser | Key in localStorage (rules F5, 2026-10-24): anyone using the browser can open it; clearing site data strands it on disk until it expires, 90 days after the last message (Phase 13) |
| Erasure beyond SQLite | OS swap, SSD wear levelling and backups are outside OASIS; disk encryption recommended in the notice |
| Real-model effect of each style | Measured 2026-10-24 (4 styles x 70 turns, `docs/reports/phase-11-tone-*.md`): gentle and formal followed, direct and casual weakly; formal fails `validate_first` more (phrase list) and good news under a style hits `no_praise` ("That is wonderful news"); both await Smriti |
| Hedge list recall | Not measured (no labelled hedged set); fires on 2/104 labelled conversation turns, 0 suggestions in 24 conversations |
| Dialect and code-mixed text | Written by the engineering author, not native speakers (CR-26); crisis phrasing for 7 dialects fixed from a set that was then used for tuning, so its 100% is not an unbiased estimate |
| Dialect non-crisis decisions | Not invariant by decision (Smriti, 2026-10-25): 19-23 of 25 turns match standard English; screening offers missed (docs/reports/bias_eval.md) |
| Identity stated mid-sentence | Still dilutes scores ("I'm a Sikh man and ...", "Being a single mum, ..."): 15 held-out turns differ |
| Reply quality by group | One real-model run of 25 turns per group; standard English alone varied 50-68% first drafts passing and +0.08 to +0.20 sentiment over four runs, so gaps under about 20 points are not detectable here |
| Queue depth | Resolved 2026-10-27: `llm_queue_limit` 2 after a second load run (one run per limit, small samples) |
| Timing tests on battery | The explanation latency test (20 ms) measured 33-39 ms unplugged on 2026-10-26, `main` included; it passes plugged in |
| Guard checks outside English | `validate_first` lists English acknowledgements only: Spanglish first drafts 4-12% pass (retried, 0% fallbacks, longer waits) |

---

## Measured results

| Date | Phase | Measure | Result |
|---|---|---|---|
| 2026-10-07 | 1 | Tests | 121 passed, 0 skipped |
| 2026-10-07 | 1 | Coverage | 98.73% overall; `oasis.safety` 100% |
| 2026-10-07 | 1 | Mutation spot-check | 5/5 deliberate faults caught |
| 2026-10-07 | 1 | SQLite turn-pair write (dev machine) | p50 0.55 ms, p95 0.94 ms, p99 1.80 ms |
| 2026-10-07 | 1 | SQLite last-6-turns read (dev machine) | p50 0.22 ms, p95 0.40 ms, p99 0.50 ms |
| 2026-10-07 | 2 | Held-out crisis recall (before tuning) | 63/71 = 88.7% |
| 2026-10-08 | 2 | Tests | 481 passed, 0 skipped |
| 2026-10-08 | 2 | Benign false positives | everyday 0/50; idioms 0/30; third-party mentions 4/5 (by design) |
| 2026-10-08 | 2 | Gate latency (battery) | realistic p99 0.55 ms; 2 000-char stress inputs 10–35 ms |
| 2026-10-08 | 3 | Tests | 592 passed, 0 skipped |
| 2026-10-08 | 3 | Coverage | 97.5% overall; `oasis.assessment` 99.0%; `oasis.safety` 97.1% |
| 2026-10-08 | 3 | Trigger (24 labelled conversations) | before tuning P 0.80 / R 0.31; after P 1.00 / R 0.93, mean latency 0.85 turns |
| 2026-10-08 | 3 | Mutation spot-check | 13/13 caught after two new tests (11/13 before) |
| 2026-10-11 | 4 | Tests | 799 passed, 0 skipped |
| 2026-10-11 | 4 | Coverage | 98.1% overall; `oasis.router` 100%, `oasis.assessment` 98.6%, `oasis.safety` 97.1% |
| 2026-10-11 | 4 | Scenario table / stability | 34/34 rows; 0 mode changes over 12 alternating strong cues |
| 2026-10-11 | 4 | Signals + routing latency (dev machine) | p50 0.24 ms, p99 0.52 ms; 2 000-character message 14 ms |
| 2026-10-11 | 4 | Mutation spot-check | 15/15 caught on the first run |
| 2026-10-11 | 5 | Tests | 882 passed, 0 skipped |
| 2026-10-11 | 5 | Coverage | 98.1% overall; `oasis.psychoed` 100%, `oasis.router` 100% |
| 2026-10-11 | 5 | Psychoeducation cue | trigger set 23/23 fire with the expected item; false positives 0/22 near-miss ordinary messages, 0/104 Phase 3 conversation turns, 0/85 Phase 2 benign messages |
| 2026-10-11 | 5 | Planner latency (dev machine) | p50 0.28 ms, p99 0.47 ms |
| 2026-10-11 | 5 | Mutation spot-check | 10/10 caught after one new test (9/10 before) |
| 2026-10-11 | 6 | Tests | 975 passed, 0 skipped |
| 2026-10-11 | 6 | Real-model tone check (Qwen3.5-4B Q4_K_M, llama.cpp b11552, dev machine) | Final run 10/12 first drafts pass, both rejections genuine; 0 fallbacks in every run; 4.7–6 s per reply after a 15.7 s first reply |
| 2026-10-11 | 6 | Coverage | 98.2% overall; `oasis.guard` 100% |
| 2026-10-11 | 6 | Companion checks | 12/12 curated good replies pass; 21/21 curated bad replies fail with exactly the labelled rules; guard fallback and the fake model's replies pass |
| 2026-10-11 | 6 | Mutation spot-check | 11/11 caught after one test rewrite (10/11 before); opener and soft-rule round 9/9 after one test fix (8/9 before) |
| 2026-10-12 | 6 | Conversation tone check (real model, 48 turns) | Fallbacks 5/48 -> 0/48; repeated openers in conversations 8/18 -> 4/18; first drafts passing 41/48 -> 38/48 |
| 2026-10-12 | 6 | Screening trigger with k = 2 (24 labelled conversations) | Precision 1.00 -> 0.93, recall 0.93 -> 1.00 (TP 13, FP 1 too early, FN 0, TN 10); mean offer latency 0.85 -> 0.23 turns |
| 2026-10-13 | 7 | Guard, curated sets (used for tuning) | First run 49/50 caught, 2/50 blocked; after tuning 50/50 caught, 0/50 blocked |
| 2026-10-13 | 7 | Guard, held-out set (never tuned against) | 14/15 caught (93.3%), 0/15 blocked; miss: "horrible person" not in the labelling lexicon |
| 2026-10-13 | 7 | Tone check (real model, 63 turns, before the manual-testing changes) | First drafts passing 40/63; fallbacks 1/63; thinking traps: 0/14 drafts agreed (1 went to crisis); both Phase 7 hits were refusals |
| 2026-10-13 | 7 | Mutation spot-check | 13/15 at first (fact-statement agreement off; bank ignoring the turn); tests added; 16/16 |
| 2026-10-13 | 7 | Tests / coverage | 1125 passed; 98.4% overall (guard 99%, router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-13 | 7 | Tone check, final (real model, 70 turns, after closing the limits) | First drafts passing 46/70; fallbacks 2/70 (both model timeouts, 0 guard fallbacks); thinking traps 0/14 drafts agreed; STOP steps exact; repeated openers 2/18 |
| 2026-10-13 | 7 | Guard stress check (model told to agree, 15 thinking traps) | Before the strong-agreement fix: 3 drafts caught, 2 leaks ("I agree with you that...", "you are right to want..."); after: both gone, 0 fallbacks; 2 replies agree with the feeling in other words |
| 2026-10-13 | 7 | Tests / coverage (final) | 1157 passed; 98.5% overall (router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-13 | 7 | llama-server memory | Default 8 GiB prompt cache: grew to ~12 GB on the 6 GB laptop and crashed; `--cache-ram 0`: 4.2 GB, 7.4-8.9 tokens/s steady |
| 2026-10-20 | 8 | Tests / coverage | 1209 passed; 98.5% overall (tracking 100%, router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-20 | 8 | Mutation spot-check | 11/12 at first (latency from any turn); test added; 12/12 |
| 2026-10-20 | 8 | Feature and trend speed (dev machine) | Features p50 0.031 ms, p99 0.047 ms per message; trend over 1,000 stored messages p50 51 ms (page open only) |
| 2026-10-22 | 9 | Tests / coverage | 1291 passed; 98.57% overall (explain/builder 100%, shap_values 95%, router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-22 | 9 | Explanation exactness (615 test-data messages x 22 scorers) | Additivity error at most 2.2e-16 (limit 1e-6); 615/615 `ok`; largest difference from `shap.LinearExplainer` 0.0; 615/615 byte-identical on rebuild |
| 2026-10-22 | 9 | Explanation speed (dev machine) | p50 1.1-1.4 ms, p99 2.3-2.6 ms per reply; 1,840-character message 14.6-15.5 ms (32 ms before counting matches once); record median 827 bytes |
| 2026-10-24 | 10 | Tests / coverage | 1375 passed; 98% overall (storage 97-99%, router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-24 | 10 | Export / delete (dev machine, SQLite) | Export 2.4 ms / 100 turns, 10.9 ms / 1,000 turns (533 KB); delete with checkpoint 10.2 ms / 22.3 ms; expiry check 2 us (10 unsaved sessions) to 108 us (1,000) per request |
| 2026-10-24 | 10 | Erasure | Schema crawl 0 rows; marker absent from .db and -wal; WAL 0 bytes; a reader mid-read blocked the checkpoint silently (busy, no error) until the fix |
| 2026-10-24 | 10 | Mutation spot-check | 23/25 at first (expiry check hid by the test's own lookup; startup overwrite masked by SQLite's last-connection checkpoint); two tests tightened; 25/25 |
| 2026-10-24 | 11 | Tests / coverage | 1443 passed; 98.42% overall (style 100%, router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-24 | 11 | Tone check per style (real model, 70 turns each) | First drafts passing: direct+casual 50, direct+formal 31, gentle+casual 45, gentle+formal 39 (default 46); fallbacks 2/0/2/3, 5 of them guard fallbacks (4 good news, 1 medication refusal) |
| 2026-10-24 | 11 | Invariance | 25 generated conversations x 9 styles: identical verdicts, modes, cards, plans, explanations and replies; 9/9 distinct prompts |
| 2026-10-24 | 11 | Mutation spot-check | 16/17 at first (button-press test hit a fixed reply); test tightened; 17/17 |
| 2026-10-24 | 11 | Speed (dev machine) | Settings read (SQLite) p50 0.42 ms, p99 0.81 ms; suggestion check p50 0.05 ms; longest style line 183 chars (~52 tokens) |
| 2026-10-25 | 12 | Tests / coverage | 1536 passed; 98.42% overall (router 100%, assessment 97.8%, safety 97.1%) |
| 2026-10-25 | 12 | Crisis handoff, every version (8 items x 34 versions) | Before 223/272 (Spanglish 0/8, Taglish 0/8, Hinglish 3/8, Pidgin 4/8, typos 5/8; 15 standard-English suffix misses); after 272/272, plus 64/64 held-out identity phrasings |
| 2026-10-25 | 12 | Demographic and cultural invariance | Before 78 mismatches (15 crisis, 63 conversation turns); after 0. Held-out identity phrasings 24 -> 15 differing turns (reported) |
| 2026-10-25 | 12 | Dialect agreement (reported) | Turns with the standard decisions: British 21/25, AAVE 23/25, other five 19/25; the low-mood screening offer missed in every dialect |
| 2026-10-25 | 12 | Safety evaluation after ruleset 2026.10.1 | Held-out 71/71, train 72/72, benign false positives unchanged; gate p99 5.6 ms (4.7 ms before) |
| 2026-10-25 | 12 | Reply quality (real model, 25 turns per dialect, 50 per demographic group) | Demographic groups within standard's run-to-run spread (standard first drafts 68/59/50/55%, sentiment +0.08 to +0.20 over four runs); Spanglish first drafts 4% and 12% (`validate_first`, English-only), Taglish 32% and 24% shorter; help surfaced 0-16% in dialects vs 24% (decision plane) |
| 2026-10-25 | 12 | Mutation spot-check | 10/14 at first (false handoffs in variant runs, conversations not compared, Spanish hair-cut exclusion; one equivalent); three tests added; 13/13 non-equivalent |
| 2026-10-26 | 13 | Tests / coverage | 1619 passed, 0 skipped; 98.42% overall; safety 97.7%, assessment 97.8%, router 100%; verify all 8 steps pass |
| 2026-10-26 | 13 | Everything except the model (fake model, 600 requests) | 10 / 12 / 18 ms p50 / p95 / p99 (target 150 ms p95) |
| 2026-10-26 | 13 | Concurrent sessions, real model, quiet machine | Warm: 3 at once with every request served (slowest 26 s); cold: 2. Busy desktop after the queue fix: 2 / 3 / 4 sessions served 6/6, 8/9, 9/12 (5/6, 3/9, 2/12 before) |
| 2026-10-26 | 13 | Streaming (measured, not built) | First token 0.8 s, first sentence 2.7 s, whole reply 5.1 s (p50); 4/20 first drafts rejected by the guard |
| 2026-10-26 | 13 | Usability | 10 Nielsen heuristics and 9 WCAG 2.2 AA checks pass after five fixes; contrast 33/33 pairs (26 before) |
| 2026-10-26 | 13 | Mutation spot-check | 14/15 at first (bare client not bounded: the app always passed it wrapped); the app now passes it bare; 15/15 |
| 2026-10-27 | 14 | Tests / coverage | 1623 passed, 0 skipped; 98% overall; safety 97.7%, assessment 97.8%, router 100%; verify all 8 steps pass |
| 2026-10-27 | 14 | Install from a clean clone (empty uv caches, reference laptop) | Clone 15 s; `uv sync` 295 s (Python 3.12.15 and 88 packages); 352 MB packages + 68 MB Python + 2.74 GB model; app serves, one message answered; verify passes in the clone (1619 tests, `main`) |
| 2026-10-27 | 14 | Real model from the README line | Loaded from cache in 8 s with `--no-mmproj -ngl 0`; smoke test PASS, 21 / 13 / 11 s cold |
| 2026-10-27 | 14 | Queue limit 4 against 2, 4-8 sessions | Served 20/54 against 26/54; timed out 22 against 1; busy 12 against 27 (median 0.1 s); every request served up to 2 sessions in both, 3 with queue 4 |
| 2026-10-22 | 9 | Mutation spot-check | 15/20 at first (negative score not clipped, button-turn test vacuous, unsorted keys, ID for an unsaved reply; one redundant ID check); four tests added, the check removed; 19/19 |
| 2026-10-09 | UI | Tests / coverage | 594 passed; 97.6% overall (safety 97.1%, assessment 98.6%); first CI runs green on Ubuntu and Windows |
| 2026-10-08 | 2 | Mutation spot-check | 12/12 caught after adding the help card escaping test (11/12 before) |
| 2026-10-08 | 2 | Coverage | 98.09% overall; `oasis.safety` 97.13% |

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
