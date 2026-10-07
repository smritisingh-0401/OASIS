-- Phase 2: audit log (design §11). Crisis entries hold tiers and pattern IDs, never
-- message text (design §2.4).

CREATE TABLE audit_log (
  audit_id    TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  event       TEXT NOT NULL CHECK (event IN ('crisis_handoff', 'consent_given', 'consent_withdrawn', 'export', 'settings_changed')),
  detail      TEXT NOT NULL,
  created_at  TEXT NOT NULL
) STRICT;

CREATE INDEX audit_user ON audit_log(user_id);
