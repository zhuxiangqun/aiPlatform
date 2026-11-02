-- B2-L: runner collect output on jobs
ALTER TABLE eval_jobs ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}';
