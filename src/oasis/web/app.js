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

async function sendText(text) {
  const pending = addMessage("user", text);
  setBusy(true);
  status.textContent = "OASIS is thinking…";
  const slow = setTimeout(() => {
    status.textContent = "Still working — this can take a few seconds on this computer.";
  }, SLOW_NOTICE_MS);

  try {
    const resp = await send(text);
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    // A crisis turn is never stored by design, so the not-saved note would only alarm.
    const note = body.persisted || body.mode === "crisis" ? "" : "This message may not have been saved.";
    addMessage("assistant", body.reply, note);
    status.textContent = "";
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

async function send(text) {
  const payload = JSON.stringify({ message: text, client_ts: new Date().toISOString() });
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
