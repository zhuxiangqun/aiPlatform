-- A6: tenant_id on sets/reports for standalone isolation (eval.store.v0 + tenant)
ALTER TABLE eval_sets ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
ALTER TABLE eval_reports ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_eval_sets_tenant ON eval_sets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_eval_reports_tenant ON eval_reports(tenant_id);
