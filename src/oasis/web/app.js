"use strict";

// The session token is the only thing kept in the browser (rules F5, see saveToken) and is
// sent only in the X-OASIS-Session header, never in a URL (rules P3). All text is rendered
// with textContent (rules F4).

const SLOW_NOTICE_MS = 8000;

const messages = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendButton = document.getElementById("send");
const status = document.getElementById("status");
const help = document.getElementById("help");
const continueButton = document.getElementById("continue");
const card = document.getElementById("card");
const onboarding = document.getElementById("onboarding");
const CONTINUE_TEXT = "I'd like to keep talking.";

// After a crisis reply, open the help card and move focus to it so crisis lines are one
// step away; the "Continue talking" button lets the user leave post-crisis mode.
function showCrisisSupport() {
  help.open = true;
  help.querySelector(".help-card").focus();
  continueButton.hidden = false;
}

// Opens the country chosen in Settings first, or else the computer's own country (decision
// 2026-10-24). The chosen one is fetched when the chat loads; the time zone is read from the
// browser's own settings, never sent anywhere and never stored. Either way the card itself
// needs no request, so it works with the backend down. Each country in the server-rendered
// card lists its zone names in data-zones; a copy of the match goes on top, and the full list
// folds into a "Not right?" dropdown.
const ZONE_NAME = /^[A-Za-z0-9_+-]+(\/[A-Za-z0-9_+-]+)+$/;
const COUNTRY_CODE = /^[A-Z]{2}$/;
let chosenCountry = "";

function suggestCountry() {
  const helpCard = help.querySelector(".help-card");
  if (helpCard.querySelector(".suggested")) return;
  let label = "Your chosen country:";
  let match = COUNTRY_CODE.test(chosenCountry)
    ? helpCard.querySelector(`.country#crisis-${chosenCountry}`)
    : null;
  if (!match) {
    let zone = "";
    try {
      zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      return;
    }
    if (!ZONE_NAME.test(zone)) return;
    label = "From this computer's time zone:";
    match = helpCard.querySelector(`.country[data-zones~="${zone}"]`);
  }
  if (!match) return;
  const copy = match.cloneNode(true);
  copy.removeAttribute("id");
  copy.removeAttribute("data-zones");
  copy.open = true;
  const box = document.createElement("div");
  box.className = "suggested";
  box.append(line("p", label, "help-pick"), copy);
  // The full list folds away under "Not right?"; without a suggestion it stays open.
  const others = helpCard.querySelector(".all-countries");
  others.open = false;
  others.querySelector("summary").textContent = "Not right? Choose another country";
  others.before(box);
}

help.addEventListener("toggle", () => {
  if (help.open) suggestCountry();
});

// The card opens over the chat: Escape closes it and returns focus to "Need help now?".
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !help.open) return;
  help.open = false;
  help.querySelector("summary").focus();
});

// A saved session's key goes in localStorage, so the conversation can be reopened in a new
// tab or after a restart; an unsaved one's in sessionStorage, so it ends with this tab
// (rules F5). An empty token forgets both.
function saveToken(token, ephemeral = false) {
  try {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    if (token && ephemeral) {
      sessionStorage.setItem(SESSION_KEY, token);
    } else if (token) {
      localStorage.setItem(SESSION_KEY, token);
    }
  } catch {
    // Storage blocked: the session lasts for this page only.
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" };
const OFFLINE = "I couldn't reach the server. \"Need help now?\" still works.";

const startSaved = document.getElementById("start-saved");
const startEphemeral = document.getElementById("start-ephemeral");
// The online demo never saves (the server enforces it), so it offers only "Start without saving".
const DEMO = document.querySelector(".demo-banner") !== null;
// True when the notice is shown again to a session that already exists (the notice changed):
// accepting continues that conversation instead of starting a new one, so a saved
// conversation is never stranded.
let resuming = false;

// The data notice replaces the conversation until a session has accepted it (FR-PRV-1).
function showOnboarding(note, resume = false) {
  resuming = resume;
  startSaved.textContent = resume ? "Accept and continue" : "Save on this computer";
  startEphemeral.hidden = resume;
  startSaved.hidden = DEMO && !resume;
  onboarding.hidden = false;
  messages.hidden = true;
  form.hidden = true;
  card.hidden = true;
  newChat.hidden = true;
  status.textContent = note || "";
  if (!help.contains(document.activeElement)) (startSaved.hidden ? startEphemeral : startSaved).focus();
}

async function postConsent(token, version) {
  const resp = await fetch("/consent", {
    method: "POST",
    headers: { ...JSON_HEADERS, "X-OASIS-Session": token },
    body: JSON.stringify({ disclosure_version: version }),
  });
  if (!resp.ok) throw new Error("consent");
}

function showChat() {
  onboarding.hidden = true;
  messages.hidden = false;
  form.hidden = false;
  newChat.hidden = false;
}

// New chat (demo testing, 2026-10-29): a fresh conversation for the same person, only when
// they ask. The earlier one stays in Mood trend; this browser keeps only the new key.
const newChat = document.getElementById("new-chat");
const emptyState = messages.querySelector(".empty-state").cloneNode(true);

newChat.addEventListener("click", async () => {
  if (sendButton.disabled) return;
  const sure = window.confirm(
    "Start a new conversation? This one stays in Mood trend, but you can't come back to it here.",
  );
  if (!sure) return;
  try {
    const resp = await api("/session/new", { method: "POST" });
    if (resp.status === 401) {
      saveToken("");
      return showOnboarding();
    }
    if (!resp.ok) throw new Error("new chat");
    const session = await resp.json();
    saveToken(session.session_id, session.ephemeral);
    messages.replaceChildren(emptyState.cloneNode(true));
    continueButton.hidden = true;
    card.hidden = true;
    newMessage.hidden = true;
    status.textContent = "New conversation started.";
    input.focus();
  } catch {
    status.textContent = OFFLINE;
  }
});

// Choosing how to start creates the session and records consent to the notice shown.
async function start(ephemeral) {
  const version = onboarding.querySelector(".notice").dataset.version;
  try {
    if (resuming) {
      await postConsent(readToken(), version);
      status.textContent = "";
      showChat();
      await loadHistory();
      input.focus();
      return;
    }
    const resp = await fetch("/session", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ ephemeral }),
    });
    if (!resp.ok) throw new Error("session");
    // The server decides whether the session is saved (the online demo never is).
    const session = await resp.json();
    const token = session.session_id;
    await postConsent(token, version);
    saveToken(token, session.ephemeral);
    status.textContent = "";
    showChat();
    input.focus();
  } catch {
    status.textContent = OFFLINE;
  }
}

async function init() {
  if (!readToken()) return showOnboarding();
  try {
    const resp = await api("/session");
    if (resp.status === 401) {
      saveToken("");
      return showOnboarding();
    }
    // Storage down: the chat may still answer, so let them try.
    if (resp.ok && !(await resp.json()).consented) {
      return showOnboarding("The data notice has changed. Please read it and accept to carry on.", true);
    }
    showChat();
    await loadHistory();
    loadSettings();
  } catch {
    showOnboarding(OFFLINE);
  }
}

// The help card's country from Settings. Best effort: without it the card uses the time zone.
async function loadSettings() {
  try {
    const resp = await api("/settings");
    if (resp.ok) chosenCountry = (await resp.json()).country || "";
  } catch {
    // The time-zone suggestion still works.
  }
}

// Shown once per tab when their recent messages are hedged (FR-CUL-2). It only points to
// Settings; the style changes only if they change it there.
let styleSuggested = false;

function styleNote() {
  const note = line("p", "You can ask OASIS to word things more gently in ", "note");
  const link = document.createElement("a");
  link.href = "settings.html";
  link.textContent = "Settings";
  note.append(link, ".");
  return note;
}

// The conversation scrolls inside the panel (demo testing, 2026-10-29). It follows new
// messages while the reader is at the bottom; scrolled up to read, they get a button instead.
const newMessage = document.getElementById("new-message");
const BOTTOM_SLACK_PX = 80;

function atBottom() {
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < BOTTOM_SLACK_PX;
}

function toBottom() {
  messages.scrollTop = messages.scrollHeight;
  newMessage.hidden = true;
}

function follow(stick) {
  if (stick) toBottom();
  else newMessage.hidden = false;
}

messages.addEventListener("scroll", () => {
  if (atBottom()) newMessage.hidden = true;
});
newMessage.addEventListener("click", toBottom);

// Three dots while OASIS writes; hidden from screen readers, which hear the status line.
function showTyping() {
  const item = document.createElement("li");
  item.className = "msg bot typing";
  item.setAttribute("aria-hidden", "true");
  item.append(document.createElement("span"), document.createElement("span"),
    document.createElement("span"));
  const stick = atBottom();
  messages.appendChild(item);
  follow(stick);
  return item;
}

// A reply types out word by word, at most TYPE_MAX_MS in all. It is already checked in full
// on the server; this only reveals it. Reduced motion shows it at once.
const TYPE_MS_PER_WORD = 40;
const TYPE_MAX_MS = 2000;
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

function typeOut(item, body, text) {
  const tokens = text.split(/(\s+)/);
  const words = tokens.filter((t) => t.trim()).length;
  const step = Math.min(TYPE_MS_PER_WORD, TYPE_MAX_MS / Math.max(words, 1));
  let shown = 0;
  body.textContent = "";
  const timer = setInterval(() => {
    const stick = atBottom();
    // One word and the space after it each tick.
    while (shown < tokens.length) {
      body.textContent += tokens[shown++];
      if (tokens[shown - 1].trim()) break;
    }
    if (shown >= tokens.length) {
      clearInterval(timer);
      item.classList.remove("typing-out");
      messages.setAttribute("aria-busy", "false");
    }
    follow(stick);
  }, step);
}

function addMessage(role, text, note, animate = false) {
  const item = document.createElement("li");
  item.className = "msg " + ({ user: "user", placeholder: "system" }[role] || "bot");
  const body = document.createElement("p");
  body.textContent = text;
  item.appendChild(body);
  const typing = animate && !REDUCED_MOTION.matches;
  if (typing) {
    // A screen reader hears the whole reply once, when the conversation is no longer busy.
    body.className = "reply-text";
    messages.setAttribute("aria-busy", "true");
    item.classList.add("typing-out");
  }
  if (note) {
    const small = document.createElement("p");
    small.className = "note";
    small.textContent = note;
    item.appendChild(small);
  }
  // Your own message always brings the conversation to the bottom.
  const stick = role === "user" || atBottom();
  messages.appendChild(item);
  follow(stick);
  if (typing) typeOut(item, body, text);
  return item;
}

function setBusy(busy) {
  sendButton.disabled = busy;
  for (const button of card.querySelectorAll("button")) button.disabled = busy;
  // A reply still typing out keeps the conversation busy until typeOut finishes.
  const typing = messages.querySelector(".typing-out") !== null;
  messages.setAttribute("aria-busy", busy || typing ? "true" : "false");
}

async function loadHistory() {
  if (!readToken()) return;
  try {
    const resp = await api("/history");
    if (resp.status === 401) {
      saveToken("");
      return;
    }
    if (!resp.ok) return;
    const body = await resp.json();
    for (const turn of body.turns) addMessage(turn.role, turn.content, "");
    // An open questionnaire picks up where it was: its buttons come back with the history.
    showCard(body);
    // Post-crisis mode outlives a reload, so the way out must too.
    const last = body.turns[body.turns.length - 1];
    if (last && (last.mode === "crisis" || last.mode === "post_crisis")) continueButton.hidden = false;
  } catch {
    // History is a convenience; the chat still works without it.
  }
}

function button(label, onClick, className) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  if (className) b.className = className;
  b.addEventListener("click", onClick);
  return b;
}

function line(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

// Each button sends its label as the message (kept in history, still safety-checked)
// and a structured action; answers are never parsed from free text (design §4.2).
function act(label, action) {
  return () => sendText(label, action);
}

// One card slot: a structured-mode offer or running exercise, else the questionnaire.
function showCard(body) {
  if (body.exercise) renderExercise(body.exercise);
  else renderCard(body.assessment);
}

function renderExercise(ex) {
  card.replaceChildren();
  card.hidden = false;
  card.setAttribute("aria-label", "Exercise");
  if (ex.step === "offer") {
    const options = document.createElement("div");
    options.className = "card-options";
    options.append(
      button("Yes, let's try", act("Yes, let's try", { type: "exercise_consent", accept: true })),
      button("Not now", act("Not now", { type: "exercise_consent", accept: false })),
    );
    card.append(line("p", "Try: " + ex.name, "card-title"), options);
    card.querySelector("button").focus();
    return;
  }
  // A running exercise is answered in words, so focus goes back to the message box.
  const controls = document.createElement("div");
  controls.className = "card-controls";
  controls.append(button("Stop exercise", act("Stop", { type: "exercise_stop" }), "link"));
  card.append(line("p", ex.name + " · Step " + ex.item + " of " + ex.item_count, "card-title"));
  // The fixed step text, in case the reply above phrased it loosely.
  if (ex.instruction) card.append(line("p", ex.instruction, "card-step"));
  card.append(line("p", "Reply in your own words when you're ready for the next step.", "card-hint"), controls);
  if (!help.contains(document.activeElement)) input.focus();
}

function renderCard(step) {
  card.replaceChildren();
  card.setAttribute("aria-label", "Questionnaire");
  card.hidden = !step || step.step === "result";
  if (card.hidden) {
    // The pressed button is gone; keep keyboard users in the conversation.
    if (!help.contains(document.activeElement)) input.focus();
    return;
  }
  const options = document.createElement("div");
  options.className = "card-options";
  const controls = document.createElement("div");
  controls.className = "card-controls";
  const stop = button("Stop", act("Stop", { type: "assessment_abort" }), "link");

  if (step.step === "offer") {
    card.append(line("p", step.name, "card-title"));
    options.append(
      button("Yes, let's start", act("Yes, let's start", { type: "assessment_consent", accept: true })),
      button("Not now", act("Not now", { type: "assessment_consent", accept: false })),
    );
    card.append(options);
  } else if (step.step === "paused") {
    card.append(line("p", step.name + " is paused.", "card-title"));
    options.append(button("Resume", act("Resume", { type: "assessment_resume" })));
    controls.append(stop);
    card.append(options, controls);
  } else {
    const title = step.step === "item"
      ? step.name + " · Question " + step.item + " of " + step.item_count
      : step.name + " · Last question";
    card.append(line("p", title, "card-title"));
    step.options.forEach((label, value) => {
      const answer = { type: "assessment_answer", value, instrument: step.instrument, item: step.item };
      options.append(button(label, act(label, answer)));
    });
    controls.append(button("Pause", act("Pause", { type: "assessment_pause" }), "link"), stop);
    card.append(options, controls);
  }
  card.querySelector("button").focus();
}

async function sendText(text, action) {
  const pending = addMessage("user", text);
  setBusy(true);
  status.textContent = "OASIS is thinking…";
  const dots = showTyping();
  const slow = setTimeout(() => {
    status.textContent = "Still working — this can take a few seconds on this computer.";
  }, SLOW_NOTICE_MS);

  try {
    const resp = await send(text, action);
    if (resp.status === 401 || resp.status === 403) {
      // Session gone (deleted, or an unsaved one forgotten) or not consented: back to the
      // notice. The words go back in the box for after they start again.
      const body = await resp.json().catch(() => ({}));
      pending.remove();
      if (resp.status === 401) saveToken("");
      // 403: the session still exists, so accepting continues it (a changed notice).
      const consent = body.error && body.error.code === "consent_required";
      showOnboarding(consent
        ? "Please read and accept the data notice first. Your message wasn't sent."
        : "Please choose how to start again. Your message wasn't sent.", consent);
      return false;
    }
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    // A crisis turn is never stored by design, so the not-saved note would only alarm.
    const note = body.persisted || body.mode === "crisis" ? "" : "This message may not have been saved.";
    dots.remove();
    // Crisis replies appear at once, never typed out.
    const animate = body.mode !== "crisis" && body.mode !== "post_crisis";
    if (body.preface) addMessage("assistant", body.preface);
    const reply = addMessage("assistant", body.reply, note, animate);
    if (body.style_suggestion && !styleSuggested) {
      styleSuggested = true;
      reply.appendChild(styleNote());
    }
    status.textContent = "";
    showCard(body);
    if (body.mode === "crisis" || body.mode === "post_crisis") {
      showCrisisSupport();
    } else {
      continueButton.hidden = true;
    }
    return true;
  } catch {
    // The message was not sent: take it out of the conversation and give it back.
    pending.remove();
    status.textContent =
      "I couldn't reach the server. Your message wasn't sent. \"Need help now?\" still works.";
    return false;
  } finally {
    dots.remove();
    clearTimeout(slow);
    setBusy(false);
  }
}

// Local time with its UTC offset, so the server can read the user's local hour for the
// mood trend (design §9.1); toISOString() would give UTC.
function localTimestamp(d = new Date()) {
  const off = -d.getTimezoneOffset();
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  const local = new Date(d.getTime() + off * 60000).toISOString().slice(0, 19);
  return `${local}${off >= 0 ? "+" : "-"}${pad(off / 60)}:${pad(off % 60)}`;
}

async function send(text, action) {
  const payload = JSON.stringify({
    message: text,
    client_ts: localTimestamp(),
    action: action || null,
  });
  return api("/chat", { method: "POST", headers: JSON_HEADERS, body: payload });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  // Enter submits even while Send is disabled; wait for the reply, keeping the text.
  if (!text || sendButton.disabled) return;
  input.value = "";
  if (!(await sendText(text))) input.value = text;
  // Leave focus on the help card when a crisis reply has just moved it there.
  if (!help.contains(document.activeElement)) input.focus();
});

continueButton.addEventListener("click", () => sendText(CONTINUE_TEXT));
document.getElementById("start-saved").addEventListener("click", () => start(false));
document.getElementById("start-ephemeral").addEventListener("click", () => start(true));

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

init();
