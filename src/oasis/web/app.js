"use strict";

// The session token is kept in sessionStorage and sent only in the X-OASIS-Session
// header, never in a URL (rules P3, F5). All text is rendered with textContent (rules F4).

const SESSION_KEY = "oasis.session";
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

function readToken() {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function saveToken(token) {
  try {
    sessionStorage.setItem(SESSION_KEY, token);
  } catch {
    // Storage blocked: the session lasts for this page only.
  }
}

async function api(path, options = {}) {
  const headers = { "X-OASIS-Session": readToken() || "", ...(options.headers || {}) };
  return fetch(path, { ...options, headers });
}

const JSON_HEADERS = { "Content-Type": "application/json" };
const OFFLINE = "I couldn't reach the server. \"Need help now?\" still works.";

// The data notice replaces the conversation until a session has accepted it (FR-PRV-1).
function showOnboarding(note) {
  onboarding.hidden = false;
  messages.hidden = true;
  form.hidden = true;
  card.hidden = true;
  status.textContent = note || "";
  if (!help.contains(document.activeElement)) onboarding.querySelector("button").focus();
}

function showChat() {
  onboarding.hidden = true;
  messages.hidden = false;
  form.hidden = false;
}

// Choosing how to start creates the session and records consent to the notice shown.
async function start(ephemeral) {
  const version = onboarding.querySelector(".notice").dataset.version;
  try {
    const resp = await fetch("/session", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ ephemeral }),
    });
    if (!resp.ok) throw new Error("session");
    const token = (await resp.json()).session_id;
    const consent = await fetch("/consent", {
      method: "POST",
      headers: { ...JSON_HEADERS, "X-OASIS-Session": token },
      body: JSON.stringify({ disclosure_version: version }),
    });
    if (!consent.ok) throw new Error("consent");
    saveToken(token);
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
    if (resp.ok && !(await resp.json()).consented) return showOnboarding();
    showChat();
    await loadHistory();
  } catch {
    showOnboarding(OFFLINE);
  }
}

function addMessage(role, text, note, explanationId) {
  const item = document.createElement("li");
  item.className = "msg " + ({ user: "user", placeholder: "system" }[role] || "bot");
  const body = document.createElement("p");
  body.textContent = text;
  item.appendChild(body);
  if (note) {
    const small = document.createElement("p");
    small.className = "note";
    small.textContent = note;
    item.appendChild(small);
  }
  if (explanationId) item.appendChild(whyPanel(explanationId));
  messages.appendChild(item);
  item.scrollIntoView({ block: "end" });
  return item;
}

// "Why this reply?" (design §10, FR-XAI-3): fetched the first time it is opened. The
// plain-language bullets come first; "See details" shows the raw record (the debug view).
function whyPanel(explanationId) {
  const panel = document.createElement("details");
  panel.className = "why";
  const summary = document.createElement("summary");
  summary.textContent = "Why this reply?";
  panel.appendChild(summary);
  panel.addEventListener("toggle", async () => {
    if (!panel.open || panel.dataset.loaded) return;
    panel.dataset.loaded = "1";
    let body = null;
    try {
      const resp = await api("/explanations/" + encodeURIComponent(explanationId));
      if (resp.ok) body = await resp.json();
    } catch {
      // Shown as unavailable below; the reply itself is unaffected.
    }
    if (!body || body.status === "unavailable") {
      panel.appendChild(line("p", "Explanation unavailable for this reply.", "why-note"));
      return;
    }
    const list = document.createElement("ul");
    for (const text of body.plain_language) list.appendChild(line("li", text));
    const details = document.createElement("details");
    details.className = "why-details";
    details.append(line("summary", "See details"), line("pre", JSON.stringify(body, null, 2)));
    panel.append(list, line("p", body.scope_note, "why-note"), details);
  });
  return panel;
}

function setBusy(busy) {
  sendButton.disabled = busy;
  for (const button of card.querySelectorAll("button")) button.disabled = busy;
  messages.setAttribute("aria-busy", busy ? "true" : "false");
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
    for (const turn of body.turns) addMessage(turn.role, turn.content, "", turn.explanation_id);
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
      const code = body.error && body.error.code;
      showOnboarding(code === "consent_required"
        ? "Please read and accept the data notice first. Your message wasn't sent."
        : "Please choose how to start again. Your message wasn't sent.");
      return false;
    }
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    // A crisis turn is never stored by design, so the not-saved note would only alarm.
    const note = body.persisted || body.mode === "crisis" ? "" : "This message may not have been saved.";
    if (body.preface) addMessage("assistant", body.preface);
    addMessage("assistant", body.reply, note, body.explanation_id);
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
  if (!text) return;
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
