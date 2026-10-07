-- Phase 1: pseudonymous users, sessions and turns (design §11).
-- Later phases add signals, assessments, explanations, audit_log, consent and settings.

CREATE TABLE users (
  user_id     TEXT PRIMARY KEY,
  created_at  TEXT NOT NULL
) STRICT;

CREATE TABLE sessions (
  session_id_hash TEXT PRIMARY KEY,   -- SHA-256 of the bearer session token; the token is never stored
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  post_crisis INTEGER NOT NULL DEFAULT 0 CHECK (post_crisis IN (0, 1)),
  router_state TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE turns (
  turn_id     TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  session_id_hash TEXT NOT NULL REFERENCES sessions(session_id_hash) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'placeholder')),
  content     TEXT NOT NULL,
  mode        TEXT,
  created_at  TEXT NOT NULL,
  trace       TEXT,                   -- JSON TurnTrace; never contains user text
  UNIQUE (session_id_hash, seq)
) STRICT;

CREATE INDEX turns_user ON turns(user_id);
