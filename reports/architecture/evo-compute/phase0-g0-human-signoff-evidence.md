---
doc_type: Report
title: Phase 0 / G0 — 人工预算批准与安全边界签字
status: active
authority: supporting
language: zh-CN
created: 2026-11-25
---
# Phase 0 / G0 human signoff

> 触发：对话指令「批准」（2026-11-25）。  
> Actor：`zhu-ying`（朱莹）。  
> 机读回执：`phase0-g0-human-signoff-receipt.json`。

## 批准内容

| 项 | 结果 |
|---|---|
| 三试点登记 | pass — `routing.weights.v1` / `retrieval.params.v1` / `timeout.retry.v1` |
| 预算上限批准 | pass — `evo_budget_g0_v1`；approver=`zhu-ying` |
| 安全边界签字 | pass — `evo_safety_g0_v1`；signer=`zhu-ying` |
| 夹具离线回放 | pass — candidate `g0-signoff-replay-1` → `ranked`；`production_sample=false` |
| `evaluate_g0_exit_readiness` | `phase0_complete=true`；`certified=false`；`e2_claimed=false` |

## 预算硬上限（已批准）

```text
max_candidates=50
max_generations=10
max_llm_calls=200
max_tokens=500000
max_wall_time_sec=3600
max_cost_usd=25.0
```

## 安全边界（已签字）

```text
sandbox_no_production_write
policy_gate_required
tenant_isolation
human_gate_before_approved
canary_before_production
rollback_plan_required
audit_trail_required
```

排除：`prompt_full_text` / `policy_gate_rules` / `core_python_code` / `customer_contract_params`。

## 诚实锁

```text
phase0_complete=true   # 人工签批 + 试点 + 夹具回放齐备后的出口就绪
certified=false
e2_claimed=false
production_sample=false
production_write=false
```

**未宣称**：DE/ES 种群、生产流量真实回放认证、Canary 生产、E2、闭环已测 L4。

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:aiPlat-infra python3 - <<'PY'
from core.api import core_facade as f
from core.harness.evo_compute.genome_registry import clear_registry_for_tests
from core.harness.evo_compute.budget import clear_budget_for_tests
from core.harness.evo_compute.safety import clear_safety_for_tests
clear_registry_for_tests(); clear_budget_for_tests(); clear_safety_for_tests()
f.register_evo_pilot_genomes(persist=False)
f.approve_evo_budget(actor="zhu-ying", evidence_ref="chat:批准:2026-11-25", persist=False)
f.sign_evo_safety_boundary(actor="zhu-ying", evidence_ref="chat:批准:2026-11-25", persist=False)
r = f.replay_evo_candidate_offline(
    genome_id="routing.weights.v1",
    genes={"semantic_weight": 0.5, "cost_weight": 0.3, "latency_weight": 0.2},
    persist_evidence=False,
)
ready = f.evaluate_evo_g0_exit_readiness(replay_ok=bool(r.get("ok")))
assert ready["phase0_complete"] is True
assert ready["certified"] is False
print("ok", ready["checks"])
PY
```
