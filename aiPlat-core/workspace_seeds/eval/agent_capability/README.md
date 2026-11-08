# Agent Capability Case Bank（P1→P4）

- **pack_id**: `agent.capability` @ `0.1.0`
- **profiles**: `agent.smoke.v1` / `agent.regression.v1` / `agent.benchmark.v1`
- **status**: 种子仍为 draft JSON；运行时经 `promote_agent_capability_bank` 晋升为 workspace frozen（`claim_eligible=false`）
- **范围**: v1 可测子集（A1/A2/A6/A7/A10–A13）；不含 A3–A5/A8/A9
- **规模**: 64 题 = 8 能力 × 8（Benchmark 配额地板）

## 文件

| 文件 | 说明 |
|------|------|
| `pack.agent.capability.v0.1.0.json` | 64 题 curated cases（含 `test_purpose`） |
| `profile.agent.regression.v1.json` | Regression Suite Profile 配额 |

权威生成/校验：`core.apps.eval.service.capability_case_bank`。  
Profile 编译：`core.apps.eval.service.suite_profile_compile.compile_plan_from_suite_profile`。

```bash
PYTHONPATH=aiPlat-core:. python -c \
  "from core.apps.eval.service.capability_case_bank import validate_agent_capability_bank as v; print(v()['ok'], v()['case_count'])"
PYTHONPATH=aiPlat-core:. python -c \
  "from core.apps.eval.service.capability_p4_gate import benchmark_readiness_report as b; r=b(); print(r['ready_for_benchmark_quotas'], r['claim_eligible'])"
```

## 人审 / 晋升

1. 机械校验 `validate_agent_capability_bank`
2. `promote_agent_capability_bank(workspace_id=…)`：draft → enqueue → approve → freeze
3. `compile_plan_from_suite_profile(profile_id=…)`：固定配额 → Plan v2 `sample_manifest`（唯一执行列表）

冻结后 `claim_eligible` / `accuracy_claim` / `certification_eligible` 仍恒为 false（真正 Certification 需外部审计立项）。
