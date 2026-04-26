# 多 Agent 协作编排：文章框架 → 我们系统能力对照（1 页版）

基于文章《多 Agent 协作编排：怎么做才靠谱？》的“两维度四象限”框架，结合我们当前已实现的能力（runs/approvals/skill&tool 分层审批/tenant policy/RBAC/证据链），输出一个可落地的对照表与下一阶段演进建议。

---

## 1) 文章框架快速复述

**维度 A：编排控制权**
- 预定义 SOP：流程确定、可审计、易调试；覆盖边界差、迭代成本高
- Agent 自主规划：灵活、适配开放任务；不确定性高、难审计、token 成本高

**维度 B：是否人工复核**
- 有人工复核：关键节点审批/拒绝/回退/编辑继续
- 无人工复核：全自动，速度快但错误可能放大

由此形成四象限：
- **A 象限：SOP + 人工复核**
- **B 象限：SOP + 无复核**
- **C 象限：自主规划 + 人工复核**
- **D 象限：自主规划 + 无复核**

---

## 2) 我们系统在四象限中的定位（当前态）

> 结论：我们已经具备支撑 **A / B / C** 三类模式的“平台底座”，并且能通过配置把不同业务落到不同象限；**D（完全自治无复核）**目前被主动限制（默认不启用 auto_resume / 需要策略放开）。

### A：预定义 SOP + 人工复核（企业级主阵地）
- **可做**：强一致的“等待审批 → 通过 → 自动恢复/重放 → 完成”，具备 run 级可追溯事件与证据链
- **落地方式**：SOP（流程引擎/编排器）在关键节点输出 run_id，统一用 `/runs/{run_id}/wait` 管理暂停/恢复

### B：预定义 SOP + 无复核（可控自动化流水线）
- **可做**：通过 tenant policy 把某些操作 `approval_required=false` 或 allowlist 放开；仍保留审计与可回放
- **风险控制**：保留“异常复核/策略回滚”的能力作为兜底（见第 4 部分）

### C：自主规划 + 人工复核（探索型/研究型工作）
- **可做**：Planner/Leader 输出阶段性中间产物，以“审批点/检查点”的形式落 run 事件；必要时动态插入审批
- **关键**：审批不是 UI 按钮，而是 run 状态机 + replay 机制

### D：自主规划 + 无复核（沙箱/低风险）
- **谨慎**：平台机制支持，但默认策略上应“关”，只在沙箱租户/白名单操作放开

---

## 3) 能力对照表（文章能力点 → 我们实现情况）

| 能力项（文章隐含需求） | 我们现状 | 说明/证据（对应机制） |
|---|---|---|
| 统一的运行态（run） | ✅ 已有 | run_summary + run_events；`/runs/{run_id}`、`/runs/{run_id}/events` |
| waiting_approval 可观测 | ✅ 已有 | run status = waiting_approval；`approval_request_id` 可从 wait 返回 |
| 审批闭环（approve → replay/resume） | ✅ 已有 | approvals hub + `/runs/{run_id}/wait(auto_resume)` 自动恢复 |
| 可重放且 run_id 稳定 | ✅ 已有 | replay 复用同一 run_id（skill/tool 都已跑通） |
| 分层审批（skill vs tool） | ✅ 已有 | `approval_layer_policy`（skill_only/tool_only/both/sensitive_only） |
| 分层审批可配置 | ✅ 已有 | env + tenant policy（`policy.approval_layering`） |
| 自动恢复（auto_resume）可控 | ✅ 已有 | env + tenant policy（`policy.run_wait_auto_resume`） |
| auto_resume 的权限控制 | ✅ 已有 | RBAC：`resume/run` 仅 operator/admin（enforced 下 403） |
| 证据链/审计 | ✅ 已有（基础） | run_events / syscall_events / audit_log（用于追溯与合规） |
| “最终生效配置”可观测 | ✅ 已有 | `/policies/tenants/{tenant_id}/effective` |
| 动态插入复核节点 | ⚠️ 部分具备 | 机制上可通过“在 wait 阶段触发审批”实现；但还没形成编排器侧的通用接口 |
| 拒绝回退到历史节点并恢复上下文 | ⚠️ 部分具备 | 有 replay，但“节点级快照/回退到某 step”需要编排器/状态机层进一步建设 |
| 抽样/异常复核策略 | ⏳ 待做 | 需要策略引擎支持按风险/置信度/比例触发审批 |
| 并行分支的复核与汇合 | ⏳ 待做 | 需要 run 关联多个 child runs + join 规则 |

---

## 4) 下一阶段演进建议（按投入/收益排序）

### P6-1：把“审批点/检查点”抽象成一等公民（SOP/Planner 通用）
- 目标：让编排器不需要理解 approvals 细节，只需要“在某节点输出 checkpoint”  
- 形态建议：  
  - `run_event: checkpoint_requested`（包含 node_id、artifact_ref、risk、suggested_reviewers）  
  - 对应 `/runs/{run_id}/wait` 返回 checkpoint（类似现在 approval_requested）

### P6-2：把“拒绝→回退→重做”产品化
- 目标：不仅能 replay “同一次请求”，还能回退到某个 node/step，并带着当时上下文重跑  
- 关键能力：事件溯源 + 节点快照（或可重建的 deterministic inputs）

### P6-3：异常/抽样复核策略（降低人工瓶颈）
- 目标：从“全量人工复核”进化到“信任阶梯”  
- 策略输入：风险等级、工具类型、变更规模、模型置信度、历史通过率等
- 输出：是否审批 + 审批类型（抽样/异常/全量/事后）

### P6-4：并行/汇合语义（多 Agent 真正编排）
- 子 run（子任务）并行执行，父 run 在 join 点做统一复核或分支复核

---

## 5) 建议的“落地模板”（给产品/解决方案）

### 企业默认模板（高风险）
- 象限：A（SOP + 全量复核）
- 配置：
  - `approval_layering.policy=skill_only`（避免双审）
  - `run_wait_auto_resume.enabled=true` + allowlist 精确到 `skill:*` / 特定 tool
  - RBAC enforced

### 内部运营模板（中风险）
- 象限：A → B 渐进
- 配置：
  - 初期全量复核；稳定后启用抽样/异常复核（P6-3）

### 研究探索模板（开放任务）
- 象限：C（自主规划 + 关键节点复核）
- 配置：
  - checkpoint 机制（P6-1）
  - 关键节点必须审批（例如对外输出、写入、发布）

---

## 6) 你要我补哪一块“下一步文档”
如果你希望继续深化，我建议二选一：
1) **做一份“能力缺口 → API/数据模型/事件类型”的技术方案**（偏研发落地）  
2) **做一份“象限 A/B/C 的产品化配置模板 + 交付打法”**（偏解决方案/售前）

