# Phase 9 — Explainability

**Goal.** Every reply explains why its strategy was chosen (FR-XAI-1 to FR-XAI-3, PRD L1): which signals in the message mattered and by how much, how the router weighed each mode, what the guard did, and the same in plain words. The explanation covers the **response strategy**, never the language model's wording.

**Report topic.** Explaining response strategy, not words: SHAP on a hybrid rule/LLM system.

## 1. Design

| Component | File | Role |
|---|---|---|
| SHAP values | `explain/shap_values.py` | Exact SHAP values for one lexicon scorer, in closed form; the background means; the background sentences loader |
| Record and plain language | `explain/builder.py` | `build()` returns the explanation JSON; `unavailable()` the record stored when building fails. Checks additivity, ranks the router's contributions, writes the bullets |
| Wording | `content/explain/plain_language.yaml` | Everyday names for every router signal, mode, thinking-trap category and planner reason; the bullet phrases (CR-22). Startup stops if anything is missing |
| Background | `content/explain/neutral.yaml` | 30 synthetic everyday messages that set each term's ordinary rate (CR-22) |
| Scorer access | `core/detectors/lexicon.py` | `counts()`, `rates()` and `linear()` (the pre-clip value) split out of `score()`, unchanged arithmetic |
| Engine | `core/engine.py` | Stage 8 builds the explanation after the guard, stores it with the reply; fail-soft |
| Storage | `storage/migrations/0005_explanations.sql`, both repositories | `explanation` JSON column on `turns`; `get_explanation(user_id, turn_id)`; `TurnRecord.has_explanation` |
| API | `api/routes.py`, `api/schemas.py` | `explanation_id` on `/chat` and on each `/history` turn; `GET /explanations/{id}` |
| Panel | `web/app.js`, `web/styles.css` | "Why this reply?" under each bot message, fetched when first opened; "See details" shows the raw record (the debug view) |
| Import rule | `.importlinter` | C3: `oasis.explain` may not import the LLM, storage or API packages |

**Why closed form instead of the `shap` library** (Smriti, 2026-10-22). The spike confirmed `shap` 0.54.1 installs on Windows with Python 3.12.15. But every detector in OASIS is linear: the hand-weighted lexicon scorers are `f(x) = b + Σ cᵢxᵢ` before the clip (`xᵢ` = a term's matches per token, `cᵢ = scale · wᵢ`), no scikit-learn model was built, and the design lists no black-box part for v1. For a linear model with independent features, the SHAP value of each term is exactly

> φᵢ = cᵢ (xᵢ − E[xᵢ]),  base = b + Σ cᵢ E[xᵢ],

which is what `shap.LinearExplainer` computes. A runtime `shap` would bring numpy, scipy, pandas and scikit-learn into a local app meant for a 6 GB laptop to evaluate that one line. So the app computes it directly, and `shap` is a dev-only dependency used as a test oracle: one test runs `LinearExplainer` on every scorer and compares.

**The background** decides what "ordinary" means: E[xᵢ] is each term's mean rate over 30 everyday messages ("I always have tea before I go to bed", "Nobody was at the gym this morning"). A word like "always" gets less credit in a message than a rare one like "nothing ever", because some of its use is just normal talk.

**The additivity check** compares base + Σφ with the scorer's own `Lexicon.linear()`, the function the router's `score()` runs. Both use the same match counts (counted once, for speed), but the arithmetic is separate, so a wrong φ or base shows. Any check that fails marks the record `inconsistent` and logs that without content.

**The harsh-label rule.** A label like "I'm a horrible person" is caught by a VADER-based rule (Phase 7), not by a lexicon term, and the signal takes the larger of the two. Its extra share becomes one more feature, `rule:harsh_label`, so the parts still add up; a second check confirms the result equals the larger-of rule in `signals.py`.

**The router** is already an exact weighted sum (Phase 4): every mode's score is its bias plus `weight × value` for each signal. The record keeps all four modes with their non-zero contributions. Its additivity holds by construction and is checked as a guard against a future change to `score_modes`.

**The record** (`version` "1"): scope note, status, the plan (mode, reason codes, templated), the router breakdown, the detectors that fired, the guard (attempts, outcomes, fallback reason) and the plain-language bullets. It holds no IDs or timestamps and is written with sorted keys, so identical input gives identical bytes. Feature names are lexicon patterns or `rule:harsh_label`; the user's words never appear (tested with a marker word).

**Plain language.**
- *Routed replies:* "Your message showed {the top two inputs of the leading mode}." Then, on a thinking-trap turn, "Your message had what can be a thinking trap ({categories}), so the reply does not simply agree with it." Then what the reply does: the mode sentence, an exercise offer ("You can say no"), the next exercise step, or "One message is not enough to change approach…" while hysteresis builds.
- *Replies chosen by precedence* (questionnaire steps, psychoeducation, exercise buttons, leaving post-crisis mode): one bullet per planner reason code, saying why and what. A screening offer is told apart by its stored reason ("You asked for a questionnaire…" or "Several recent messages mentioned low mood or worry…"). A message that gets both a psychoeducation item and an offer gets both bullets.
- A pre-written fallback adds "The reply is a pre-written message…".

**Engine and failure.** Stage 8 runs the explainer after generation and the guard, when every decision is final, and stores the record in the same `append_turn` as the reply. Any exception stores `{"status": "unavailable", "reason": "explain.error"}`, adds `explain.error` to the turn's degraded list, and leaves the reply exactly as it would have been. Crisis turns return before stage 8 (rules S3, S4) and have no explanation; their `explanation_id` is null.

**Departures from the phase plan.**
- **No runtime `shap`, no LIME** (above).
- **Fewer files:** no `router_explainer.py` (the router's breakdown already exists in `RouteDecision`), no `plain_language.py` (the bullets are one function in `builder.py`), no `api/routes_explain.py` (one route in `routes.py`), no `web/why.js` (one function in `app.js`).
- **Storage:** a column on `turns` (migration `0005`, as 0004 was taken by Phase 8) instead of an `explanations` table. The explanation lives and dies with the reply it explains, so export and delete need nothing extra; `explanation_id` is the reply's turn ID.
- **Debug view:** "See details" inside the panel instead of a separate `debug.html` and `GET /debug/turns/{id}`. The record already carries the raw contributions.

## 2. Evaluation method

- **Exactness:**
  - Additivity on 200 generated messages (Hypothesis) for every one of the 22 scorers, against `Lexicon.linear()` with its own matching.
  - Every scorer compared with `shap.LinearExplainer` over the same background on 8 fixed messages.
  - A measurement script over every user message in the labelled test data (615 distinct messages, none written for Phase 9): additivity error and the largest difference from `LinearExplainer`.
- **Record:** design fields present; only scorers that fired are listed; φ ranked and never zero; `clipped` past 1; router sums; byte-identical JSON on rebuild and across two fresh engines; no user text; harsh-label share; button turns explain no detectors; `unavailable` says why.
- **Checks that must fail:** a wrong output, a wrong φ and a wrong harsh-label share each mark the record `inconsistent` (monkeypatched).
- **Plain language:** thinking-trap categories named once; the message never quoted; the fallback bullet; every reason code a reply can be chosen by without the router (14) has a bullet; psychoeducation gets its cue bullet and not a duplicate mode sentence; an explicit screening request; an offer plus an explanation; a declined exercise; routed replies use signals, not reason bullets. Four kinds of invalid wording file are rejected.
- **Engine:** every non-crisis reply of 8 varied messages has an explanation that resolves; templated replies too; crisis replies none; an explainer that raises leaves the reply identical to a normal run (fault injection, rules T4).
- **Storage contract** (both backends): round trip; another user gets nothing; user turns have none; invalid JSON rejected. SQLite: the CHECK rejects a non-JSON row.
- **HTTP:** `/chat` returns the ID; `GET /explanations/{id}` returns the record with `no-store`; history marks explained replies; another session gets 404, no session 401, a malformed or unknown ID 404; crisis has none; `app.js` holds the panel, "See details" and the unavailable text.
- **Speed:** best of 5 under 20 ms per message, including a ~1,900-character message (test); distribution measured over the 615 messages.
- **Mutation spot-check:** 20 deliberate faults across the SHAP code, the builder, the engine, storage and the endpoint, each run against the explain, contract, integration, engine, fault-injection and latency tests, then restored.
- **Browser check:** messages through the dev server (llama-server not running, so the replies were the fallback), the panel opened live and after a reload, "See details", phone width (375 px).

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass. One earlier run's pip-audit failed on a pypi.org read timeout; the rerun and the final run found no known vulnerabilities |
| Tests | 1291 passed, 0 skipped |
| Coverage | 98.57% overall; `explain/builder.py` 100%, `explain/shap_values.py` 95% (the one miss is the empty-background error), `oasis.router` 100%, `oasis.assessment` 97.8%, `oasis.safety` 97.1% |
| Additivity (615 real test-data messages × 22 scorers) | Largest error 2.2 × 10⁻¹⁶ (limit 10⁻⁶); 615/615 records `ok`, 0 `inconsistent` |
| Agreement with `shap.LinearExplainer` | Largest difference 0.0 over the same 615 messages and 22 scorers; ≤ 10⁻¹² in the test |
| Determinism | 615/615 byte-identical on rebuild; identical across two fresh engines |
| Mutation spot-check | 15/20 at first. Four misses were test gaps: a score below 0 (no scorer has a negative bias today), a button turn tested with "Yes" (which fires no scorer anyway), unsorted keys (dicts keep their order, so the bytes did not change) and an ID returned for a reply that was not saved; a test was added for each. The fifth (a malformed ID reaching storage) showed the ID check was redundant: the scoped query already returns 404, so the check was removed. **Now 19/19** |
| Speed (dev machine) | Building the explanation: p50 1.1–1.4 ms, p95 1.7–2.3 ms, p99 2.3–2.6 ms over the 615 messages (two runs); a 1,840-character message 14.6–15.5 ms best of 5. One 119 ms outlier in the first run was not repeatable (slowest best-of-5: 2.7 ms). Before counting matches once, the long message took 32 ms. Records: median 827 bytes, at most 1,953 |
| Coverage of replies | Detectors per reply: median 0, at most 3 (most everyday messages match no lexicon term, so the router breakdown and the plain language carry the explanation) |
| Browser | "I always mess everything up and nobody likes me": the panel named "a thinking trap" twice (once as a signal, once with its categories), then the hold while hysteresis builds and the fallback note; the signal is now left out of the first bullet when the trap bullet follows. "I always fail at everything, nobody cares" → "Your message showed a thinking trap." and "So OASIS asks whether you would like to try a short CBT exercise. You can say no." "See details" showed the record; a reloaded conversation kept its panels. No console errors; no sideways scrolling at 375 px |

## 4. Known limits

- **It explains the decision plane, not the reply.** The language model's wording, tone and any mistake in it are outside the explanation, and the scope note says so on every panel.
- **The SHAP values are exact for the model, not for the meaning.** They say which lexicon terms moved a score; the lexicons themselves are engineering start values (CR-20). A message that matches no term (median: none) is explained only by the router's bias and the plain language.
- **Valence (VADER) is not broken down.** It enters the router as `valence_neg` with its exact contribution, but which words drove VADER is not shown.
- **The background is small and synthetic** (30 sentences). It shifts each base and φ but not their sum; a different background would give different φ, which is normal for SHAP. A wrong background mean cannot be caught by additivity, only by the library comparison.
- **The router's additivity holds by construction.** Its check guards against a future change; it cannot fail today.
- **Patterns as feature names.** "See details" shows regex patterns (`\\balways\\b`), which suit a developer, not a user. The plain-language bullets name categories, not terms.
- **A third pass over the lexicons per turn** (planner, mood features, explanation): about 1 ms for an everyday message, ~15 ms for a 2,000-character one, inside the 150 ms non-LLM budget.
- **A failed fetch in the panel** shows "Explanation unavailable" until the page is reloaded; reopening does not retry.
- **Real-model replies were not part of the browser check** (llama-server was not running). The explanation does not depend on the reply text, but the end-to-end look with a real reply is not verified here.
- English only; the wording and background sentences await clinician review (CR-22).
