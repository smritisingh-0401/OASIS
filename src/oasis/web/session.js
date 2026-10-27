"use strict";

// Shared by every page, loaded before the page's own script. The session token is the only
// thing kept in the browser: a saved session's key in localStorage, an unsaved one's in
// sessionStorage (rules F5). It is sent only in the X-OASIS-Session header, never in a URL
// (rules P3).

const SESSION_KEY = "oasis.session";

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
