"use strict";

// Mood-trend view (design §9, FR-TRK-3). Uses the chat's session token from browser storage,
// sent only in the X-OASIS-Session header (rules P3, F5). All text goes in with textContent
// (rules F4); the charts are plain SVG built here, with no outside requests.

const SESSION_KEY = "oasis.session";
// The SVG namespace, read from an <svg> the HTML parser already made, so no URL-like
// string appears in the page's code (see the no-external-requests test).
const SVG = document.querySelector(".chart svg").namespaceURI;
const W = 600;
const H = 200;
const PAD = 24;
// VADER's own cut-offs for positive, neutral and negative text.
const NEUTRAL = 0.05;
const NAMES = {
  valence: "How positive or negative the words are",
  sadness: "Sad words",
  anxiety: "Worried words",
  anger: "Angry words",
  shame: "Shame words",
  loneliness: "Lonely words",
  fp_pronoun_rate: "How often you say “I” or “me”",
  absolutist_rate: "All-or-nothing words (always, never, nothing…)",
  msg_length: "Message length",
  reply_latency_s: "Time between replies",
  hour_of_day: "Time of day",
};

const status = document.getElementById("trend-status");

// A saved session's key is in localStorage, an unsaved one's in sessionStorage (rules F5).
function readToken() {
  try {
    return localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function svg(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function words(v) {
  if (v >= NEUTRAL) return "more positive words";
  if (v <= -NEUTRAL) return "more negative words";
  return "mostly neutral words";
}

// One chart on a -1..1 scale: a solid line with dots, an optional dashed line, rings on
// flagged points, and a zero line.
function chart(container, values, { dashed = [], flags = [], label }) {
  const x = (i, n) => (n === 1 ? W / 2 : PAD + (i * (W - 2 * PAD)) / (n - 1));
  const y = (v) => PAD + ((1 - v) / 2) * (H - 2 * PAD);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label });
  root.append(svg("line", { x1: PAD, x2: W - PAD, y1: y(0), y2: y(0), class: "axis" }));
  const top = svg("text", { x: PAD, y: 14, class: "axis-text" });
  top.textContent = "more positive";
  const bottom = svg("text", { x: PAD, y: H - 4, class: "axis-text" });
  bottom.textContent = "more negative";
  root.append(top, bottom);
  const line = (vals, cls) => {
    if (vals.length < 2) return;
    const pts = vals.map((v, i) => `${x(i, vals.length)},${y(v)}`).join(" ");
    root.append(svg("polyline", { points: pts, class: cls }));
  };
  line(dashed, "trend-line ewma");
  line(values, "trend-line");
  values.forEach((v, i) => {
    const cx = x(i, values.length);
    if (flags[i]) root.append(svg("circle", { cx, cy: y(v), r: 9, class: "flag" }));
    root.append(svg("circle", { cx, cy: y(v), r: 4, class: "dot" }));
  });
  container.replaceChildren(root);
}

function showNow(current) {
  const note = document.getElementById("now-note");
  const values = current.map((p) => p.valence);
  if (!values.length) {
    note.textContent = "Nothing yet. Once you send a message, it shows here.";
    return;
  }
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const label = `${values.length} messages in this conversation; on average ${words(mean)}.`;
  chart(document.getElementById("now-chart"), values, { label });
  note.textContent = label;
}

function showPast(body) {
  const note = document.getElementById("past-note");
  const means = body.sessions.map((s) => s.mean.valence);
  if (means.length < 2) {
    note.textContent =
      "This fills in when there are more conversations to compare. For now, each visit to " +
      "OASIS starts a new record, so there is only this one.";
    return;
  }
  const label = `${means.length} conversations. Dots: each conversation's average. Dashed: the overall direction.`;
  chart(document.getElementById("past-chart"), means, {
    dashed: body.ewma,
    flags: body.change_flags,
    label,
  });
  const flagged = body.change_flags.flatMap((f, i) => (f ? [i + 1] : []));
  note.textContent = flagged.length
    ? `${label} Ringed: conversation ${flagged.join(", ")} used noticeably different words ` +
      "from your earlier ones. This is about word choice only, not how you are."
    : label;
}

function showBasis(features) {
  const list = document.getElementById("basis");
  list.replaceChildren(
    ...features.map((f) => {
      const item = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = NAMES[f.name] || f.name;
      const detail = document.createElement("span");
      detail.textContent = f.exploratory
        ? "Exploratory: not backed by a checked study yet."
        : `Source: ${f.source}`;
      item.append(name, detail);
      if (f.note) {
        const note = document.createElement("span");
        note.textContent = f.note;
        item.append(note);
      }
      return item;
    }),
  );
}

async function load() {
  const token = readToken();
  if (!token) {
    status.textContent = "Start a conversation first, then come back here.";
    return;
  }
  try {
    const resp = await fetch("/trends", { headers: { "X-OASIS-Session": token } });
    if (resp.status === 401) {
      status.textContent = "Start a conversation first, then come back here.";
      return;
    }
    if (!resp.ok) throw new Error(String(resp.status));
    const body = await resp.json();
    status.textContent = "";
    showNow(body.current);
    showPast(body);
    showBasis(body.features);
  } catch {
    status.textContent = "The trend couldn't load just now. Your conversation is not affected.";
  }
}

load();
