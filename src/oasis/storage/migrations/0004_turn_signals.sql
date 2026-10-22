-- Phase 8: language features of each user message (design §9.1). Numbers only, as JSON
-- with one key per TurnFeatures field; never message text. Deleted with the user.

CREATE TABLE turn_signals (
  signal_id   INTEGER PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  session_id_hash TEXT NOT NULL REFERENCES sessions(session_id_hash) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  features    TEXT NOT NULL CHECK (json_valid(features))
) STRICT;

CREATE INDEX turn_signals_user ON turn_signals(user_id, created_at);
