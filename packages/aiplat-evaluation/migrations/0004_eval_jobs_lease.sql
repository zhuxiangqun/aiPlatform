-- B2-L: lease holder for SKIP LOCKED claim / heartbeat
ALTER TABLE eval_jobs ADD COLUMN leased_by TEXT NOT NULL DEFAULT '';
