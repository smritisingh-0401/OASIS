# Phase 8 — Sentiment tracking

**Goal.** A mood trend built only from the user's own words, always labelled honestly: **"language-based mood trend, not a clinical measure"** (FR-TRK-1 to FR-TRK-4).

**Report topic.** Text-derived behavioural signals and their limits.

## 1. Design

| Component | File | Role |
|---|---|---|
| Per-turn features | `tracking/features.py` | `turn_features(message, signals, received_at, last_reply_at, client_ts)` returns a `TurnFeatures` of numbers only. The engine calls it at stage 8 for every typed user message |
| Citations and word lists | `content/tracking/features.yaml` | The label, the aggregation settings, the first-person and absolutist word lists, the negation list, and a source or "exploratory" for every feature (CR-21). A bad file stops startup |
| Storage | `storage/migrations/0004_turn_signals.sql`, both repositories | `append_signals` / `list_signals`. One JSON row of numbers per message, scoped to the user and deleted with them |
| Aggregation | `tracking/aggregate.py` | Per-session mean and sample variance of every feature; EWMA over session mean valence; the change flag against the user's own earlier sessions |
| Trend API | `GET /trends` (`api/routes.py`, `api/schemas.py`) | Label, per-feature source and note, sessions (means, variances), EWMA, change flags, and this session's valence per message |
| Trend view | `web/trends.html`, `web/trends.js`, `styles.css` | Linked from the chat header ("Mood trend"). Two plain SVG charts and the list of sources; the label is always visible |

**The features** (design §9.1):

| Feature | Definition | Basis |
|---|---|---|
| `valence` | VADER compound, −1 to 1 | Hutto & Gilbert (2014): validated for the sentiment of short social-media texts, not for mood |
| `fp_pronoun_rate` | I, me, myself (and I'm, I've, I'd, I'll, im, ive) per word | Tackman et al. (2019): a small effect (r = .10, 4,754 people), better read as distress proneness than depression |
| `absolutist_rate` | 19 absolutist words per word, a word right after a negation or qualifier left out | Al-Mosaiwi & Johnstone (2018): forum-level, observational |
| `sadness` … `loneliness` | The Phase 4 emotion lexicon scores | Exploratory |
| `msg_length` | Words | Exploratory |
| `reply_latency_s` | Since OASIS's last reply in the session, server time, capped at 600 s; none on the first message | Exploratory |
| `hour_of_day` | The user's local hour from the browser's clock | Exploratory |

**Aggregation** (design §9.2): sessions are ordered by their first message. Each session gets the mean and sample variance of every feature; missing values (the first message's latency) are left out, and one value gives no variance. The trend is an EWMA over session mean valence, `e₁ = x₁, eₜ = 0.3·xₜ + 0.7·eₜ₋₁`. A session is flagged when at least 5 sessions come before it and its mean valence lies more than 1.5 sample SDs from theirs; a baseline with no spread flags nothing.

**What is not recorded:** button presses (their label is not the user's words) and crisis messages (nothing runs after a crisis verdict, rules S3). A failed feature write never fails the turn; it shows as `storage.down` in the turn's degraded list.

**Sources were checked** on 2026-10-20 by search, not from memory: VADER against its AAAI ICWSM page; Al-Mosaiwi & Johnstone against the full text on PubMed Central; Tackman et al. against its abstract and the University of Arizona summaries (the full text was not opened). That check changed the design in one place: Tackman et al. found the depression link for every first-person singular form **except possessive "my"**, so `my` and `mine` are not counted. The paper confirms its absolutist dictionary has 19 words and names several; the full list is in its supplementary Table S2, which could not be opened, so the list is as quoted from that table by several secondary sources (flagged in CR-21).

**Decision on returning users** (Smriti, 2026-10-20). Today every new browser session creates a new pseudonymous user (the token lives in `sessionStorage`), so one person never builds up several sessions. Phase 8 builds the cross-session trend and the change flag exactly as designed and proves them on synthetic timelines. The trend view shows this conversation's line now and says plainly that the cross-session line fills in when there are more conversations to compare. Returning users wait for the Phase 10 consent, export and delete, and the Phase 13 session continuity, so no persistent identity arrives before its safeguards.

**Departures from the phase plan.**
- **Migration `0004_turn_signals.sql`**, not `0003_signals.sql`: 0003 was taken by the Phase 3 assessments.
- **Possessives left out** of the first-person rate (above).
- **No Welford update.** The design named Welford's method for the session variance; aggregates are recomputed from the stored features on each request with `statistics`, so there is no running state to keep consistent. Rebuilding 1,000 messages takes ~50 ms, and only when the trend page is opened.
- **`web/trends.js` added:** the content security policy allows scripts only from files.
- **The browser now sends its local time with its offset** (it sent UTC before), so the local hour can be read.
- **Export and delete** arrive in Phase 10. The new table is deleted with the user (tested), so delete will cover it; the export will need to include it.
- **The planner does not read the trend yet** (architecture §2.17 says it will, as part of state). No phase uses it so far, so it is not wired.

## 2. Evaluation method

- **Golden features:**
  - A fixed message with known word, pronoun and absolutist counts.
  - Each pronoun form, including "my", "mine", "ill" and "id", which must not count.
  - Curly apostrophes.
  - Negated and qualified absolutist words ("not completely", "almost completely", "isn't always").
  - A message with no words.
  - Valence and emotion scores equal to the signals.
- **Latency and hour:** absent on the first message; 42 s measured; 2 hours capped at 600 s; clock skew clamped to 0; the client's local hour (23 for 23:30+05:30), none without a client time.
- **Citations:** every feature has exactly one of a source or "exploratory"; the three cited features have sources; the label is exact. Nine kinds of invalid config are rejected (approved review status, a missing or extra feature, both or neither, another label, out-of-range α or K, an empty word list).
- **Aggregation on synthetic timelines:**
  - Exact mean and sample variance (0.13 for 0.2, 0.4, 0.9); sessions ordered by first message.
  - Missing latencies left out of the mean.
  - EWMA against the recurrence (0, 0.3, 0.51).
  - The change flag does not fire on a drop in the 5th session (4 before it), but fires on the same drop in the 6th; 1.0 SD away is not flagged, 2.0 SDs is, in either direction; a flat baseline flags nothing.
  - The full trend for the current session.
- **Storage contract** (both backends): round trip in order and per user; another user's session is rejected. SQLite: the rows are deleted with their user.
- **Engine:** a typed turn records its features (numbers only, local hour, latency on the second turn); crisis and button turns record none; a failed feature write leaves the reply intact; latency counts from the last reply, not the last turn.
- **HTTP and page:** `/trends` returns the label, sources and this session's points; it needs a valid session (401 otherwise); the page always shows the label and loads its script; the chat links to it; in-memory storage writes nothing to disk; the existing no-external-requests guard covers the new files.
- **Mutation spot-check:** 12 deliberate faults (counting "my", counting negated uses, no latency cap, population variance, swapped EWMA weights, flagging before a baseline, a one-sided flag, recording button turns, the hour in UTC, unordered sessions, a reworded label, latency from any turn), each run against the unit, contract and integration tests, then restored.
- **Browser check:** three messages through the dev server, then the trend page at desktop and phone width (375 px).

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass |
| Tests | 1209 passed, 0 skipped |
| Coverage | 98.5% overall; `oasis.tracking` 100%, `oasis.router` 100%, `oasis.assessment` 97.8%, `oasis.safety` 97.1% |
| Mutation spot-check | 11/12 caught at first. The miss (latency from the last turn of any kind instead of OASIS's last reply) changes nothing while the newest turn is a reply, so no test told them apart; a direct test was added. **Now 12/12** |
| Speed (dev machine) | Features: p50 0.031 ms, p99 0.047 ms per message. The engine runs the signal extraction a second time for the features (~0.2–1.4 ms). Trend over 50 sessions × 20 messages: p50 51 ms, on page open only |
| Browser | "I always mess everything up at work" → −0.36; "I had a nice walk this evening though" → 0.42; "Honestly I feel a bit better now" → 0.71, drawn as a rising line with "on average more positive words". Local hour 19 recorded for 13:55 UTC in India (+05:30). No console errors; no sideways scrolling at 375 px; the chat header fits "Mood trend" beside "Need help now?" |

## 4. Known limits

- **Not a measure of mood.** Every feature describes word choice. VADER was validated on the sentiment of social-media posts, the pronoun effect is small (r = .10) and points to general distress proneness, and the absolutist finding compares whole forums, not people. The label and the page say this; the trend must never feed a clinical decision.
- **No cross-session trend for real users yet.** Each browser session is a new user until Phase 10 / 13, so the "Across conversations" line and the change flag only work on synthetic data for now.
- **The change flag is statistical, not clinical:** 5 earlier sessions and 1.5 SDs are engineering defaults (CR-21). Short sessions give noisy means; one long session weighs the same as one short one.
- **Word counting is simple.** Words are split on letters and apostrophes, so numbers and emoji are not counted; the negation check looks only at the word directly before; "all" and "ever" are absolutist in every use, as in the dictionary. Emotion features reuse lexicons built for routing, not for tracking.
- **The absolutist list comes from secondary sources** quoting the paper's Table S2; it should be checked against the table.
- **Latency and hour of day depend on circumstances,** like stepping away or the time zone setting of the device, more than on mood. Both are exploratory.
- **The signal extraction runs twice per turn** (planner and features). It costs about a millisecond, so it is left as is.
- English only; the word lists, thresholds and page wording await clinician review (CR-21).
