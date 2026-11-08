# Agent Capability Case Bank（P1 draft）

- **pack_id**: `agent.capability` @ `0.1.0`
- **profile_id**: `agent.regression.v1`
- **status**: `draft`（**未 freeze**；`claim_eligible=false`）
- **范围**: v1 可测子集（A1/A2/A6/A7/A10–A13）；不含 A3–A5/A8/A9

## 文件

| 文件 | 说明 |
|------|------|
| `pack.agent.capability.v0.1.0.json` | 32 题 curated cases（含 `test_purpose`） |
| `profile.agent.regression.v1.json` | Suite Profile 配额（fixed） |

权威生成/校验：`core.apps.eval.service.capability_case_bank`。

```bash
PYTHONPATH=aiPlat-core:. python -c \
  "from core.apps.eval.service.capability_case_bank import validate_agent_capability_bank as v; print(v()['ok'], v()['case_count'])"
```

## 人审

冻结前须对每题 `purpose_ok`；`purpose_mismatch` / `not_testable` / `prompt_leak` 不得 freeze。
