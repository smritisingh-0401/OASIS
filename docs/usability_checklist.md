# Usability checklist

Heuristic review of the chat, help card, onboarding, settings and mood-trend pages (Phase 13, PRD L10). It was done in the browser on the reference laptop, at desktop width and at 375 px, with the keyboard only and with the server stopped. There were **no participants**: testing with people needs ethics approval first (open item O4).

Each item says what was checked and how. ✓ means it passed. **Fixed** means it failed and was fixed in Phase 13, with a test. **Open** means it is listed for later.

Run the automated part again with:

```bash
uv run pytest tests/unit/test_contrast.py tests/unit/test_web_ui.py tests/unit/test_help_card.py
```

## Nielsen's ten heuristics

| # | Heuristic | What was checked | Result |
|---|---|---|---|
| 1 | Visibility of system status | The status line while waiting; "This message may not have been saved." under a reply when storage failed; the offline message with the server stopped; the "Why this reply?" panel saying when an explanation is unavailable | ✓ |
| 2 | Match with the real world | Plain-language notice, buttons named by outcome ("Save on this computer", "Start without saving"), crisis lines by country with the hours | ✓ |
| 3 | User control and freedom | Stop and Pause on questionnaires and exercises; "Not now" on offers; delete everything in Settings. The help card covers the chat but did not close with Escape: **Fixed**, Escape now closes it and returns focus to "Need help now?" | Fixed |
| 4 | Consistency and standards | Same glass panels, pill buttons and focus ring on every page; native `<details>` for the notice, the help card and "Why this reply?" | ✓ |
| 5 | Error prevention | Delete asks you to type a confirmation. Pressing Enter while a reply was pending sent a second message, and that message was answered without the first one in its history: **Fixed**, Enter now waits and keeps the text | Fixed |
| 6 | Recognition rather than recall | Questionnaire answers are buttons with the full option text; the open questionnaire or exercise card comes back after a reload or restart | ✓ |
| 7 | Flexibility and efficiency | Enter sends and Shift+Enter starts a new line; the help card opens on the time-zone country first, with every other country one tap away | ✓ |
| 8 | Aesthetic and minimalist design | One panel and one action per screen; the notice puts the rest under "Read more" | ✓ |
| 9 | Help users recover from errors | Every failure gives a reply or a plain message (fault-injection matrix, design §16). Offline, the typed message stays in the box | ✓ |
| 10 | Help and documentation | "Need help now?" on every page, which works offline; "Why this reply?" under each reply; the README | ✓ |

## WCAG 2.2 AA

| Criterion | What was checked | Result |
|---|---|---|
| 1.3.1 Info and relationships | Headings in order (h1 OASIS, h2 per panel, h3 per section); every control has an accessible name (script check: none unnamed on the chat, settings or trend page) | ✓ |
| 1.4.3 Contrast (minimum) | `scripts/contrast_check.py`: 33 text and background pairs, each translucent layer composited over every colour that can show through it, worst case counted. 7 failed over the darkest orb under the clear chat glass (Phase 11): the pill and help-button accent (4.04:1), "Why this reply?" on the blue bubble (2.98:1), and muted text on the panel (3.63:1). **Fixed** with three colour tokens (`--accent` #1e4aa8, `--accent-deep` #1e3f8f, `--muted` #283244). Now 33/33, checked in CI | Fixed |
| 1.4.10 Reflow | 375 px: no sideways scrolling on any page. The help card ran 55 px off the left edge, cutting off the start of every crisis line: **Fixed**, on narrow screens it now spans the header with 16 px on each side | Fixed |
| 2.1.1 Keyboard | Onboarding, chat, help card, the "Read more" and "Why this reply?" disclosures, and Settings all work with Tab, Enter and Escape only | ✓ |
| 2.4.3 Focus order | Mood trend, Need help now?, Settings, Read more, then the two start buttons; after starting, focus goes to the message box and stays there after each reply | ✓ |
| 2.4.7 Focus visible | 3 px outline in `--focus` on every focusable element | ✓ |
| 2.5.8 Target size (minimum) | "Why this reply?" was 114×22 px, and the help card's short numbers ("15", "112") were 20–31 px wide: **Fixed**, both now at least 24 px. Script check at 375 px: no control under 24 px | Fixed |
| 4.1.3 Status messages | New messages and the status line are `aria-live="polite"`; the message list is `aria-busy` while waiting | ✓ |
| Reduced motion | `prefers-reduced-motion` turns off smooth scrolling and transitions | ✓ |

## Open

- **Contrast is checked from the stylesheet, not the rendered pixels.** The `backdrop-filter` blur and saturation are not modelled. They average neighbouring colours, so the composited worst case is the stricter bound.
- **No screen-reader walkthrough.** A walkthrough with NVDA or Narrator is not done; roles, names and live regions were checked in the DOM.
- **No participant testing**: ethics approval comes first (O4).
