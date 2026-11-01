# OASIS — ML models

Four small models sit beside the rule-based decision plane. Each one only **adds** to a rule path (it can raise an alert, an emotion, a rejection or an item, never remove one), has a fallback when it fails, and was measured on data it never saw. The principle from [architecture.md](architecture.md) still holds: rules decide, the LLM only phrases.

| # | Model | Where | Runtime cost | Needs |
|---|---|---|---|---|
| 1 | Add-only crisis classifier | `safety/classifier.py`, `content/safety/classifier.yaml` | ≤ 0.3 ms typical, pure Python | nothing (on by default) |
| 2 | Learned emotion scorers | `content/lexicons/emotions_learned.yaml` | ~2 ms, pure Python | nothing (on by default) |
| 3 | Guard NLI agreement check | `guard/nli.py`, `content/guard/nli.yaml` | ~24 ms per generated reply | `uv sync --extra ml` + `ml/fetch_models.py` |
| 4 | Psychoeducation retrieval | `psychoed/semantic.py`, `content/psychoed/semantic.yaml` | ~5 ms per question | same as 3 |

Models 1 and 2 are trained offline and shipped as weights in YAML, so the app gains no dependency and explanations stay exact SHAP values. Models 3 and 4 are pretrained transformers run as int8 ONNX on the CPU; without the optional extra or the files, OASIS runs exactly as before.

Reproduce everything from the repository root:

```bash
uv sync --extra ml
uv run python ml/train_crisis.py      # 1: trains, writes the weights, docs/reports/ml-crisis.json
uv run python ml/train_emotions.py    # 2: docs/reports/ml-emotions.json
uv run python ml/fetch_models.py      # 3 and 4: pinned model revisions into models/
uv run python ml/eval_guard_nli.py    # 3: docs/reports/ml-guard-nli.json
uv run python ml/eval_psychoed.py     # 4: docs/reports/ml-psychoed.json
uv run python scripts/safety_eval.py  # 1: held-out recall and false alarms, rules vs rules + classifier
```

Seeds are fixed (rules T7). Downloads are cached in `ml/data/` and `models/` (both git-ignored).

---

## 1. Add-only crisis classifier

**Problem.** The crisis patterns miss misspellings ("i want to dye", "im goin to end my lfe"). On a typo copy of the held-out phrases, the rules catch 51%.

**Model.** L1 logistic regression over word, word-pair and 3–5 letter features (`features()` in `safety/classifier.py`; the training script uses the same function, so training and serving cannot drift). Each sentence is scored separately and the highest score counts. 1,167 non-zero weights, scored in pure Python, so `oasis.safety` still imports only the standard library and PyYAML (rules S8).

**Data.**
- Crisis: the 81 training phrases in `tests/data/safety/train_phrases.yaml`, each with 20 keyboard-typo variants. The held-out files were never used (rules T8).
- Not crisis: GoEmotions training comments (Demszky et al. 2020, Apache-2.0) split into sentences, the allow-list idioms, 280 contrastive everyday sentences (`ml/hard_negatives.yaml`, ×5 weight), and the therapy-forum posts of the thinking-trap corpus (Shreevastava & Foltz 2021, MIT mirror, ×2 weight). Any sentence the rules already flag is dropped.

**Training.** 5-fold `StratifiedGroupKFold`, where a phrase and its typos share a fold. C is chosen from {0.3, 1, 3}. The threshold keeps the out-of-fold false-alarm rate on Reddit sentences at 0.1%.

**Results.**

| Set | Rules | Rules or classifier |
|---|---|---|
| Held-out typos (`heldout_typos.yaml`, 166 phrases, generated once and frozen) | 84 (51%) | **132 (80%)** |
| Known gap "i want to dye" | 0/1 | **1/1** |
| Held-out batches 1 and 2 (93 phrases) | 93 | 93 |
| Benign everyday, idioms and objects (98 messages) | 0 | 3 (3%) |
| GoEmotions test comments (5,410, untouched) | — | 7 (0.13%) |

The classifier adds about 0.1 ms to an ordinary message and 0.3 ms to a 600-character one (each word's letter pieces are cached). The safety latency test, with its 10 ms budget, passes with the classifier included. Across the evaluation set, the classifier adds about 1 ms at p99, where the 2,000-character stress messages dominate.

**Behaviour.** The gate is "rules OR classifier", and the classifier is asked only when no rule matched. A classifier-only alert gets a **check-in** (`CHECK_IN_REPLY`: it asks directly, opens "Need help now?" and offers "Continue talking"), because no pattern matched and it may be a misread. A pattern match always decides the reply (CR-28). It can be turned off with `OASIS_CRISIS_CLASSIFIER=0`.

**Iterations kept in the record.**
- The first model flagged 18% of the benign set, because the negatives had no everyday first-person phrasing.
- Contrastive negatives brought that to 14%.
- Forum posts plus the stricter 0.1% threshold brought it to 3%, at a cost of 10 points of typo recall.

The benign set is now consumed for the classifier. A fresh, externally written set is still needed.

---

## 2. Learned emotion scorers

**Problem.** The hand-written sadness, anxiety, anger and shame lexicons miss most emotional messages: recall 8–35% on GoEmotions.

**Model.** One L1 logistic regression per emotion, with the lexicon's own features (each word's count per token on the base form). The logit z is shipped as the lexicon's pre-clip value (z − t) / 3, with t the dev-set threshold of best F0.5. The learned scorer is therefore an ordinary lexicon file, and the "Why this reply" page explains it with exact SHAP values like any other.

**Add-only, after a measured failure.** Replacing the hand lexicons outright lost OASIS's own phrasings ("on edge", "my mind is racing", "boiling with rage"), which Reddit vocabulary lacks; 10 router tests caught it. So `signals.py` takes the **larger** of the hand and learned scores. The learned scorer can raise an emotion the hand terms miss but never lower one, and every router test passes unchanged.

**Data.** GoEmotions train/dev/test (43k/5.4k/5.4k). Label mapping: sadness ← sadness, grief, disappointment; anxiety ← fear, nervousness; anger ← anger, annoyance; shame ← embarrassment, remorse. Loneliness has no GoEmotions label and keeps its hand terms.

**Results (GoEmotions test split, used once).**

| Emotion | ROC-AUC hand → learned | Recall hand → hand or learned | Precision hand → hand or learned |
|---|---|---|---|
| sadness | 0.573 → **0.822** | 0.151 → **0.466** | 0.603 → 0.367 |
| anxiety | 0.668 → **0.904** | 0.347 → **0.622** | 0.395 → 0.455 |
| anger | 0.536 → **0.823** | 0.082 → **0.475** | 0.430 → 0.436 |
| shame | 0.569 → **0.925** | 0.140 → **0.677** | 0.520 → 0.477 |

Lexicon scoring got a fast path for single-word terms (one word count instead of a regex scan per term, with identical counts), so the 1,500 learned terms fit the 20 ms explanation budget.

**Limits.** Reddit is not OASIS's domain, and the sadness precision drop is real. An in-domain labelled set (about 300 chat messages, two annotators) is the next step.

---

## 3. Guard NLI agreement check

**Problem.** The guard's phrase lists catch agreement that echoes the user's words or says "you're right". A reply that rewords the claim and takes it as true ("the breakup really was your responsibility") slips through. A new frozen held-out set, `tests/data/guard/heldout_paraphrase.yaml` (20 agreeing, 20 benign), was written before any model ran. On it, the phrase lists catch 2 of 20.

**Model.** `cross-encoder/nli-deberta-v3-xsmall` (Apache-2.0, int8 ONNX, 87 MB). Each reply statement (questions are skipped) is the premise. The hypothesis is each thinking-trap clause of the user's message said back to them ("its all my fault" → "it's all your fault"). The reply fails `no_agreeing` when entailment ≥ the threshold. It only adds rejections, and a model error leaves the phrase lists in charge.

**Threshold.** The lowest value that blocks at most 1 of the 50 curated benign replies. That gives 0.5; the curated sets give little signal at higher values.

**Results and size comparison (held-out sets, used once).**

| Guard | Paraphrased agreement caught | Benign blocked | Original held-out (15 + 15) | Latency |
|---|---|---|---|---|
| Phrase lists | 2/20 | 1/20 | 15/15, 0/15 | — |
| + deberta-v3-xsmall (shipped) | **6/20** | 1/20 | 15/15, 0/15 | 24 ms |
| + deberta-v3-small | 5/20 | 1/20 | 15/15, 0/15 | 26 ms |
| + deberta-v3-base | 7/20 | 2/20 | 15/15, 0/15 | 49 ms |

**Limits.** Most reworded agreement still passes. Hedged agreement ("does seem to be a pattern for you") is not strict entailment, and 3 of the 20 messages produce no detected claim, so nothing is compared. Fine-tuning on owner-labelled pairs from real tone-check transcripts is the next step.

---

## 4. Psychoeducation retrieval

**Problem.** Items are chosen by phrase lists, so a question in other words ("does needing support mean I'm weak?") gets nothing. On a new frozen held-out set (`tests/data/psychoed/heldout_semantic.yaml`), the phrase lists give the right item to 3 of 33 questions.

**Model.** `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, int8 ONNX, 23 MB), mean-pooled and normalised. Each vetted item is embedded as its topic and text, and a question gets the closest item not yet shown, above a cosine threshold. It is asked only when the cue lexicon found nothing, and **only for a question**: a statement on the same topic ("I couldn't sleep last night") wants listening, not an explanation. The engine asks it before planning, so the planner stays free of model calls. The reply text is always the vetted item.

**Threshold.** The lowest value giving at most 1 of the 22 ordinary messages in `ordinary.yaml` an item: 0.3.

**Results (held-out, used once).**

| | Right item | Any item | Ordinary messages given an item |
|---|---|---|---|
| Phrase lists | 3/33 | 5/33 | 0/30 |
| + retrieval (shipped) | **24/33** | 30/33 | 1/30 |
| + retrieval without the question check (ablation) | 24/33 | 30/33 | 14/30 |

**Limits.** Both held-out sets were written by the build, not by users or clinicians. The one false item was "is it normal for cats to sleep all day?" (sleep).

---

## Reports

`docs/reports/ml-crisis.json`, `ml-emotions.json`, `ml-guard-nli.json`, `ml-psychoed.json` hold every number above, plus the grids, misses and false alarms.
