"use strict";

// Settings (design §15.1, FR-PRV-2, FR-PRV-3): whether this conversation is saved, export and
// delete. Uses the chat's session token from browser storage, sent only in the X-OASIS-Session
// header (rules P3, F5). All text goes in with textContent (rules F4).

const SESSION_KEY = "oasis.session";
const CONFIRM = "DELETE";

const mode = document.getElementById("mode");
const status = document.getElementById("settings-status");
const exportButton = document.getElementById("export");
const deleteStart = document.getElementById("delete-start");
const confirmForm = document.getElementById("delete-confirm");
const confirmWord = document.getElementById("delete-word");

// A saved session's key is in localStorage, an unsaved one's in sessionStorage (rules F5).
function readToken() {
  try {
    return localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function api(path, options = {}) {
  const headers = { "X-OASIS-Session": readToken() || "", ...(options.headers || {}) };
  return fetch(path, { ...options, headers });
}

async function load() {
  try {
    const resp = await api("/session");
    if (resp.status === 401) {
      mode.textContent = "There is no conversation yet, so nothing is kept about you.";
      return;
    }
    if (!resp.ok) throw new Error("status " + resp.status);
    const info = await resp.json();
    mode.textContent = info.ephemeral
      ? "This conversation is not being saved. It is kept in memory only: closing this tab ends " +
        "your access, and it is gone after two hours without a message, when you delete it, " +
        "or when OASIS restarts."
      : "This conversation is saved in a file on this computer until you delete it. This " +
        "browser remembers it, so anyone who uses this browser on this computer can open it.";
    exportButton.disabled = false;
    deleteStart.disabled = false;
  } catch {
    mode.textContent = "I couldn't reach the server, so these settings are unavailable right now.";
  }
}

// The file is built in the page and saved with a temporary link; nothing leaves the computer.
exportButton.addEventListener("click", async () => {
  status.textContent = "";
  try {
    const resp = await api("/export");
    if (!resp.ok) throw new Error("status " + resp.status);
    const url = URL.createObjectURL(await resp.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "oasis-export.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    status.textContent = "Your data was saved as oasis-export.json.";
  } catch {
    status.textContent = "The export did not work. Please try again.";
  }
});

// Two steps: open the confirmation, then type the word (design §15.1).
deleteStart.addEventListener("click", () => {
  confirmForm.hidden = false;
  deleteStart.hidden = true;
  confirmWord.focus();
});

document.getElementById("delete-cancel").addEventListener("click", () => {
  confirmForm.hidden = true;
  deleteStart.hidden = false;
  confirmWord.value = "";
  deleteStart.focus();
});

confirmForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (confirmWord.value.trim() !== CONFIRM) {
    status.textContent = "Type DELETE in capital letters to confirm.";
    confirmWord.focus();
    return;
  }
  try {
    const resp = await api("/account", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: CONFIRM }),
    });
    const body = resp.status === 204 ? {} : await resp.json().catch(() => ({}));
    const code = body.error && body.error.code;
    if (resp.status !== 204 && code !== "erasure_pending") throw new Error("status " + resp.status);
    try {
      localStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Nothing to remove.
    }
    confirmForm.hidden = true;
    exportButton.disabled = true;
    // erasure_pending: deleted, but another program holds the file, so the overwrite waits.
    mode.textContent = code === "erasure_pending"
      ? body.error.message
      : "Everything OASIS kept about you has been deleted.";
    status.textContent = "You can start a new conversation from the chat page.";
  } catch {
    status.textContent = "Nothing was deleted. Please try again in a moment.";
  }
});

load();
