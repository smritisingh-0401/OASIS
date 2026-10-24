# Phase 11 — Cultural adaptation

**Goal.** A communication style the user sets (FR-CUL-1 to FR-CUL-3, PRD L3): how direct and how formal replies are. It changes the wording only, never what a reply does, and OASIS never infers it, or anything about who the user is, from their messages.

**Report topic.** Runtime cultural adaptation without demographic inference.

## 1. Design

| Component | File | Role |
|---|---|---|
| Profile | `oasis.types.StyleProfile`, `Plan.style` | Directness (direct / balanced / indirect) and formality (casual / neutral / formal); defaults balanced, neutral |
| Framing | `style/framing.py`, `content/style/framing.yaml` (CR-25) | One `Style:` line in the system prompt, just before the PLAN; empty for the defaults |
| Suggestion | `style/suggest.py` | Notices hedged phrasing and asks the page to point to Settings; never changes the profile |
| Settings store | `storage/migrations/0007_settings.sql`, `get_settings` / `set_settings` in both backends | One row per user: directness, formality, country; exported and deleted with everything else |
| API | `GET /settings`, `PUT /settings`, `ChatResponse.style_suggestion` | Read and replace the settings; PUT needs the current notice accepted and a country on the help card; a change is audited by field name |
| Pages | `settings.html` (server-rendered country list), `settings.js`, `app.js`, `styles.css` | Two segmented controls with an example reply under each option; the help card's country; the suggestion note in the chat |

**Style can only change the wording.** The architecture puts this as an invariant (§2.7); the build makes it structural. The planner's signature is unchanged and it never receives the style: the engine attaches the user's profile to the finished plan, and only the prompt builder reads it. The invariance test then checks the whole pipeline rather than trusting that structure: a Hypothesis property test generates conversations from messages covering every decision (explicit and passive crisis phrases, screening-trigger symptoms, psychoeducation cues, thinking traps, anger, acute overwhelm, the continue phrase, hedging and small talk), runs each under all nine styles, and requires identical replies, modes, crisis verdicts, questionnaire and exercise cards, plans, explanations, and prompts once the style line is removed.

**The framing line.** Each non-default value adds one sentence: "Be clear and straightforward…" (direct), "Be gentle and tentative: soften what you say with words like 'perhaps'…" (indirect), "Sound relaxed and friendly…" (casual), "Sound polite and formal, with no slang and no contractions" (formal). The defaults add nothing, so a user who never opens Settings gets exactly the prompt the earlier tone checks were run on; the file loader refuses a default that adds text. The line reaches every generated reply, including the one-sentence acknowledgement before an exercise step; fixed replies (crisis, post-crisis, questionnaires, offers) are vetted text and do not change.

**The suggestion** (FR-CUL-2). A short list of hedges ("maybe", "perhaps", "I guess", "I suppose", "sort of", "kind of", "I'm not sure", "probably nothing", "no big deal", "I wonder if", …) is matched on whole words, ignoring case and apostrophes. When the message just typed is hedged, at least two of the last three typed messages are, the directness is not already indirect, and the reply is generated (not a button press or fixed text), the response carries `style_suggestion: true`. The chat shows "You can ask OASIS to word things more gently in Settings." under that reply, once per tab, with a link. Nothing else happens: the profile changes only if the user changes it on the settings page.

**No demographic inference** (PRD L3c). No type or table has a field for ethnicity, nationality, language, dialect, religion or gender (tests over the dataclasses and the migration). The suggestion reads phrasing, not identity, and only ever points at a setting. The country is a help-card choice the user makes, validated against the crisis resources; it never reaches the prompt (test), and the time-zone suggestion (CR-24) is still worked out in the browser and never sent.

**The help card's country** (moved from Phase 10, decision 2026-10-23). The settings page lists the help card's own countries plus "Use this computer's time zone". The chat page fetches the choice once when it loads; "Need help now?" then opens "Your chosen country:" first, else the time-zone country, with the full list under "Not right?". The card itself still makes no request, so it works with the backend down (S12); if the settings cannot be fetched, it falls back to the time zone.

**Departures from the phase plan.**
- No `style/profile.py`: the profile is a frozen dataclass in `oasis.types`, because the plan carries it, and the settings row is a repository type.
- The suggestion's hedge list and thresholds live in `framing.yaml` with the framing sentences, so there is one style content file.
- The planner takes no style argument (design §6 sketches `plan(signals, state, style)`); attaching it after planning is what makes the invariance hold by construction.
- `PUT /settings` replaces all three values and is refused before consent (`403`), so nothing is stored for a session that has not accepted the notice.
- `oasis.style` sits in its own import layer under `llm`, `storage` and `safety`, and in the decision-plane contract (C2): it imports only content and types.

## 2. Evaluation method

- **Framing:** each of the nine styles gives a different system prompt; the default gives the old prompt; the style line sits before `PLAN:` and removing it leaves the default prompt; indirect + formal reaches companion, CBT, DBT and psychoeducation prompts and exercise acknowledgements; five kinds of invalid framing file are rejected.
- **Invariance (property test):** 25 generated conversations of 1-6 messages, each run under all nine styles through the real engine, gate, planner, guard and explainer with the fake model; replies, modes, verdicts, cards, prefaces, plans (style reset), explanations and prompts (style line removed) must be identical.
- **Engine:** the stored style reaches the prompt and the country does not; a failed settings read gives the default style and `storage.down`; the suggestion appears on the second hedged message and the settings are unchanged (a repository that fails any `set_settings` call); no suggestion for a button press even when its reply is generated.
- **Suggestion:** hedged and plain phrasings (curly apostrophe, "May I ask?", "I guessed"), one hedge not enough, two of three enough, only the last three messages count, none when already indirect.
- **Storage contract (both backends):** defaults until set, round trip, reset, scoped to the user, invalid values and unknown users rejected, exported in the same shape, removed by delete.
- **HTTP:** defaults and changes for saved and unsaved sessions, isolation between users, 401 without a session, 403 before consent, 422 for five kinds of bad body, 503 when storage is down, audit by field name only and not for an unchanged save, the chosen style framing the next reply, the suggestion on the response, none on a crisis reply, settings gone after delete.
- **Pages:** six radios with six examples and the "never guesses" sentence; every help-card country as an option; the settings script saves with `PUT /settings`; the chat page fetches `/settings` for the card while `suggestCountry` itself makes no request; the suggestion is shown once and links to Settings.
- **No inference:** no demographic field in `StyleProfile`, `UserSettings`, `Plan` or the settings table; only the settings endpoint and the storage layer call `set_settings` (source scan).
- **Mutation spot-check:** 17 deliberate faults across the engine, prompt, framing, suggestion, routes and both backends, each run against the style, settings API, contract and prompt tests, then restored.
- **Hedge rate on existing data:** the hedge list run over the repository's labelled user messages and conversations (written before this phase, for other purposes).
- **Browser check** (dev server, real model running, unsaved session): settings page, choosing Gentle, Formal and the United Kingdom, the help card, the suggestion, phone width.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass (ruff, format, mypy strict, import-linter with `oasis.style` in C2 and its own layer, bandit, pip-audit, pytest with coverage, critical coverage) |
| Tests | 1464 passed, 0 skipped (1443 before the CR-14 phrase change) |
| Coverage | 98.42% overall; `oasis.style` 100%, `api/routes.py` 96%, `core/engine.py` 96%; `oasis.router` 100%, `oasis.assessment` 97.8%, `oasis.safety` 97.1% |
| Done-when: different style, different framing | 9/9 styles give distinct prompts; the default prompt is unchanged from Phase 10 |
| Done-when: safety and mode invariance | Property test passes: 25 conversations x 9 styles, identical verdicts, modes, cards, plans, explanations and replies |
| Done-when: user can change style | Settings page saves on each choice; `GET /settings` returned `{"directness": "indirect", "formality": "formal", "country": "GB"}` after the browser check; the next reply used it |
| Suggestion never changes the profile | Settings unchanged after suggestions (engine and HTTP); no code outside `PUT /settings` writes them |
| Mutation spot-check | 16/17 at first: the button-press test pressed a stale button, whose fixed reply was already excluded, so a suggestion on button presses went unnoticed. The test now uses a button whose reply is generated. **Now 17/17** |
| Hedge rate | Single messages: 0/85 Phase 2 benign messages, 1/22 psychoeducation near-misses ("…is normal I guess, I'll be fine"), 0/23 psychoeducation triggers, 2/104 labelled conversation turns ("I feel kind of empty…", "work has been ok I guess"). Suggestions along the 24 labelled conversations: 0 |
| Speed (dev machine) | Settings read (SQLite) p50 0.42 ms, p99 0.81 ms per turn; suggestion check p50 0.05 ms, p99 0.07 ms on a 60-word message. Longest style line 183 characters (~52 tokens) |
| Browser | Segmented controls with examples, saved on click ("Saved. The next reply uses it."); unsaved session told the choices last as long as the conversation; help card opened "Your chosen country: United Kingdom" with the list folded under "Not right?"; with Formal set, the real model wrote "I am here to listen if you wish to share more…" and "It appears you are feeling fatigued…" with no contractions; the note appeared on the hedged message after an answered one, linking to `settings.html`; no console errors; no sideways scrolling at 375 px |
| Real-model tone check per style (Qwen3.5-4B Q4_K_M, dev machine, 70 turns each; transcripts `phase-11-tone-*.md`) | First drafts passing every check: direct+casual 50/70, direct+formal 31/70, gentle+casual 45/70, gentle+formal 39/70 (Phase 7 default 46/70). Fallbacks: 2, 0, 2, 3 (Phase 7: 2, both timeouts). Of the 7, 5 are guard fallbacks: 4 on good news ("That is wonderful news…" fails `no_praise`) and 1 on a medication refusal not in the allowed "can't tell you if" form; 2 are timeouts. No unsafe reply reached the user in any style. Repeated openers 0-2 of 6 per conversation |
| Style followed | Gentle clearly ("Perhaps…", "It might be that…", "I wonder if…"); formal clearly (no contractions, measured wording); direct shorter and plainer but close to the default; casual weakly, close to the default |

## 4. Known limits

- **Formal replies failed `validate_first` more often** (30/70 and 25/70 first drafts, against 13/70 by default): they acknowledged in words the list lacked ("I understand that…", "You mentioned that…", "I hear how…", "It is natural to…", "It might be that you feel…"). Each miss cost a retry: the direct+formal run took 17 minutes against 12 for direct+casual. **Fixed** (Smriti, 2026-10-24): those phrases were added (CR-14), with curated good and bad replies. Re-scoring the saved first drafts: direct+formal 30 → 18, gentle+formal 25 → 13, the Phase 7 default 13 → 9. The rest mostly open with a judgement or advice ("Staying late every night shows dedication…"), which the check should flag. Not yet re-run on the model.
- **Good news under a non-default style** brought out "That is wonderful news", which `no_praise` blocked; four turns ended on the companion fallback. **Fixed** (Smriti, 2026-10-24): "…news" no longer counts as praise and counts as an acknowledgement; praise of the person in the same reply still fails. Re-scoring: every good-news praise block cleared.
- **Casual and direct are only weakly followed** by the 4B model; a stronger sentence or an example in the framing (CR-25) may be needed.
- **The hedge list is a phrase list.** "What kind of music" counts as a hedge; one stray match never suggests anything, because two of the last three messages must be hedged. Its recall on real hedged writing is unmeasured (no labelled set), and it is English-only.
- **The suggestion only points one way.** It suggests the gentle style; nothing suggests direct, casual or formal, which users pick themselves.
- **A message sent before the previous reply arrives** is answered without that previous message in its history (seen in the browser check: Enter submits while the Send button is disabled). That pre-dates this phase; here it only delays a suggestion by one message.
- **The chosen country is read when the chat page loads,** so a change in Settings shows on the next visit to the chat page, which is how the Settings link works today.
- **Fixed replies do not change with the style:** crisis, post-crisis, questionnaire and offer texts are vetted wording (by design).
- English only.
