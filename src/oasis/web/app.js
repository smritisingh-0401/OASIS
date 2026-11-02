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

function showCrisisSupport() {
  help.open = true;
  help.querySelector(".help-card").focus();
  continueButton.hidden = false;
}

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
  const others = helpCard.querySelector(".all-countries");
  others.open = false;
  others.querySelector("summary").textContent = "Not right? Choose another country";
  others.before(box);
}

help.addEventListener("toggle", () => {
  if (help.open) suggestCountry();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !help.open) return;
  help.open = false;
  help.querySelector("summary").focus();
});

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
  }
}

const JSON_HEADERS = { "Content-Type": "application/json" };
const OFFLINE = "I couldn't reach the server. \"Need help now?\" still works.";

const startSaved = document.getElementById("start-saved");
const startEphemeral = document.getElementById("start-ephemeral");
// Only the online demo's data notice has a "demo-" version (disclosure_demo.yaml).
const DEMO = document.querySelector('.notice[data-version^="demo-"]') !== null;
// Opens with the data notice, so it needs nothing stored in the browser (rules F5).
const demoPopup = document.getElementById("demo-popup");
let resuming = false;

function showOnboarding(note, resume = false) {
  resuming = resume;
  startSaved.textContent = resume ? "Accept and continue" : "Save on this computer";
  startEphemeral.hidden = resume;
  startSaved.hidden = DEMO && !resume;
  if (DEMO && !resume && !demoPopup.open) demoPopup.showModal();
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

async function loadSettings() {
  try {
    const resp = await api("/settings");
    if (resp.ok) chosenCountry = (await resp.json()).country || "";
  } catch {
  }
}

let styleSuggested = false;

function styleNote() {
  const note = line("p", "You can ask OASIS to word things more gently in ", "note");
  const link = document.createElement("a");
  link.href = "settings.html";
  link.textContent = "Settings";
  note.append(link, ".");
  return note;
}

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
  const stick = role === "user" || atBottom();
  messages.appendChild(item);
  follow(stick);
  if (typing) typeOut(item, body, text);
  return item;
}

function setBusy(busy) {
  sendButton.disabled = busy;
  for (const button of card.querySelectorAll("button")) button.disabled = busy;
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
    showCard(body);
    const last = body.turns[body.turns.length - 1];
    if (last && (last.mode === "crisis" || last.mode === "post_crisis")) continueButton.hidden = false;
  } catch {
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

function act(label, action) {
  return () => sendText(label, action);
}

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
  const controls = document.createElement("div");
  controls.className = "card-controls";
  controls.append(button("Stop exercise", act("Stop", { type: "exercise_stop" }), "link"));
  card.append(line("p", ex.name + " · Step " + ex.item + " of " + ex.item_count, "card-title"));
  if (ex.instruction) card.append(line("p", ex.instruction, "card-step"));
  card.append(line("p", "Reply in your own words when you're ready for the next step.", "card-hint"), controls);
  if (!help.contains(document.activeElement)) input.focus();
}

function renderCard(step) {
  card.replaceChildren();
  card.setAttribute("aria-label", "Questionnaire");
  card.hidden = !step || step.step === "result";
  if (card.hidden) {
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
      const body = await resp.json().catch(() => ({}));
      pending.remove();
      if (resp.status === 401) saveToken("");
      const consent = body.error && body.error.code === "consent_required";
      showOnboarding(consent
        ? "Please read and accept the data notice first. Your message wasn't sent."
        : "Please choose how to start again. Your message wasn't sent.", consent);
      return false;
    }
    if (!resp.ok) throw new Error("status " + resp.status);
    const body = await resp.json();
    const note = body.persisted || body.mode === "crisis" ? "" : "This message may not have been saved.";
    dots.remove();
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
  if (!text || sendButton.disabled) return;
  input.value = "";
  if (!(await sendText(text))) input.value = text;
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
