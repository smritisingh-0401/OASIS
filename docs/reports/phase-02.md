# Phase 2 — Safety layer

**Report topic:** rule-based crisis detection that is explainable, fails closed and cannot be blocked by storage — obfuscation-tolerant matching, span-based idiom suppression, verified crisis resources and the post-crisis policy.

## 1. Design

| Component | File | Role |
|---|---|---|
| Normaliser | `safety/normalize.py` | NFKC, invisible-character strip, casefold, confusables, apostrophe removal, stretched letters → up to 4 variants (base, leetspeak, unspaced, both) |
| Pattern loader | `safety/rules.py` | Validates `patterns.yaml` and `allowlist.yaml`, rewrites patterns to tolerate repeated letters, runs the example self-check; any problem stops the app at startup |
| Gate | `safety/gate.py` | `RuleBasedSafetyGate.check()` returns a `SafetyVerdict` with tiers, pattern IDs and ruleset version; `check_fail_closed` turns any error into a crisis verdict |
| Handoff | `safety/handoff.py` | Fixed reply, compiled-in |
| Resources | `safety/resources.py`, `content/safety/resources.yaml` | 224 countries and territories, validated at startup (ISO code, region, phone format, https source, verification date not in the future) |
| Help card | `api/pages.py`, `web/index.html` | Rendered on the server into the page as nested `<details>`; no JavaScript, no fetch |
| Post-crisis | `core/planner.py`, `core/engine.py`, `core/templates.py` | In-memory set plus persisted flag; templated supportive reply until an explicit continue phrase |
| Audit | `core/engine.py` (`record_crisis`), `api/routes.py`, migration `0002_audit_log.sql` | Background task after the response: post-crisis flag, audit entry (tiers, pattern IDs, version; no text), history placeholder |

Key mechanisms:

- **Order is the safety argument.** The gate runs before any storage access. A crisis verdict returns the handoff with zero LLM and zero storage calls; the audit is written by a FastAPI background task after the response has been sent, so a slow or dead database can never delay or block the handoff.
- **Fail closed at two levels.** Bad content stops the app at boot (validation plus an example self-check). Any exception at turn time becomes a crisis verdict.
- **Obfuscation.** Matching runs over every normalised variant; a hit in any one triggers. `tolerant()` rewrites each literal letter `c` to `c+` (and `c?` to `c*`) once at load, so stretched spellings match without hand-written repeats.
- **No negation suppression.** "I don't want to kill myself" triggers by design: a missed crisis costs far more than an unneeded handoff.
- **Span-based allow-list.** An idiom ("dying to see it", "killing it at work") removes a hit only when its span covers the hit span, so a real disclosure later in the same message still triggers.
- **Five tiers:** `explicit`, `passive`, `plan_method`, `burden` and the new `self_harm` (non-suicidal self-injury), which needs clinician confirmation (CR-01).
- **Crisis resources standard.** Tier 1 requires a crisis line verified on the service's own site or a government site. Tier 2 uses emergency numbers from UK FCDO travel advice (gov.uk Content API). Every entry records its source URL and verification date.
- **The help card works offline.** It is plain HTML inside a `<details>` element, so it opens with the server stopped. Phone numbers are `tel:` links.

## 2. Evaluation method

- **Test sets written before any pattern** (commit `d5ffef3`): held-out crisis phrases (71, by tier and obfuscation type) and a benign set (everyday messages, idioms, third-party mentions). Patterns were then written against a separate training set.
- **Held-out set status:** measured once before tuning; misses were then analysed, so the set is now *consumed* and its later recall is not an unbiased estimate. A fresh external set is an open item.
- **Unit tests** for each normalisation step, each loader rejection, negations, designed non-triggers and an idiom followed by a real disclosure in the same message; **property tests** (Hypothesis) that the gate never raises and that stretched letters, invisible characters and case changes never hide a pattern example.
- **Integration and fault injection:** the full crisis flow through HTTP (audit row, post-crisis hold, continue, placeholder, no crisis text stored); crisis with dead storage and an LLM that fails the test if called; crisis with no session.
- **Latency:** `tests/performance/test_gate_latency.py` asserts p99 < 10 ms; `scripts/safety_eval.py` reports recall, false-positive rate and latency.
- **Mutation spot-check** of the safety path and **live browser check**.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass: ruff lint, ruff format, mypy strict, import-linter, bandit, pip-audit, pytest + coverage, critical-package coverage |
| Tests | 481 passed, 0 skipped |
| Coverage | 98.09% overall (branch coverage on); `oasis.safety` 97.13% (target ≥ 95%) |
| Held-out recall, before tuning | 63/71 = 88.7% |
| Benign false positives | Everyday messages 0/50; idioms and hyperbole 0/30; third-party mentions 4/5 (by design: "my friend wants to kill himself" gets the handoff) |
| Training set recall (must be 100%) | 72/72 |
| Gate latency (laptop on battery) | Realistic messages p50 0.20 ms, p99 0.55 ms (n = 4 560). Dense 2 000-character stress inputs 10–35 ms; the evaluation script's mixed p99 is 11.4 ms, over the 10 ms target |
| Mutation spot-check | 11/12 caught on the first run; the survivor (help card not escaping crisis line names) led to a new test, after which 12/12 are caught. Faults: verdict ignores hits; fail-open on error; one normalisation variant dropped; stretched-letter folding removed; allow-list suppression inverted; example self-check disabled; tolerant rewrite disabled; crisis branch skipped; post-crisis hold skipped; future verification dates accepted; crisis audit not scheduled; HTML escaping removed |
| Live check | Leetspeak crisis message ("k1ll") gets the handoff, the help card opens and takes focus, "Continue talking" appears; after a page reload history shows "Crisis support was shown." instead of the message and post-crisis mode still holds; "Continue talking" returns to companion mode; the India card dials `tel:14416`, `tel:18008914416`, `tel:112`; with the server stopped the help card still opens; no external requests; no message text in server logs. Two UI bugs found and fixed: focus was taken back from the help card, and crisis replies showed a "may not have been saved" note |

**Crisis resources.** 224 countries and territories: 40 Tier 1, 184 Tier 2, of which 8 carry an emergency note instead of a number.

**Moved to Tier 2.** The target was 64 Tier 1 countries. For 24 of them the official page could not be fetched from the development environment (blocked request, expired certificate, or no government source found), so they list the FCDO emergency number only: Philippines, Chile, Colombia, Pakistan, Egypt, Iran, Kenya, Uganda, Ghana, Jordan, Russia, Kazakhstan, Mongolia, Vietnam, Turkey, Morocco, Ethiopia, Tanzania, Uzbekistan, Cambodia, Laos, Myanmar, Timor-Leste, Afghanistan. No blocks were bypassed. Five candidates are ready to promote after a check in a normal browser: Philippines NCMH 1553, Chile *4141, Colombia 192 option 4, Pakistan Umang, and Sweden's Mind line hours.

## 4. Known limits

- **Recall on unseen phrasing is not yet measured honestly.** 88.7% is the only unbiased number, taken before tuning. Rule-based matching will miss novel phrasing; the handoff errs towards triggering on third-party mentions and negations.
- **Latency on long, dense input.** Each of the 34 patterns scans every variant, about 1 ms per pattern on a 2 000-character message on battery power. Realistic messages are far under target; a combined pre-filter is the upgrade path if real traffic approaches the limit. The whole gate stays well inside the 150 ms non-LLM budget.
- **English only.** Non-English crisis messages are not detected.
- **Post-crisis state after a restart with storage down** falls back to normal mode (CR-05).
- **Clinician review pending** for every pattern, the allow-list, the handoff and post-crisis wording, the continue phrases and the self-harm tier (CR-01..06).
- **Templates stay Python constants** (CR-18); a YAML loader waits for a second user.
- **Classifier:** none in v1; rules S7 governs any future one.
