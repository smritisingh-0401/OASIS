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
  item.className = "msg " + (role === "user" ? "user" : "bot");
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
  } catch {
    // History is a convenience; the chat still works without it.
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

  const pending = addMessage("user", text);
  input.value = "";
  setBusy(true);
  status.textContent = "OASIS is thinking…";
  const slow = setTimeout(() => {
    status.textContent = "Still working — this can take a few seconds on this computer.";
  }, SLOW_NOTICE_MS);

  try {
    const resp = await send(text);
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    const note = body.persisted ? "" : "This message may not have been saved.";
    addMessage("assistant", body.reply, note);
    status.textContent = "";
  } catch {
    // The message was not sent: take it out of the conversation and give it back.
    pending.remove();
    status.textContent =
      "I couldn't reach the server. Your message wasn't sent. \"Need help now?\" still works.";
    input.value = text;
  } finally {
    clearTimeout(slow);
    setBusy(false);
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

loadHistory();
