-- Phase 11: what the user chose in Settings (design §11, FR-CUL-1): the communication style
-- and the help card's country. One row per user, written only from the settings page; no
-- row means the defaults. Deleted with the user.

CREATE TABLE settings (
  user_id     TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  directness  TEXT NOT NULL DEFAULT 'balanced' CHECK (directness IN ('direct','balanced','indirect')),
  formality   TEXT NOT NULL DEFAULT 'neutral'  CHECK (formality IN ('casual','neutral','formal')),
  country     TEXT,                            -- optional ISO code, checked against resources.yaml
  updated_at  TEXT NOT NULL
) STRICT;
