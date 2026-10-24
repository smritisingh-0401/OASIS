-- Phase 10: consent to the data notice (design §11, FR-PRV-1). One row per user, replaced
-- when they accept a newer version. Deleted with the user.

CREATE TABLE consent (
  user_id     TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  disclosure_version TEXT NOT NULL,
  given_at    TEXT NOT NULL
) STRICT;
