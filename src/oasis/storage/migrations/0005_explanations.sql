-- Phase 9: the explanation of each reply (design §10.2), stored with the reply it explains so
-- it is exported and deleted with it. JSON of numbers, codes and fixed phrases; never user text.

ALTER TABLE turns ADD COLUMN explanation TEXT CHECK (explanation IS NULL OR json_valid(explanation));
