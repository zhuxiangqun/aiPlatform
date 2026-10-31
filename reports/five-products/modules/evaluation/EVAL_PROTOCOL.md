# Eval Protocol v0（草案）

> Capability: **evaluation** · Central deploy · A1 契约冻结起步  
> Schema: `contracts/schemas/eval_protocol.schema.json`

## 目标

统一「评什么 / 跑什么 / 记什么 / 判什么」的最小交换格式，供：

- `apps/eval` 现有 runs / skill / gold 路径逐步收敛  
- Pi / FDE 导出的 Evidence 引用（`evidence_refs`）  
- 后续独立 Evaluation Service（需 ADR 才 A3）

## v0 字段

| 字段 | 含义 |
|------|------|
| `schema_version` | 固定 `eval.protocol.v0` |
| `task` | `id` + `target_kind`（agent/skill/workflow/bundle/http/cli）+ `target_ref` |
| `status` | pending → running → passed/failed/skipped/error |
| `trajectory_ref` | 轨迹存储键（可选） |
| `metrics` | 扁平指标字典 |
| `report` | summary / score / gate |
| `evidence_refs` | 外部证据 ID（含 FDE / slice） |

## 首版边界

- **只承诺** aiPlat 产物（Agent/Skill/Workflow/Bundle）  
- **不承诺**「所有程序」；http/cli 枚举预留  
- 不替代 FDE 验收真源；评测报告 ≠ 客户签收  

## 收敛路径

1. ✅ 适配器 `to_eval_protocol_v0` / `from_run_evaluation` / `from_skill_eval_run` / generic  
2. ✅ 已接线：run evaluate / auto / latest · skill-eval run+GET · gold · kb · prompt · arena  
3. A2 build/version；A3 进程/DB 另 ADR  

## 验证

```bash
python3 reports/five-products/modules/evaluation/contracts/validate_sample.py
python3 -m pytest aiPlat-core/core/tests/unit/test_eval_protocol_v0.py -q
```
