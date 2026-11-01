# OASIS build and evaluation report

This report records what each of the fourteen build phases added, how it was evaluated and what was measured. It replaces the separate phase reports, the reliability and bias reports, the usability checklist and the build plan. The four ML models added afterwards are documented in [ml_models.md](ml_models.md).

Two rules apply to every number below.

- Test sets were written and committed before the rules they test. The first measurement on each set is the honest one and is reported as "first run". Once a set had been used to guide a fix, later scores show coverage of known cases, not accuracy on new ones.
- No real users took part. Testing with people needs ethics approval (open item O4). All sets are synthetic and were written by the developer, and real-model results come from one model in small runs.

The reference laptop is an AMD Ryzen 5 5500U (6 cores, 12 threads) with 5.8 GB of usable memory, Windows 11, CPU only. The model is Qwen3.5-4B, GGUF Q4_K_M, on llama.cpp build 11552.

## Summary

| Phase | What it added | Key result |
|---|---|---|
| 1 | Core chat loop: request path, deadlines, fallbacks, storage | Every failure path returns a reply; storage costs about 1 ms per turn |
| 2 | Safety layer and crisis handoff | Held-out crisis recall 88.7% on first run; 0 false positives on 80 everyday and idiom messages |
| 3 | PHQ-9 and GAD-7 screening | Offer trigger precision 1.00, recall 0.93 after tuning (0.80 and 0.31 first run) |
| 4 | Signals, therapy router, exercises | 34/34 scenario rows; 0 mode changes over 12 alternating strong cues |
| 5 | Psychoeducation | 0 false triggers on 211 ordinary messages |
| 6 | Companion mode checks | Real-model fallbacks 5/48 to 0/48; repeated openers 8/18 to 4/18 |
| 7 | Hypercompliance guard | Held-out sycophantic replies caught 14/15 (93.3%), benign blocked 0/15 |
| 8 | Language-based mood trend | 12/12 mutation faults caught after one new test |
| 9 | Explainability | Additivity error at most 2.2 x 10^-16 over 615 messages; byte-identical rebuilds |
| 10 | Consent, unsaved mode, export, delete | Deleted text absent from the database and WAL files |
| 11 | User-set communication style | Decisions identical under all 9 styles |
| 12 | Bias evaluation | Crisis handoffs 223/272 to 272/272; demographic mismatches 78 to 0 |
| 13 | Reliability and usability | Every fault-matrix row answered within the timeout; non-model path 18 ms p99 |
| 14 | Cost and access | Clean install in about 5 minutes plus the model; 2 people at once fully served |

Every phase ended with all eight checks of `scripts/verify.py` passing: ruff lint, ruff format, mypy strict, import-linter, bandit, pip-audit, the test suite with coverage, and the critical-package coverage threshold. The suite grew from 121 tests (Phase 1) to 1,623 (Phase 14), and overall branch coverage stayed between 97.5% and 98.7%. Each phase also ran a mutation spot-check: across Phases 1 to 13, 172 of 194 deliberate faults were caught on the first run, and every missed fault except one equivalent mutant led to a new test.

## Phase 1: Core chat loop

Built. The full request path exists with every decision component as a hook. The engine calls the safety gate before any storage method, so a crisis is answered even from an unknown session. The safety wrapper fails closed; every other stage fails soft, so a storage error gives a stateless reply, and a planner or model error gives a templated reply. The engine sets a deadline at 90% of the request timeout and gives each model call only the remaining time, and a bounded queue returns "busy" at once when full. Hidden reasoning is disabled and any `<think>` text is stripped from every draft. One repository protocol has an SQLite and an in-memory implementation that pass the same contract tests.

Results.

| Check | Result |
|---|---|
| Tests, coverage | 121 passed; 98.73% overall, `oasis.safety` 100% |
| Mutation spot-check | 5/5 caught (storage read moved before safety, safety failing open, unterminated `<think>` kept, queue off by one, user scoping removed) |
| SQLite, 1,000 turns | Write p50 0.55 ms, p99 1.80 ms; read last 6 turns p50 0.22 ms, p99 0.50 ms |
| Browser | History survives a page reload and a server restart; the help card opens with the server stopped; no message text in logs |

Known limits. The prompt budget used a character estimate at this stage. The body-size limit trusted `Content-Length` until Phase 14 counted bodies as they arrive.

## Phase 2: Safety layer

Built. The normaliser applies NFKC, strips invisible characters, folds case and look-alike letters, removes apostrophes and collapses stretched letters, then produces up to four variants (base, leetspeak undone, spaces removed, both). Tiered rules (explicit, passive, plan or method, burden, self-harm) match against every variant. There is no negation suppression; an idiom on the allow-list removes a hit only when its span covers the hit. Invalid rule files or a failing rule example stop the app at startup, and any exception at turn time becomes a crisis verdict. The handoff is compiled-in text with zero model calls. Crisis resources cover 224 countries and territories: 40 with a verified crisis line (Tier 1) and 184 with the emergency number from UK travel advice (Tier 2). The "Need help now?" card is server-rendered HTML that works with the server stopped. After a handoff, post-crisis mode gives fixed supportive replies until the user chooses to continue.

Results.

| Check | Result |
|---|---|
| Held-out recall, first run | 63/71 (88.7%) |
| Training set recall | 72/72 |
| Benign false positives | Everyday 0/50; idioms 0/30; third-party mentions 4/5 (by design) |
| Gate latency | Realistic messages p50 0.20 ms, p99 0.55 ms; dense 2,000-character inputs 10 to 35 ms |
| Tests, coverage | 481 passed; 98.09% overall, `oasis.safety` 97.13% |
| Mutation spot-check | 11/12 first run; the miss (help card not escaping names) got a test |

Known limits. Rule-based matching misses phrasing nobody foresaw; 88.7% is the only unbiased figure for this ruleset. Long dense input exceeds the 10 ms latency target; a combined pre-filter is the upgrade path. English only. Post-crisis state falls back to normal mode after a restart with storage down (CR-05). Twenty-four target countries stayed at Tier 2 because their official pages could not be fetched.

## Phase 3: Screening questionnaires

Built. PHQ-9 and GAD-7 items, options and bands were checked word for word against the official phqscreeners.com forms; GAD-7 asks no functional question because its form has none. A state machine handles offer, consent, items, pause, resume, stop and expiry, and `score()` raises unless every item has a 0 to 3 answer. Database CHECK constraints back this up. Answers are buttons that send their label as text, so the safety gate still sees them. A PHQ-9 item 9 answer of 1 or more triggers the crisis handoff before any storage call. A questionnaire is offered only when readiness (a decaying mean of symptom evidence over six user turns) stays at or above 0.45 for two turns in a row, or on an explicit request. Unprompted offers are blocked after a decline in the last 24 hours, a completion in the last 10 days, or an open questionnaire.

Results on 24 labelled conversations (14 should offer, 10 should not):

| Version | Precision | Recall | False offers |
|---|---|---|---|
| First run | 0.80 | 0.31 | 1/10 |
| After tuning, 3 turns required | 1.00 | 0.93 | 0/10 |
| Current, 2 turns required | 0.93 | 1.00 | 1/10 (one turn early) |

Tests 592 passed; `oasis.assessment` 99.0%. Mutation spot-check 11/13 first run; the misses (item 9 tested only with the value 3, no test of sustained third-person symptoms) got tests.

Known limits. Trigger quality on real conversations is unmeasured; the tuned figures come from the tuning set. Short conversations rely on an explicit request. English only. CR-07 to CR-10 await review.

## Phase 4: Signals, therapy router and exercises

Built. Lexicon scorers compute `clip(b + k * sum(w_i * n_i / T), 0, 1)` over the normalised text for emotions, dysregulation, overwhelm, wanting to talk, opting out and Burns's eleven distortion categories; VADER gives valence. The router scores each mode as a bias plus weighted signals, returning every contribution. Overwhelm at or above 0.6 goes straight to grounding. Otherwise a mode must lead the runner-up by 0.15 for two turns in a row (three until 2026-10-12), and a structured mode is offered, never entered. One low-risk exercise per mode runs one step per message: Thought check (CBT), STOP skill (DBT), Notice the breath (mindfulness) and 5-4-3-2-1 senses (grounding).

Results. Scenario table 34/34 (30 scored rows plus 4 acute). Twelve turns of alternating strong CBT and DBT cues gave 0 mode changes and 0 offers. Contribution additivity held on every property-test example. Signals plus routing took p50 0.24 ms, p99 0.52 ms. Tests 799 passed; `oasis.router` 100%. Mutation spot-check 15/15 first run.

Known limits. Detector accuracy on natural messages is not measured. Lexical cues miss paraphrases and are diluted in long messages. "I want to stop smoking" typed mid-exercise ends the exercise, which fails safe. Weights and scripts await review (CR-11, CR-12, CR-20).

## Phase 5: Psychoeducation

Built. A cue detects "what's wrong with me" questions, diagnosis questions and stigma statements. Eleven items, each paraphrasing one NHS or WHO page that was fetched to confirm it, carry source, reading level, version and review status. The first unshown matching item wins, else the general item; the model rewords it and the item text is the fallback. Startup rejects any item above Flesch-Kincaid grade 8. Acute overwhelm skips psychoeducation.

Results. Trigger set 23/23 with the expected item. False positives: 0/22 near misses, 0/104 unseen conversation turns, 0/85 unseen benign safety messages. Reading grades 4.2 to 8.0. Tests 882 passed; `oasis.psychoed` 100%.

Known limits. The same author wrote the trigger set and the cues, so 23/23 shows coverage, not accuracy. A message touching two topics gets the earlier one in file order. Items await review (CR-13).

## Phase 6: Companion mode

Built. Every generated reply passes `check(draft, plan)`. Companion replies must acknowledge before asking (`validate_first`), end with exactly one question (`one_question`) and avoid the last three openers (`fresh_opener`); these form rules are soft, so a draft failing only them is kept after its retry. Praise, unasked-for advice and dependency language are hard rules; two failures give the fallback "I hear you. What feels most important to talk about right now?". An advice request swaps `no_advice` for `offer_ideas`.

Results.

| Check | First run | Final |
|---|---|---|
| Curated replies | 12/12 good pass; 21/21 bad fail with their labelled rules | same |
| Real model, 48 turns: fallbacks | 5/48 | 0/48 |
| Real model: repeated openers in conversations | 8/18 | 4/18 |
| Real model: first drafts passing every check | 41/48 | 38/48 (repeats now count as faults) |

Manual testing changed the prompt: small talk had received inflated feelings ("hi, how are you?" got "It takes courage to share that"), so the system text now says to keep small talk light and never make a feeling bigger or darker. Tests 975 passed; `oasis.guard` 100%.

Known limits. Openers still repeat in 4 of 18 conversation replies. Phrase lists miss praise or advice in unlisted words, and validation in unlisted words costs a retry. "Exactly one question" counts question marks. Lists await review (CR-14).

## Phase 7: Hypercompliance guard

Built. When a message holds a thinking trap, signals extract the claim as content words ("I'm such a failure" becomes {failure}) and the planner adds `no_agreeing` and the Socratic rules. A reply sentence echoes a claim when it repeats at least 60% of its content words. `no_agreeing` fails an echo with an agreement marker or stated as fact, and "you're right" or "I agree with you" on a trap or medication message. Further rules reject presupposing advice, harsh labels (a listed word, or an adjective scoring at or below -0.3 on VADER before a person word), diagnosis, medication advice, invented exercise steps and blank drafts. A refusal in the form "I can't tell you if you have depression" passes. After two hard failures, a trap turn or any CBT or DBT turn gets a question from a bank of 25 (two per trap, three general).

Results.

| Set | Sycophantic caught | Benign blocked |
|---|---|---|
| Curated, first run | 49/50 | 2/50 |
| Curated, after tuning | 50/50 | 0/50 |
| Held out, first run (never tuned on) | 14/15 (93.3%) | 0/15 |

The targets set before building were at least 90% caught and at most 5% blocked. With the real model (70 turns), 0 of 14 thinking-trap drafts agreed, labelled or presupposed, and there were 0 guard fallbacks. A stress run with the model told to agree leaked two replies before the strong-agreement rule and none after. Exercise steps are now appended word for word after one model sentence, because the 4B model rewrote "T is for Take a step back" as "N is for Name what you are feeling". llama-server now runs with `--cache-ram 0`; the default cache grew to about 12 GB and crashed the server. Tests 1,157 passed.

Known limits. The guard is phrase-based, so agreement in unlisted words passes; the ML models doc adds an NLI check for this. The medication rule can block a reply that only reflects the question, costing a retry. About 10 s per reply on the 6 GB laptop. Lists await review (CR-15, CR-16).

## Phase 8: Mood trend

Built. Each typed user message records numbers only: VADER valence, first-person pronoun rate (I, me, myself, excluding "my" as Tackman et al. 2019 found), absolutist word rate (19 words, skipping a word after a negation), emotion scores, length, reply latency capped at 600 s, and local hour. Sessions get mean and sample variance; the trend is an EWMA over session mean valence with weight 0.3; a session is flagged when at least five earlier sessions exist and its mean is more than 1.5 SD from theirs. The page always shows "language-based mood trend, not a clinical measure". Button presses and crisis messages are not recorded.

Results. Golden features, synthetic timelines and the flag edges all pass. Features take p50 0.031 ms per message; the trend over 1,000 messages takes 51 ms on page open. Tests 1,209 passed; `oasis.tracking` 100%. Mutation spot-check 11/12 first run.

Known limits. Every feature describes word choice, not mood. The absolutist list comes from secondary sources quoting the paper's table. Thresholds are engineering defaults (CR-21).

## Phase 9: Explainability

Built. Each lexicon scorer is linear before its clip, so SHAP values have a closed form: `phi_i = c_i (x_i - E[x_i])`, `base = b + sum(c_i E[x_i])`, with E taken over 30 neutral background sentences. The `shap` package is a development dependency used only as a test oracle. The router is an exact weighted sum, so its breakdown needs no estimation. The record holds the plan, the router breakdown, the detectors that fired and the guard outcome, sorted for byte-identical output and free of user words. A failure stores "unavailable" and leaves the reply unchanged. Explanations now sit on the "Why replies" page.

Results over 615 test-data messages and 22 scorers: largest additivity error 2.2 x 10^-16 (limit 10^-6); largest difference from `LinearExplainer` 0.0; 615/615 byte-identical on rebuild. Building one took p50 1.1 to 1.4 ms, p99 2.3 to 2.6 ms. Tests 1,291 passed. Mutation spot-check 15/20 first run; four test gaps got tests and one redundant check was removed.

Known limits. It explains the decision plane, not the model's wording. Most everyday messages match no lexicon term (median 0 detectors), so the router breakdown carries the explanation. The words driving VADER are not shown.

## Phase 10: Privacy and autonomy

Built. A versioned plain-language notice gates the chat; "Save on this computer" or "Start without saving" is the consent. The consent gate runs after the safety gate, so a crisis is always answered. A split repository keeps each session in SQLite or in memory, and unsaved sessions never touch the file and expire after 2 hours idle. Export returns every table with a `user_id` column, found from the schema. Delete cascades, zeroes freed pages with `secure_delete` and empties the WAL with `wal_checkpoint(TRUNCATE)`. A saved session's key lives in `localStorage`, an unsaved one's in `sessionStorage`. The help card opens on the country of the computer's time zone, read in the browser and never sent.

Results.

| Requirement | Result |
|---|---|
| Notice gates the API | 403 `consent_required` before consent; crisis answered from unconsented and unknown sessions |
| Export complete | Same 8 tables and columns from both backends; own rows only; never the session key |
| Delete leaves nothing | 0 rows in every user table; marker absent from `.db` and `-wal`; WAL 0 bytes |
| Unsaved writes nothing | Every data-folder file byte-identical before and after an unsaved session |
| Export and delete speed | Export 10.9 ms for 1,000 turns; delete with checkpoint 22.3 ms |

The erasure test found that SQLite leaves deleted text on disk without raising when another program holds the file open mid-read. Delete now reports `503 erasure_pending` and retries after every later call and at startup. Tests 1,375 passed. Mutation spot-check 23/25 first run.

Known limits. Anyone using the same browser can open a saved conversation; the notice says so. "Nothing written to disk" covers OASIS only, not swap files or SSD copies. The notice awaits legal review (O8, CR-23).

## Phase 11: Communication style

Built. The user sets directness (direct, balanced, indirect) and formality (casual, neutral, formal). Each non-default value adds one sentence to a style line in the prompt; the defaults add nothing. The planner never receives the style, so it cannot change a decision. A hedged message, with two of the last three hedged, gets a note pointing to Settings; nothing changes automatically. No type or table holds any identity field.

Results. 9/9 styles give distinct prompts. The invariance property test passed: 25 generated conversations under all 9 styles gave identical verdicts, modes, cards, plans, explanations and replies. With the real model, gentle and formal were followed clearly, direct and casual weakly. Formal replies at first failed `validate_first` more often (30/70 first drafts against 13/70), so formal acknowledgements were added to the list. Tests 1,464 passed; `oasis.style` 100%. Mutation spot-check 16/17 first run.

Known limits. Casual and direct are weakly followed by the 4B model. The hedge list's recall is unmeasured. Fixed replies do not change with style (CR-25).

## Phase 12: Bias evaluation

Built. Eight crisis items and six conversations (low mood, exam worry, a thinking trap, anger, overwhelm, good news) are written in standard English and seven dialect or code-mixed versions; crisis items also have a typo version. Twenty-five demographic and cultural variants are applied to the standard text (10 identity prefixes, 7 signed names, 4 family-and-place sentences, 4 festivals), plus 8 held-out identity phrasings. CI requires every crisis version handed off, no false handoffs, and identical decisions for every demographic and cultural variant. Dialect agreement on other decisions is reported, not required.

The first run found three problems. "I don't want to live anymore" was missed when anything followed it. Dialect and code-mixed crisis phrasing was often missed. Identity words diluted per-word scores and delayed the DBT offer and grounding. Five rules were widened and ten added, each with examples, next to seven code-mixed idioms that must not trigger; scorers now use each message's highest-scoring sentence, with a leading identity clause scored on its own.

| Measure | First run | After fixes |
|---|---|---|
| Crisis handoffs, every version | 223/272 | 272/272, plus 64/64 held out |
| By version (of 8) | Standard 8, British 7, Indian English 6, AAVE 5, typos 5, Nigerian Pidgin 4, Hinglish 3, Spanglish 0, Taglish 0 | 8 each |
| False handoffs in conversations | 0 | 0 |
| Demographic decision mismatches | 78 | 0 |
| Held-out identity turns that differ (reported) | 24 | 15 |

Dialect agreement with standard decisions (reported): British 21/25, AAVE 23/25, Indian English, Nigerian Pidgin, Hinglish, Spanglish and Taglish 19/25 each. The low-mood screening offer is missed in every dialect, and most dialects miss the DBT offer and grounding.

Reply quality on the real model (25 turns per dialect, 50 per demographic group):

| Group | Words | Sentiment | First drafts passing | Fallbacks | Help surfaced |
|---|---|---|---|---|---|
| Standard | 31.4 | +0.08 | 68% | 0% | 24% |
| British | 29.7 | +0.20 | 50% | 0% | 16% |
| AAVE | 28.8 | +0.21 | 46% | 0% | 16% |
| Indian English | 33.0 | +0.20 | 44% | 0% | 0% |
| Nigerian Pidgin | 32.3 | +0.19 | 52% | 4% | 0% |
| Hinglish | 34.9 | +0.09 | 57% | 8% | 0% |
| Spanglish | 30.3 | -0.00 | 4% | 0% | 0% |
| Taglish | 23.8 | +0.10 | 32% | 0% | 0% |
| Identity | 34.0 | +0.06 | 57% | 2% | 24% |
| Name | 29.7 | +0.28 | 55% | 2% | 24% |
| Family | 32.6 | +0.21 | 50% | 2% | 24% |
| Culture | 32.5 | +0.17 | 55% | 4% | 24% |

Standard English alone ranged from 50% to 68% first drafts passing and +0.08 to +0.20 sentiment over four runs, so the demographic groups sit within its own spread. Spanglish fails because `validate_first` lists English acknowledgements only; replies are retried, not dropped. Tests 1,536 passed; gate p99 5.6 ms after the new rules.

Known limits. Dialect text was written by the developer, not native speakers (CR-26), and the crisis set was then used for tuning. Identity stated mid-sentence still dilutes scores. One quality run per group cannot show gaps under about 20 points.

## Phase 13: Engagement and reliability

Built. Every row of the fault matrix is an HTTP test; model faults go through the real client to a local stub server, including a stream of single bytes that only the engine deadline can end. Open questionnaires, exercises, post-crisis mode and style survive a restart; a saved conversation unused for 90 days is deleted. The generation timeout now starts once the model is free, and the wait is bounded by the request deadline.

Non-model latency over 600 requests (fake model, SQLite on disk), against a 150 ms p95 target:

| Stage | p50 / p95 / p99 (ms) |
|---|---|
| Safety | 0 / 0 / 0 |
| Load state | 1 / 2 / 2 |
| Plan | 2 / 3 / 3 |
| Explain | 1 / 1 / 1 |
| Record | 2 / 4 / 11 |
| Whole request | 10 / 12 / 18 |

Fault matrix (all pass in CI):

| Fault | Outcome |
|---|---|
| Model down | Templated reply within about 1 s |
| Model stalls or sends one byte at a time | Templated reply at the generation deadline |
| Empty or think-only output, HTTP 500, malformed JSON | Templated reply |
| Queue full | Busy reply at once |
| Guard rejects twice, or no time to retry | Vetted fallback |
| Database locked | Reply marked "may not have been saved" |
| Database dead | Reply, not saved |
| Safety gate raises | Crisis handoff, no model call |
| Explainer raises | Reply with "explanation unavailable" |
| Planner raises | Companion template; a crisis is still handed off |
| Storage never answers | Templated reply at the deadline; a crisis is still handed off |
| Invalid safety content | App refuses to start |
| Model stalled and storage dead | Crisis handoff in under 1 s |

The matrix found two bugs: a refused connection on Windows was traced as a timeout, and crisis bookkeeping could wait forever on dead storage. The queue fix raised requests served on a busy desktop from 5/6 to 6/6 (two sessions), 3/9 to 8/9 (three) and 2/12 to 9/12 (four).

Real model, quiet machine: one session 8.8 s median warm, 20 s cold. llama-server commits 4.1 GB but Windows kept only about 0.25 GB of it in RAM next to a desktop app; the app used 23 to 64 MB. Streaming was measured, not built: the first sentence arrives 2.0 s before the whole reply, but the guard rejected 4 of 20 first drafts that would already have been on screen.

Usability. A review against Nielsen's ten heuristics and nine WCAG 2.2 AA checks, at desktop and 375 px, keyboard only and with the server stopped, found five problems, each fixed with a test: the help card ran off a phone screen, Enter sent a second message while a reply was pending, Escape did not close the help card, seven colours failed contrast (now 33/33 pairs pass, checked in CI), and two controls were under 24 px. There were no participants and no screen-reader walkthrough.

Tests 1,619 passed. Mutation spot-check 14/15 first run.

## Phase 14: Cost and access

Built. The README became a three-step install. A second load run compared queue limits, and the default became 2. `scripts/licences.py` lists every runtime licence, and `scripts/export_diagrams.py` renders the Mermaid diagrams.

Clean install on the reference laptop with empty caches: clone 15 s, `uv sync` 295 s (Python 3.12.15 and 88 packages), disk 3.2 GB including the 2.74 GB model; all eight checks passed in the fresh clone. The install guide gained `-ngl 0` (the Vulkan build ran out of memory on the integrated graphics) and `--no-mmproj` (skips a 0.68 GB vision file).

Requests served, busy or timed out (three messages per session, 30 s timeout):

| Sessions | Queue 4 | Queue 2 |
|---|---|---|
| 1 | 1 / 0 / 2 (cold start) | 3 / 0 / 0 |
| 2 | 6 / 0 / 0 | 6 / 0 / 0 |
| 3 | 9 / 0 / 0 | 8 / 0 / 1 |
| 4 | 8 / 0 / 4 | 8 / 3 / 1 |
| 6 | 4 / 3 / 11 | 9 / 9 / 0 |
| 8 | 8 / 9 / 7 | 9 / 15 / 0 |

Cost profile: nothing to run (no paid API, account or cloud); runtime licences MIT, BSD, Apache-2.0, MPL-2.0 and PSF; network used only to install; 8 GB of RAM recommended; one reply 8 to 9 s warm, 11 to 21 s cold; 2 people at once fully served; about 0.04 Wh per reply, estimated from the processor's rated 15 W.

Known limits. The install check ran on the same laptop, not a second computer; macOS and Linux commands are not verified. Load samples are small.

## Demo testing changes

A test version was shared by link from a 32 GB host through a Cloudflare tunnel, in demo mode (memory only, a demo notice and a "made-up messages only" banner). Testers' reports led to these changes, each with tests.

| Finding | Change |
|---|---|
| "i want to kill mess chef" and "Feeling to die" got ordinary replies | New `harm_others` tier with its own reply naming the emergency number; rules for feeling like dying and asking for a means. A second held-out batch, written first, scored 20/22 (90.9%) before the fixes |
| Negative messages showed as positive in the trend ("life is no horrible" +0.35) | Four VADER corrections: comparison "like" and "hand" score nothing; a negated bad word and a good word after "over" or "too" are neutral |
| Too many questions | Listening-only replies on request, after two question replies in a row, or after a 40-word message |
| One-word answers got a paragraph | A one-sentence acknowledgement for statements of five words or fewer |
| Testers wanted suggestions and encouragement | One small idea with hope every fourth reply about a difficulty; "stay positive" phrases rejected |
| Testers wanted a fresh conversation each day | A New chat button; the trend page graphs each conversation |
| A panel under every reply was cluttered | Explanations moved to a "Why replies" page |

## Reproduce

```bash
uv run python scripts/verify.py
```

```bash
uv run python scripts/safety_eval.py
```

```bash
uv run python scripts/bias_eval.py --fake
```

```bash
uv run python scripts/load_test.py profile
```

`scripts/bias_eval.py` without `--fake`, `scripts/tone_check.py`, `scripts/load_test.py load` and `scripts/load_test.py stream` need llama-server running.
