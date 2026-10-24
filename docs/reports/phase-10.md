# Phase 10 — Privacy and autonomy

**Goal.** The user controls their data, and OASIS says plainly what it keeps before the first message (FR-PRV-1 to FR-PRV-6, PRD L5): a first-use notice whose acceptance gates the chat, a choice between saving on this computer and not saving at all, export of everything kept, and delete that leaves nothing readable behind.

**Report topic.** Privacy by design for a sensitive-data chatbot; verifiable erasure.

## 1. Design

| Component | File | Role |
|---|---|---|
| Data notice | `content/privacy/disclosure.yaml` (CR-23), `api/pages.py` | Versioned plain-language notice rendered into the chat page on the server. First two sections shown, the rest under a native "Read more" dropdown; the agreement line stays above the two start buttons |
| Consent | `storage/migrations/0006_consent.sql`, `POST /consent`, `GET /session` | One row per user with the accepted notice version, plus a `consent_given` audit entry. The request must name the version on screen |
| Consent gate | `core/engine.py` | After the safety gate and state load: no reply until the current notice is accepted (`403 consent_required`); a crisis is always answered |
| Saved or unsaved | `storage/split.py`, `storage/memory.py`, `POST /session {ephemeral}` | Each session lives in SQLite or in memory, chosen at the start; every call goes to the store holding it. Unsaved users are forgotten after 2 hours idle and on restart |
| Export | `GET /export`, `export_user` in both backends | Everything kept about the user as one JSON download |
| Delete | `DELETE /account`, `delete_user` in both backends | Two-step confirmation; one cascading delete, zeroed pages, emptied WAL; honest report when another program blocks the overwrite |
| Pages | `web/index.html`, `app.js`, `settings.html`, `settings.js`, `styles.css` | Onboarding in place of the chat until consent; Settings (gear icon) with the mode, Export and Delete |
| Help card | `content/help/time_zones.yaml`, `scripts/time_zones.py`, `api/pages.py`, `app.js` | Opens the country of the computer's time zone first (CR-24), added in this phase at the owner's request |

**Where the key lives** (rules F5, changed 2026-10-24). The session key is the only thing the browser stores. A saved session's key is in `localStorage`, so the conversation can be reopened in a new tab or after a restart; an unsaved session's key is in `sessionStorage`, so closing the tab ends access to it. The notice says that anyone who uses this browser on this computer can open a saved conversation, and suggests "Start without saving" on a shared computer. The notice went to version 2 for this; a session that accepted an older version sees the notice again with a single "Accept and continue" button that re-consents that same session, so a saved conversation is never stranded by a new notice.

**The notice** (CR-23) covers what OASIS is and is not, the two ways to start, what is kept, the crisis-message policy, who can see the data, and the user's choices. Choosing "Save on this computer" or "Start without saving" is the consent: the page creates the session, then posts the version it showed. A newer version in the file asks everyone again.

**Self-harm disclosure policy** (PRD L5), as stated in the notice and as built since Phase 2: the words of a message answered with crisis support are never saved. OASIS keeps a note that crisis support was shown, which kind of phrase was recognised (pattern IDs and tiers, never words) and a placeholder line in the conversation; all of it is exported and deleted with everything else. This bookkeeping also runs for a session that has not consented yet (Smriti, 2026-10-24); through the page that cannot happen, as the message box is hidden until consent.

**Consent gate and safety order** (architecture §3.3). The gate sits in the engine, not in front of it: safety runs first on every message, so a crisis is answered from any session, consented, unconsented or unknown. A session that accepted the notice is remembered in memory, so a storage outage does not lock it out; a session whose consent cannot be checked gets `403` for anything but a crisis. Nothing is stored for a refused message.

**Saved or unsaved.** `SplitRepository` holds the SQLite store and an in-memory one. A session is created in one and stays there; every repository call is routed by the session hash or the user ID, so an unsaved conversation never touches the database file, not even for a read, and keeps working while the database is down. The in-memory store keeps the same fields SQLite does, so either one exports the same tables and columns. An unsaved user is forgotten after 2 hours without a request: the check runs on every request of any session, so idle data does not wait for another unsaved user to arrive.

**Export** returns `{format, exported_at, ephemeral, tables}`. SQLite finds every table with a `user_id` column from the schema itself, so a table added by a later migration is exported with no code change. The session key is never in it: only its hash is stored. Settings saves the file from the page, so it never leaves the computer.

**Delete** removes the `users` row, which cascades to every table (design §11). With `secure_delete` on, freed pages are zeroed; `wal_checkpoint(TRUNCATE)` then copies them into the main file and empties the WAL, so the deleted text is in neither. Testing showed one case this does not cover: when another program holds the file open mid-read (a database browser, a backup tool), SQLite does not raise, it reports the checkpoint busy and leaves the old text on disk, even if that program started reading when the WAL was empty, so checking before deleting would not catch it. The delete therefore checks the result: the rows are gone at once, the API answers `503 erasure_pending` and Settings says so in plain words, and the store retries the overwrite after every later call (never waiting for the other program) and at startup, until it succeeds.

**Help card country** (added at the owner's request, CR-24). Opening "Need help now?" shows the country of the computer's time zone first, already open, with the full list folded under "Not right? Choose another country". The time zone is read in the browser and never sent or stored, with no permission prompt; with no match, no script or the backend down, the list shows open as before. The map of 500 zone names comes from the IANA time zone database through `scripts/time_zones.py`; older names that browsers still report (Chrome: `Asia/Calcutta`) are included only when they belong to exactly one country. Browser location was considered and not used: rules P6 block it, a desktop browser asks an online location service, and the first use would put a permission prompt over the card. The card's opening line lost "pick your country below" (CR-03, owner's decision).

**Departures from the phase plan.**
- The notice is YAML rendered on the server, not `disclosure.md`, and onboarding is part of the chat page, not `onboarding.html`.
- No `api/routes_privacy.py`, `storage/export.py` or `storage/delete.py`: one route each in `routes.py` and one method per backend.
- Migration `0006_consent.sql` (0004 and 0005 were taken by Phases 8 and 9).
- No separate "withdraw consent" control: Delete removes the consent with everything else.
- No `export` audit event: the export is its own record, and audit rows are deleted with the account.
- The in-memory store has no `asyncio.Lock` (design §11.1): its methods never await, so each is atomic on the one event loop.
- The chosen-country setting moved to Phase 11 (Smriti, 2026-10-23); the time-zone suggestion was added instead.

## 2. Evaluation method

- **Consent gate (engine):** no reply and nothing stored before consent; a crisis answered before consent; an older notice version refused; remembered consent survives a storage outage; unknown consent during an outage refused while a crisis is answered; deleting forgets the remembered consent.
- **Consent over HTTP:** 403 then 200 after consent; the version must be the current one (422 otherwise); unknown session 401; `GET /session` reports mode and consent; consent is audited. Every earlier HTTP test now consents first, through one helper.
- **Storage contract (both backends):** consent round trip and replace; export holds every record of the user and no one else's; both backends give the same tables and columns; delete removes everything of that user only; unknown user is a no-op.
- **Erasure (SQLite, real files):** a schema crawl finds every table with a `user_id` column (at least 8) and counts zero rows after delete; a marker phrase written 20 times is gone from the `.db` and `-wal` files after delete, with another user's rows still present until they are deleted too; the WAL is empty after delete. With a second connection holding the file open mid-read: the delete reports `ErasureIncomplete`, the rows are gone, the marker is still on disk, and the next call finishes the overwrite; a still-blocked retry returns in under 0.5 s; after a restart while the other program still holds the file, the overwrite finishes once it lets go.
- **Unsaved sessions:** expiry with a fake clock, activity keeping a session alive, no expiry for the plain memory backend; an idle unsaved user forgotten on a saved session's request; the split store keeps unsaved sessions out of SQLite and works with SQLite down. Over HTTP, an unsaved session that chats, opens an explanation, the trend, the export and deletes leaves every file in the data folder byte-identical.
- **HTTP export and delete:** attachment header, `no-store`, the user's own words in, another user's and the session key out, for saved and unsaved sessions; delete needs `{"confirm": "DELETE"}`, then every endpoint answers 401 and a crisis is still answered; the marker is gone from the database files; logs hold no message text or session key through consent, export and delete; a blocked overwrite answers `503 erasure_pending` and ends the session.
- **Notice:** it must mention not a diagnosis, emergency, crisis, export, delete, without saving, this computer and no one else, with no external links; seven kinds of invalid file are rejected; text is escaped; the fold falls after "Two ways to start" and the agreement stays outside it.
- **Help card:** zone names map to their country, including Chrome's older names; names shared by several countries are left out; the committed map is exactly the script's output; each country carries its zones and none appears twice; the list is one dropdown that starts open; the page script folds it under "Not right?" only after a suggestion and never makes a request.
- **Mutation spot-check:** 25 deliberate faults across the gate, the routes, both backends, the split store, the help card and the zone script, each run against the privacy, storage, contract, engine, fault-injection, logging, help-card and HTTP tests, then restored.
- **Browser check** (dev server, real SQLite file): onboarding, both ways to start, export, a refused and an accepted delete, reload, phone width; a saved conversation reopened in a new tab, an unsaved one not; a session with an older consent shown "Accept and continue" and kept; the help card with this computer's zone, with UTC and with New York (simulated in the page).
- **Key storage:** only the session key is ever written to browser storage, in `localStorage` for saved and `sessionStorage` for unsaved sessions, and every page reads both; a newer notice is accepted on the same session and its history stays.

## 3. Results

| Check | Result |
|---|---|
| `scripts/verify.py` | All 8 steps pass (one earlier run failed pip-audit on new `filelock` advisories; upgraded to 4.2.4) |
| Tests | 1375 passed, 0 skipped |
| Coverage | 98.35% overall; `storage/memory.py` 99%, `storage/split.py` 98%, `storage/sqlite.py` 97%, `api/pages.py` 98%, `api/routes.py` 95%, `core/engine.py` 96%; `oasis.router` 100%, `oasis.assessment` 97.8%, `oasis.safety` 97.1% |
| Done-when: notice gates the API | 403 `consent_required` before consent on every non-crisis message; crisis answered from unconsented and unknown sessions |
| Done-when: export round-trips | Both backends export the same 8 tables with the same columns; the user's own rows only, the session key never |
| Done-when: delete leaves zero rows | Schema crawl over every table with a `user_id` column: 0 rows; marker absent from `.db` and `-wal`; WAL 0 bytes. Dev database in the browser check: the marker was in the WAL before, in no file after, WAL 0 bytes |
| Done-when: no content in logs | Marker words and session key absent from captured logs through consent, chat, export and delete |
| Done-when: ephemeral leaves no files | Every file in the data folder byte-identical before and after an unsaved session that chatted, opened an explanation, the trend and the export, and deleted; in the browser, the unsaved marker never reached the dev database |
| Blocked overwrite (measured) | With another connection mid-read, SQLite reported the checkpoint busy, raised nothing and left the marker in the WAL and the main file, also when that reader started on an empty WAL. Now reported as `erasure_pending`, finished on the next call (still-blocked retry under 0.5 s) or at startup |
| Mutation spot-check | 23/25 at first. Both misses were test gaps: the expiry test's own last check called `has_user()`, which runs the expiry and hid a missing call; and the startup test let the other program close first, when SQLite finishes the overwrite by itself as the last connection closes. The startup retry matters when OASIS restarts while the other program still holds the file; both tests were tightened. **Now 25/25** |
| Speed (dev machine, SQLite) | Export: 2.4 ms for 100 turns (54 KB), 10.9 ms for 1,000 turns (533 KB). Delete including the checkpoint: 10.2 ms and 22.3 ms. Memory store, 1,000 turns: export 10.5 ms, delete 1.3 ms. Expiry check per request: 2 µs with 10 unsaved sessions, 108 µs with 1,000 |
| Help card | The time-zone data adds 10 KB to a 61 KB card. This computer (`Asia/Calcutta`) opened on India; New York gave the United States; UTC and a malformed name gave no suggestion and the list stayed open |
| Browser | Onboarding before the chat with "Need help now?" reachable; "Start without saving" and "Save on this computer" both worked; a reload and a new tab both reopened a saved conversation without the notice (the first new tab, opened while the first reply was still being saved, showed no messages until reloaded); an unsaved session's key stayed out of `localStorage` and a new tab showed the notice; a session with an older consent got one "Accept and continue" button and kept its conversation; export saved `oasis-export.json` with every table (the download was intercepted in the page, not written to disk); "delete" refused, "DELETE" accepted, then back to the notice; no console errors; no sideways scrolling at 375 px |

## 4. Known limits

- **The key to a saved conversation sits in the browser profile.** Anyone who uses this browser on this computer can open, export or delete the conversation; the notice says so and suggests "Start without saving" on a shared computer. Clearing the browser's site data loses the key, and the conversation then stays in the file with no way to reach it from OASIS (Phase 13 brings proper returning users).
- **"Nothing written to disk" means OASIS writes nothing.** The operating system may still page process memory to its swap file, and SQLite's zeroing cannot reach copies made by SSD wear levelling, backups or file-sync tools. The notice recommends disk encryption (PRD §6.3).
- **Expiry is lazy.** An idle unsaved conversation is forgotten on the next request of any session after 2 hours; if no one uses OASIS at all, it stays in memory until the process stops.
- **A blocked overwrite finishes later, not at once.** While another program keeps the file open, the deleted text stays in the file; the user is told, and OASIS finishes as soon as it can.
- **Consent memory grows** with each consented session until restart, like the post-crisis set (session hashes only).
- **The export is raw:** table rows with JSON columns (traces, explanations, features). Complete, but not a friendly read.
- **Wording not yet reviewed:** the notice needs legal review (PRD O8) and clinician review (CR-23); like the crisis reply (CR-03) it points to "Need help now?" rather than to the emergency number. The time-zone suggestion is wrong on a computer set to another country's time (CR-24).
- English only.
