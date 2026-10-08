-- Phase 3: PHQ-9 / GAD-7 administrations and answers (design §11). Answers are 0-3 and
-- totals stay within each instrument's range at the database level, not only in code.

CREATE TABLE assessments (
  assessment_id TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  instrument  TEXT NOT NULL CHECK (instrument IN ('PHQ9', 'GAD7')),
  status      TEXT NOT NULL CHECK (status IN ('offered', 'declined', 'in_progress', 'paused', 'aborted', 'escalated', 'scored')),
  offer_reason TEXT NOT NULL,         -- JSON reason code and score; never message text
  total       INTEGER CHECK (total IS NULL OR total BETWEEN 0 AND 27),
  band        TEXT,
  functional  INTEGER CHECK (functional IS NULL OR functional BETWEEN 0 AND 3),
  created_at  TEXT NOT NULL,
  completed_at TEXT,
  CHECK (status <> 'scored' OR (total IS NOT NULL AND band IS NOT NULL)),
  CHECK (instrument <> 'GAD7' OR total IS NULL OR total <= 21)
) STRICT;

CREATE INDEX assessments_user ON assessments(user_id);

CREATE TABLE assessment_answers (
  assessment_id TEXT NOT NULL REFERENCES assessments(assessment_id) ON DELETE CASCADE,
  user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  item_index  INTEGER NOT NULL CHECK (item_index BETWEEN 1 AND 9),
  value       INTEGER NOT NULL CHECK (value BETWEEN 0 AND 3),
  answered_at TEXT NOT NULL,
  PRIMARY KEY (assessment_id, item_index)
) STRICT;
