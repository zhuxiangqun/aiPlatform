# 可执行落地计划（基于差距评分表）

> 目标：把“生态/学习/安全”三个方向同时推进，形成 90 天内可交付的里程碑（每条都有明确验收指标、代码落点与最小 PR 切片）。
>
> 说明：负责人/日期可按你们团队实际情况填充；这里先给 **可直接建 Jira/Linear issue 的颗粒度**。

---

## 0. 总原则（确保不走偏）

1) **所有变更都必须可回归**：任何会改变路由/触发/权限/执行行为的改动，必须走 change-control（changeset）并产生 evidence。  
2) **“学习”必须绑定评测与回滚**：所有自动建议/自动应用都要能 A/B 对比并可回滚。  
3) **安全能力先“观测+审计”，再“阻断+审批”**：先不影响生产，再逐步加 gate。

---

## 1) 里程碑总览（90 天）

### M0（第 1~2 周）：把优势固化成默认门禁 + 报告可读
- [P0-1] Apply gate 支持“三件套”策略：Trigger Eval + Quality Eval + Security Scan（any/all）
- [P0-2] Evidence pack 增加摘要 summary（给管理层/合规直接看）

### M1（第 3~6 周）：补齐 Hermes 关键缺口（真 live + 成本 + 反馈）
- [P1-1] Trigger Eval 真 live：从 routing_decision / candidates_snapshot 取数
- [P1-2] 成本指标：tokens/rounds/tool_calls 聚合 + 回归门禁
- [P1-3] Feedback API：accept/reject/edit → 自动转 suite case / suggest

### M2（第 7~12 周）：补齐 OpenClaw 产品化缺口（多渠道适配+开箱模板）
- [P2-1] Channel Adapter SDK（Slack/飞书/企微 2~3 个官方模板）
- [P2-2] Skill catalog（发现/依赖/版本兼容/评分/使用量）最小可用版

---

## 2) 可执行任务清单（按 PR 切片）

下面每个任务都可以直接建工单：**输入/输出、验收、代码落点、依赖**齐全。

---

### P0-1：Apply gate 加入 Eval + Security Scan（any/all）

**目标**：apply-engine-skill-md-patch 这条链路，在现有 autosmoke/approval gate 基础上，再引入可选的评测与安全扫描门禁。

**范围**：
- 针对 `change_id` 的 proposed patch：在 apply 前自动触发（或校验已存在）：
  - Trigger Eval（suite/run）
  - Quality Eval（suite/run，可选）
  - Security scan（对 diff / updated_raw 做扫描，可选）

**建议设计**（最小切片）：
1) 在 changeset（proposed）里写入 `recommended_suites`：例如 `{trigger_suite_id, quality_suite_id}`（允许为空）
2) apply API 新增 query：
   - `gate_policy`（已有：autosmoke/approval/any/all）
   - `eval_gate=off|trigger|trigger+quality`
   - `security_gate=off|scan_warn|scan_block`
3) 若 eval_gate 开启：
   - 先尝试找 change_id 下是否已有对应 eval run 的 changeset 事件（避免重复跑）
   - 没有则创建 job（kind=skill，target_id=skill_eval_trigger / skill_eval_quality），run_job_once
4) 若 security_gate 开启：
   - 对 proposed changeset.result.updated_raw（或 diff）运行 `SecurityScanner`，将结果写入 changeset 事件 `skill_eval.security_scan`
   - scan_warn：仅记录 + 继续
   - scan_block：高危（HIGH/CRITICAL）则 409 + next_actions

**代码落点**：
- `core/api/routers/change_control.py`：apply endpoint 加 eval/security gate
- `core/apps/quality/scanner.py`：复用
- `core/governance/changeset.py`：继续用 record_changeset 记录结果

**验收标准**：
- 当 eval_gate 开启且 eval 不通过 → 返回 409（gate_error_envelope），并给 next_actions（去看失败 run / 重试）
- 当 security_gate=scan_block 且命中高危 → 返回 409（带 vulnerabilities 摘要）
- 证据包 evidence.json 包含新增事件

**依赖**：
- 已有：skill_eval_trigger / skill_eval_quality / change-control / jobs / next_actions

---

### P0-2：Evidence pack 增加 summary（合规可读）

**目标**：导出的 evidence 包里增加 `summary.md` 或 `summary.json`，让非研发也能看懂：
- 变更是什么
- 谁审批
- 冒烟是否通过
- 评测对比是否回归
- 安全扫描是否有风险

**代码落点**：
- `core/api/routers/change_control.py` → `export_change_control_evidence()`

**输出建议**：
- ZIP 包里新增：`summary.md`（人读）+ `summary.json`（机器读）

**验收标准**：
- summary 中必须包含 links（change-control/audit/approvals/runs）
- summary 可独立阅读（不需要打开 evidence.json 才知道发生了什么）

---

## 3) Hermes 路线（学习闭环）任务

### P1-1：Trigger Eval 真 live（从 routing events 取数）

**目标**：Trigger Eval 的 live 不再“阈值模拟”，而是对每条 query 触发一次真实路由/选择，并从 `syscall_events(kind=routing,name=routing_decision)` / `skill_candidates_snapshot` 中提取结果。

**实现策略（最小可行）**：
1) 新增一个轻量执行入口：对每条 query 调用一次最小 agent loop（或最小 routing function），保证会产生 routing_decision 事件
2) 以 run_id/trace_id 或 routing_decision_id 关联，抓取：
   - selected_kind / selected_skill_id
   - candidates top-k
3) 写入 skill_eval_results（selected_kind/selected_skill_id/candidates）

**代码落点候选**：
- `core/apps/skills/eval_trigger.py`：mode=live 分支重写
- `core/harness/execution/loop.py`：已有 routing_decision/skill_candidates_snapshot 事件

**验收标准**：
- live 结果与实际 routing_decision 一致（用集成测试验证）
- 能回放：run_id 能在 routing explain 里查到

---

### P1-2：成本指标与回归门禁

**目标**：把“省不省”变成可量化指标，并能作为 gate。

**最低指标集**：
- token（prompt/completion/total）
- tool call 次数
- 回合数（step_count）
- 总耗时、p95

**落点建议**：
1) 扩展 execution_store：对 run 计算 aggregated metrics（或者在 runs 表 metadata 里写入）
2) 新增 `/metrics/cost` 或复用现有 observability metrics
3) 在 apply gate 可选启用：成本回归阈值（例如 >20% 直接阻断或需要审批）

**验收标准**：
- 任意 run 都能查询到 cost summary
- 支持按 tenant/agent/skill 聚合

---

### P1-3：Feedback API（线上学习信号）

**目标**：让用户反馈成为学习闭环输入：accept/reject/edit，自动沉淀到 suite。

**最小数据模型**：
- feedback_id, run_id, tenant_id, user_id
- decision: accept/reject/edit
- comment, edited_output(optional)

**最小工作流**：
- reject → 自动把 query 加入 negative_examples 或 quality_cases
- accept → 自动把 query 加入 positive_examples（或提升权重）
- edit → 生成 quality_case（expected contains/edit diff）

**验收标准**：
- 每次反馈都会落 audit_log
- suite 自动更新可追溯（changeset）

---

## 4) OpenClaw 路线（入口生态）任务

### P2-1：Channel Adapter SDK + 官方模板

**目标**：把 gateway 从“一个 API”升级成“多渠道适配框架”。

**最小 SDK 形态**：
- 统一事件结构：channel、channel_user_id、text、attachments、reply_token/response_url
- verify/auth hook（如 Slack signature）
- reply hook（回传/异步投递）

**先做 2~3 个官方模板**：
- Slack（你们已具备签名/回传能力，补全事件类型）
- 飞书/企微（二选一）
- Generic Webhook（已有 ConnectorDelivery 可复用）

**验收标准**：
- 每个 adapter 都能复用同一个 `/gateway/execute`（或内部函数），且能完成一个“消息→回答”的端到端演示

---

### P2-2：Skill Catalog（最小可用）

**目标**：让“生态厚”可运营：可发现、可依赖、可评分。

**最小功能**：
- list skills（已有）+ 标签/能力（capabilities）过滤
- 依赖声明（tools/capabilities）
- 版本兼容字段（min_platform_version）
- 使用量指标（来自 syscall_events）

**验收标准**：
- 可按标签/能力筛选技能
- 能看到“最近使用/成功率/失败率”

---

## 5) 任务模板（复制到工单）

**标题**：\[方向\]\[模块\] 任务名  
**背景**：一句话业务目标  
**范围**：包含/不包含  
**验收标准**：可测试、可观测、可回滚  
**代码落点**：文件/模块  
**风险**：安全/兼容/性能  
**回滚方案**：开关/版本回退/禁用  

