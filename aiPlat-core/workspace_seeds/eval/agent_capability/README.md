# Agent Capability Case Bank（内容权威）

题目是评测体系的一等资产：**在本目录编辑，不在 Python 里写题。**

- **pack_id**: `agent.capability` @ `0.1.0`
- **profiles**: `agent.smoke.v1` / `agent.regression.v1` / `agent.benchmark.v1`
- **status**: draft 种子；运行时经 `promote_agent_capability_bank` → workspace frozen（`claim_eligible=false`）
- **范围**: v1.1 可测子集（A1–A13；mock/session/fixture；claim 关闭）
- **模式实评**: 见 `mode_core_capabilities.v1.yaml` + Plan `eval-agent-impl-mode-exam.md`（M0；live 未开）

## 目录（编辑面）

| 路径 | 角色 |
|------|------|
| `cases/{capability}.json` | **内容权威** — 每能力一组 case（含 `test_purpose`） |
| `pack.meta.json` | Pack 元数据（无 cases） |
| `profile.agent.*.json` | Suite Profile 配额 / holdout |
| `pack.agent.capability.v0.1.0.json` | **派生** — 由 loader 组装，便于整体审阅；勿当作唯一编辑源 |
| `mode_core_capabilities.v1.yaml` | M0 模式×能力矩阵（选题/执行分栏权威） |
| `intersection/parity_sample.v1.json` | 交集候选 + parity/rank_gate 清单（默认 rank_eligible=false） |
| `fixtures/mock_tools/` | Mock tool 目录 / harness fixtures |
| `fixtures/session/` | Session 卷字段样例 |
| `fixtures/long_context/` | 长上下文 fixtures |
| `fixtures/{tool_*,multi_turn_memory}/` | A3–A5/A8 fixture cases |
| `fixtures/mode_exam/` | M1a–M1c 分栏 smoke（plan_execute/conversational/rag/react；A3–A5 unknown） |

扩题：在对应 `cases/*.json` 追加 case → `validate_agent_capability_bank` →（可选）`write_agent_capability_seeds` 刷新派生 pack → promote / freeze。  
工厂 mutation/template 仍可生成 draft 候选，人审后写入 `cases/` 或 workspace pack bump。

## 校验

```bash
PYTHONPATH=aiPlat-core:. python -c \
  "from core.apps.eval.service.capability_case_bank import validate_agent_capability_bank as v; print(v()['ok'], v()['case_count'], v()['content_authority'])"
PYTHONPATH=aiPlat-core:. python -c \
  "from core.apps.eval.service.capability_p4_gate import benchmark_readiness_report as b; r=b(); print(r['ready_for_benchmark_quotas'], r['claim_eligible'])"
```

Loader：`core.apps.eval.service.capability_case_bank.load_agent_capability_cases`。  
冻结后 `claim_eligible` / `accuracy_claim` / `certification_eligible` 仍恒为 false。
