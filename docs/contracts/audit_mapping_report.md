# audit_schema.v1 ↔ ActionStore 映射报告

| 字段 | 值 |
|------|-----|
| 生成 | Phase 1 dry-run (`scripts/fde_audit_mapping.py`) |
| present | 8 |
| embedded | 13 |
| missing | 0 |

## 分类明细

| schema 字段 | 状态 | 落点 / 备注 |
|-------------|------|-------------|
| `action_name` | **present** | action_id |
| `action_namespace` | **embedded** | params.action_namespace (可选加列 `action_namespace`) |
| `actor_id` | **present** | actor |
| `actor_type` | **embedded** | role|params.actor_type |
| `after_state_snapshot` | **embedded** | entity_snapshot.after |
| `approver_id` | **embedded** | params.approver_id (可选加列 `approver_id`) |
| `audit_id` | **present** | audit_id |
| `before_state_snapshot` | **embedded** | entity_snapshot.before |
| `domain_id` | **present** | domain_id |
| `evidence_ref` | **embedded** | params.evidence_ref |
| `input_params_hash` | **embedded** | params.params_hash (可选加列 `input_params_hash`) |
| `input_params_snapshot` | **embedded** | params.redacted |
| `pipeline_run_id` | **embedded** | params.pipeline_run_id (可选加列 `pipeline_run_id`) |
| `policy_gate_decision` | **embedded** | params.policy_gate_decision |
| `result_message` | **present** | effect_summary |
| `result_status` | **present** | result_status |
| `retention` | **embedded** | params.retention |
| `rollback_ref` | **embedded** | compensation |
| `target_entity_id` | **present** | entity_id |
| `target_entity_type` | **embedded** | params.target_entity_type (可选加列 `target_entity_type`) |
| `timestamp` | **present** | created_at |

## Phase 2 可选 ADD COLUMN（全部 NULL）

```sql
ALTER TABLE action_audit ADD COLUMN approver_id TEXT NULL;
ALTER TABLE action_audit ADD COLUMN action_namespace TEXT NULL;
ALTER TABLE action_audit ADD COLUMN target_entity_type TEXT NULL;
ALTER TABLE action_audit ADD COLUMN input_params_hash TEXT NULL;
ALTER TABLE action_audit ADD COLUMN pipeline_run_id TEXT NULL;
```

## 回滚 SQL

```sql
ALTER TABLE action_audit DROP COLUMN approver_id;
ALTER TABLE action_audit DROP COLUMN action_namespace;
ALTER TABLE action_audit DROP COLUMN target_entity_type;
ALTER TABLE action_audit DROP COLUMN input_params_hash;
ALTER TABLE action_audit DROP COLUMN pipeline_run_id;
```

## 策略

- Phase 1：**优先 JSON 嵌入**（`params` / `entity_snapshot`），不改生产表。
- Phase 2：按需加列后可从 embedded 迁到 present；完整率硬门见方案。
