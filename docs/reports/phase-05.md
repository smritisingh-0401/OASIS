# Phase 5 — Psychoeducation

**Goal.** Contextual, stigma-reducing explanations from vetted content: when a message asks "what's wrong with me" or "is this normal", asks for a diagnosis, or repeats a stigma ("therapy is for weak people"), OASIS answers with one short, sourced explanation. The decision plane picks the item; the LLM only rewords it.

## 1. Design

| Component | File | Role |
|---|---|---|
| Cue | `content/lexicons/cues.yaml` (`psychoed` scorer), `core/signals.py` | `Signals.psychoed_cue`: true when any cue phrase matches the normalised message. Three groups: questions ("what's wrong with me", "is it normal to", "am I going crazy", "does anyone else feel"), diagnosis questions ("do I have depression", "could this be anxiety"), stigma statements ("therapy is only for crazy people", "snap out of it", "asking for help means I'm weak") |
| Items | `content/psychoed/items.yaml` | 11 items, each with `source`, `reading_level`, `version`, `review_status` plus `topic`, `text`, `cues[]` (FR-PSY-3). Order: diagnosis, help-seeking, not weakness, panic, grief, sleep, loneliness, anxiety, stress, low mood, general |
| Selector | `psychoed/selector.py` | Loads and checks the items at startup; picks the first unshown item whose topic cues match, else the general item; Flesch-Kincaid grade |
| Planner | `core/planner.py` | Precedence slot (design §6a); mode `psychoed` with `no_diagnosis, use_snippet_only`; the item text is the snippet and the fallback |
| Memory | `types.RouterState.psychoed_shown`, `router/router.py` | Shown item IDs persist with the router memory JSON (no migration) and survive the acute override |
| Prompt | `llm/prompt.py` | Psychoeducation goal: explain the item in two or three plain sentences, without diagnosing, adding nothing |

**Precedence** (design §6a). Post-crisis → buttons → open questionnaire → (exercise running: router only) → explicit questionnaire request → psychoeducation → unprompted questionnaire offer → router.

- A message that is both an explicit request and a cue gets the item first, as its own message, and then the questionnaire offer (Smriti's choice).
- Acute overwhelm skips psychoeducation and goes to grounding: "is this a panic attack? I can't breathe…" needs help first.

**Content.** Every item paraphrases one NHS or WHO page, and each page was fetched on 2026-10-11 to confirm what the text says:
- "not dangerous and will not cause you physical harm" and "5 to 20 minutes" come from NHS *Panic disorder*.
- "a real illness with real symptoms", "not a sign of weakness" and "snap out of it" come from NHS *Depression in adults*.
- The two-week threshold comes from NHS *Low mood, sadness and depression*.

No item names a country's services, so nothing assumes the user is in the UK. Flesch-Kincaid grades are 4.2–8.0. Startup refuses any of these: a missing provenance field, an item not flagged `needs_clinician_review`, a stored grade that no longer matches the text, a grade above 8, a bad cue, or a misplaced general item.

**Departures from the phase plan's file list.**
- No `psychoed/cues.py`: the cue is a scorer in the existing lexicon file, run by the Phase 4 scorer.
- No `scripts/readability.py`: the grade check runs when the app starts.

## 2. Evaluation method

- **Trigger set** (`tests/data/psychoed/trigger.yaml`, 23 messages, written before the cue phrases): each must raise the cue and select the named item.
- **Ordinary-talk set** (`ordinary.yaml`, 22 near misses written before the cue phrases): the same words in other senses, such as "what's wrong with my laptop", "is it normal for the train to be this late" or "I'm not crazy about spicy food". None may fire.
- **Unseen sets** for false positives: all 104 user turns of the Phase 3 labelled conversations, and the 85 Phase 2 benign safety messages. Neither was looked at while writing the cues.
- **Content checks:** provenance fields, review flag, NHS or WHO source, reading grade equal to the stored value and at most 8, and each kind of invalid file rejected.
- **Planner:**
  - the plan's shape
  - once per session, with the fall-through to the router
  - explicit request plus cue gives the item as a preface and then the offer
  - psychoeducation beats an unprompted offer
  - mid-exercise and acute-overwhelm cases
  - an open exercise offer lapses
  - post-crisis and open-questionnaire precedence
- **Engine and HTTP:** the item reaches the prompt as the script line; the LLM failing gives the item text; the full flow over HTTP.
- **Mutation spot-check:** 10 deliberate faults across selector, planner, signals, router memory and prompt.
- **Live check** in the browser against the fake LLM.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass |
| Tests | 882 passed, 0 skipped |
| Coverage | 98.1% overall; `oasis.psychoed` 100%, `oasis.router` 100%, `oasis.assessment` 98.6%, `oasis.safety` 97.1% |
| Trigger set | 23/23 fire with the expected item |
| False positives | 0/22 near-miss ordinary messages; 0/104 Phase 3 conversation turns; 0/85 Phase 2 benign messages |
| Reading level | Grade 4.2–8.0 (target ≤ 8) |
| Planner latency (dev machine, 300 messages) | p50 0.28 ms, p95 0.41 ms, p99 0.47 ms |
| Mutation spot-check | 9/10 caught on the first run; the miss (general item not listed last) now has a test; 10/10 |
| Live check | "what's wrong with me?" → general item. "is it normal to have panic attacks? can I take a depression test" → panic item, then the PHQ-9 offer with Yes / Not now. Repeating "what's wrong with me?" → an ordinary companion reply. Reload keeps the history. No console errors |

## 4. Known limits

- **Recall on unseen phrasing is not measured.** The same author wrote the trigger set and the cue phrases, so 23/23 shows coverage of intended phrasings, not accuracy. The zero false positives on unseen sets are encouraging. A fresh labelled set is needed for both.
- **Cues are phrase lists.** Paraphrases outside them are missed, for example "why am I so broken", or a stigma said in other words.
- **Topic choice is first match in file order.** A message touching two topics gets the earlier one. "Is it normal to feel anxious and low" gets anxiety, not low mood.
- **"Is it normal?" at the end of a message fires whatever came before.** "The train is late, is that normal?" would get the general item.
- **A psychoeducation turn holds back an unprompted questionnaire offer** for that turn. The trigger fires again later if its evidence still holds.
- **Real-model phrasing of the items is not verified here.** The fake LLM returns the item verbatim; the prompt asks the model to add nothing.
- English only. Items paraphrase UK and global sources. Item text, cues and order await clinician review (CR-13).
