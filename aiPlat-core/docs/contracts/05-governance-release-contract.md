# Governance & Release Contract（治理/发布契约）

本文件约束系统的“可控变更、可回滚、可审计”。

## 1. Policy / Approval（MUST）

- PolicyGate **MUST** 能对 tool/skill/exec 等高风险行为给出 allow/deny 决策与原因。
- ApprovalGate **MUST** 支持：
  - 生成 approval_request_id
  - 暂停/恢复（resume）执行
  - 审批结果写入审计与 run_events

## 2. Change Control（MUST）

对以下动作 **MUST** 生成 change_id 并形成审计证据：
- 发布/回滚 policy
- 发布/回滚 skill pack / tool pack（如果支持）
- prompt template / prompt revision 应用
- rollout 策略变更（灰度/金丝雀）

证据 **MUST** 可导出（便于合规与事故复盘）。

## 3. Rollout / Rollback（MUST）

系统 **MUST** 支持：
- 发布候选（candidate）与生效版本（active）的区分
- 回滚到上一个稳定版本（或 baseline）
- rollout 过程中自动化 smoke（若启用），失败触发回滚或阻断

## 4. Autosmoke（SHOULD）

当发生关键发布：
- **SHOULD** 触发 autosmoke
- autosmoke 结果 **SHOULD** 进入 artifacts/metrics，并可关联 change_id、run_id

## 5. 事件与审计（MUST）

以下数据 **MUST** 可查询/聚合：
- run_events（执行链路事件）
- policy audit logs（策略判定记录）
- tool/skill 统计（成功率/耗时/错误码分布）

