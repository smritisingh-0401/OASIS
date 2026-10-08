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

async function newSession() {
  const resp = await fetch("/session", { method: "POST" });
  if (!resp.ok) throw new Error("session");
  const body = await resp.json();
  saveToken(body.session_id);
  return body.session_id;
}

async function api(path, options = {}) {
  const token = readToken() || (await newSession());
  const headers = { "X-OASIS-Session": token, ...(options.headers || {}) };
  return fetch(path, { ...options, headers });
}

function addMessage(role, text, note) {
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
  messages.appendChild(item);
  item.scrollIntoView({ block: "end" });
  return item;
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
    for (const turn of body.turns) addMessage(turn.role, turn.content);
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

function renderCard(step) {
  card.replaceChildren();
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
    if (step.stem) card.append(line("p", step.stem, "card-stem"));
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
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    // A crisis turn is never stored by design, so the not-saved note would only alarm.
    const note = body.persisted || body.mode === "crisis" ? "" : "This message may not have been saved.";
    addMessage("assistant", body.reply, note);
    status.textContent = "";
    renderCard(body.assessment);
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

async function send(text, action) {
  const payload = JSON.stringify({
    message: text,
    client_ts: new Date().toISOString(),
    action: action || null,
  });
  const request = () =>
    api("/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
  let resp = await request();
  if (resp.status === 401) {
    await newSession();
    resp = await request();
  }
  return resp;
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

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

loadHistory();
