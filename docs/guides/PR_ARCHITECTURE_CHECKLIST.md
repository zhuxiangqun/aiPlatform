# PR 架构规范检查清单（Architecture Boundary Checklist）

> 目标：让系统整体架构规范在 PR 评审阶段“硬生效”。  
> 适用范围：aiPlatform 全系统（management / app / platform / core / infra）。

---

## 1. 变更归属（必填）

- 本次改动主要归属哪一层？
  - [ ] Management（aiPlat-management）
  - [ ] Layer 3 / app（aiPlat-app）
  - [ ] Layer 2 / platform（aiPlat-platform）
  - [ ] Layer 1 / core（aiPlat-core）
  - [ ] Layer 0 / infra（aiPlat-infra）

## 2. 依赖方向检查（MUST）

- [ ] 是否新增了跨层 import / 直接调用？（如 app→core、platform→infra 等）
- [ ] 是否保持单向依赖：`app → platform → core → infra`？
- [ ] 是否避免循环依赖？

> 参考：系统整体架构规范（跨层契约）  
> - `docs/architecture/system-architecture-contract.md`

## 3. 跨层契约是否变化（MUST）

若本次改动涉及以下任意项，请在 PR 中说明并更新对应规范文档：

### 3.1 身份/权限/租户透传
- [ ] 是否新增/修改 `X-AIPLAT-*` headers？
- [ ] 是否改变了鉴权/权限校验位置或语义？

参考：`规范-platform-鉴权与身份透传.md`

### 3.2 request_id / run_id / trace_id
- [ ] 是否新增/修改 request_id 的生成/透传逻辑？
- [ ] 是否改变 run_id/trace_id 的生成/返回字段语义？

参考：`规范-core-run_id-trace_id-request_id.md`

### 3.3 错误透传
- [ ] platform 是否仍能透传下游 detail？是否出现吞错只返回 500？

参考：`docs/architecture/system-architecture-contract.md`（错误透传与网关行为）

## 4. core 层边界检查（仅当涉及 core 时必填）

若本次改动涉及 `aiPlat-core`：

- [ ] 是否把业务语义决策下沉到 `core/harness/*`？（禁止）
- [ ] 新增的是执行能力（Skill）还是决策/规划（Internal Policy）？
  - Internal Policy：问题分析/检索路由/回答策略
  - Skill：单一职责、明确 I/O 的可执行能力
- [ ] Agent 是否仍然主要承担会话编排，而不是底层检索实现？

参考：`aiPlat-core/docs/contracts/01-architecture-contract.md`（Layer Boundary Contract）

## 5. 文档与测试（建议）

- [ ] 是否需要更新系统级规范或各层 docs 索引？
- [ ] 是否补充/更新单元测试或集成测试？
- [ ] 是否包含最小验证步骤（如何复现/如何验证修复）？

