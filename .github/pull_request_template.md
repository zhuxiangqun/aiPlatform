## 变更摘要

- 简述本次改动内容：

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
