"use strict";

// Why replies (design §10, FR-XAI-3): every reply of this conversation, newest first, each a
// closed panel whose plain-language reasons are fetched when opened. Moved here from under each
// reply (demo testing, 2026-10-29). The session token goes only in the X-OASIS-Session header
// (rules P3, F5); all text goes in with textContent (rules F4).

const status = document.getElementById("why-status");
const list = document.getElementById("why-list");
const SNIPPET_CHARS = 140;

function line(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function snippet(text) {
  return text.length > SNIPPET_CHARS ? text.slice(0, SNIPPET_CHARS).trimEnd() + "…" : text;
}

// One reply: the start of its text as the summary; the reasons load when it is opened.
function whyPanel(reply, explanationId) {
  const panel = document.createElement("details");
  panel.className = "why";
  panel.appendChild(line("summary", snippet(reply)));
  if (!explanationId) {
    panel.appendChild(line("p", "Explanation unavailable for this reply.", "why-note"));
    return panel;
  }
  let note = null;
  panel.addEventListener("toggle", async () => {
    if (!panel.open || panel.dataset.loaded || panel.dataset.loading) return;
    panel.dataset.loading = "1";
    if (note) note.remove();
    let resp = null;
    try {
      resp = await api("/explanations/" + encodeURIComponent(explanationId));
    } catch {
      // No connection: said below and tried again on the next open.
    }
    delete panel.dataset.loading;
    // No answer, or the server could not load it right now: say which, and fetch again the
    // next time the panel is opened. Only a definite answer is kept.
    if (!resp || resp.status >= 500) {
      note = line("p", resp
        ? "OASIS couldn't load this right now. Close and reopen this to try again."
        : "Couldn't reach OASIS. Close and reopen this to try again.", "why-note");
      panel.appendChild(note);
      return;
    }
    panel.dataset.loaded = "1";
    const body = resp.ok ? await resp.json().catch(() => null) : null;
    if (!body || body.status === "unavailable") {
      panel.appendChild(line("p", "Explanation unavailable for this reply.", "why-note"));
      return;
    }
    const reasons = document.createElement("ul");
    for (const text of body.plain_language) reasons.appendChild(line("li", text));
    panel.append(reasons);
  });
  return panel;
}

async function load() {
  if (!readToken()) {
    status.textContent = "Start a conversation first, then come back here.";
    return;
  }
  try {
    const resp = await api("/history?limit=200");
    if (resp.status === 401) {
      status.textContent = "Start a conversation first, then come back here.";
      return;
    }
    if (!resp.ok) throw new Error(String(resp.status));
    const turns = (await resp.json()).turns;
    const items = turns.filter((t) => t.role === "assistant" || t.role === "placeholder").reverse();
    if (!items.length) {
      status.textContent = "No replies yet. Once OASIS replies, the reasons show here.";
      return;
    }
    status.textContent = "";
    list.replaceChildren(...items.map((t) => {
      const item = document.createElement("li");
      // A crisis reply is never saved, nor are its details (CR-06).
      item.appendChild(t.role === "placeholder"
        ? line("p", "This was crisis support. Its details are not kept.", "why-note")
        : whyPanel(t.content, t.explanation_id));
      return item;
    }));
  } catch {
    status.textContent = "The reasons couldn't load just now. Your conversation is not affected.";
  }
}

load();
