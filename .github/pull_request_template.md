## 变更摘要

- 简述本次改动内容：

## 成本阶梯（新增 Syscall / MCP 时必填）

若本 PR 新增 `sys_*` 或 MCP seed，须满足其一（见 `docs/architecture/execution-decision-matrix.md` §2.5）：

- [ ] 不适用（未新增 Syscall / MCP）
- [ ] 完整证明模板（`why_not_1_extend`…`why_not_4_plugin` 各≥20字 + `rung` + `blast_radius`）
- [ ] 内联 `# ladder-ok: <reason≥15字>`（可选 `temporary until YYYY-MM-DD`）

```text
why_not_1_extend:
why_not_2_cli:
why_not_3_tool:
why_not_4_plugin:
rung: MCP | Syscall
blast_radius:
```

## 验证方式

- [ ] 已说明如何验证
- [ ] 已补充必要测试/日志/截图（如适用）

## Architecture Boundary Checklist

- 本次改动主要归属哪一层？
  - [ ] Management（aiPlat-management）
  - [ ] Layer 3 / app（aiPlat-app）
  - [ ] Layer 2 / platform（aiPlat-platform）
  - [ ] Layer 1 / core（aiPlat-core）
  - [ ] Layer 0 / infra（aiPlat-infra）

- [ ] 保持单向依赖：`app → platform → core → infra`
- [ ] 未引入禁止依赖或循环依赖
- [ ] 如涉及跨层契约变更（身份透传 / request_id / run_id / 错误透传），已同步更新规范文档
- [ ] 如涉及 `aiPlat-core`，已核对 Harness / Policy / Agent / Skill 边界

参考文档：
- `docs/architecture/system-architecture-contract.md`
- `docs/guides/PR_ARCHITECTURE_CHECKLIST.md`
- `aiPlat-core/docs/contracts/01-architecture-contract.md`
