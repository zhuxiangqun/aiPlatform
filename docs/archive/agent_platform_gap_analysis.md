# 你们系统对标 OpenClaw / Hermes / Superagent 的差距评分表（初版）

> 目的：把“都关心”的生态/效率/安全三条路线，拆成可量化的能力项，给出你们当前（基于代码现状）评分、证据、差距与下一步动作。
>
> 评分范围：0~3（见下方“评分标准”）。**0/1/2/3 并不是好坏绝对值，而是“是否具备工程化闭环与可规模化程度”。**

## 评分标准（0~3）

| 分数 | 含义 |
|---:|---|
| 0 | 基本没有能力/仅概念 |
| 1 | 有局部实现或 PoC，但不可规模化、缺少治理/观测/测试 |
| 2 | 能用于生产的“能力模块”已具备，但尚未形成默认工作流/产品化体验/生态规模 |
| 3 | 能力闭环完整：可观测+可评测+可治理+可自动化，且对外体验/集成路径清晰 |

---

## A. OpenClaw 路线：生态/多入口/常驻助手（入口与产品化）

| 能力项 | 分数 | 你们现状（证据） | 主要差距 | 下一步（最短路径） |
|---|---:|---|---|---|
| 统一外部入口（Gateway） | 2 | 有 `/gateway/execute`，支持 channel/tenant/actor 注入、幂等 request_id、pairing（channel_user_id→user/session/tenant） | 未形成“多渠道适配 SDK”，仍偏“单入口 API” | 抽象统一 `ChannelAdapter`：auth/verify → normalize event → invoke → reply |
| Slack 级别集成 | 2 | gateway 内置 Slack 签名校验、response_url 回传；ConnectorDelivery 统一 webhook 投递 | 还缺“完整 Slack App 事件流模板”（event_callback、交互组件、线程等） | 提供官方 Slack Adapter 示例（事件→gateway→回复）+ 一键配置文档 |
| 多渠道生态（飞书/钉钉/企微/Telegram/Discord…） | 1 | 目前代码层面明显看到 Slack/gateway、delivery/webhook，其他渠道适配未形成体系 | 渠道数量与开箱体验不足 | 先补 2 个：飞书/企微（或 Telegram）并统一配置/密钥管理 |
| 常驻会话/上下文产品体验 | 2 | Memory sessions/messages API + store 支持 tenant 维度；可查询 context | “常驻助手产品形态”不足：会话管理策略、摘要、上下文裁剪策略未产品化 | 增加 session 策略（摘要/分层记忆/窗口化）+ UI/运营面板 |
| 技能生态分发/安装/回滚 | 3 | 你们已有 workspace skills + 变更治理（change-control）+ autosmoke + approval gate + evidence pack | 生态规模与“发现/评分/依赖”层缺失 | 做“skill pack catalog”：依赖、版本兼容、评分/使用量指标 |
| 连接器投递与 DLQ | 2 | ConnectorDelivery + 重试/DLQ 迹象存在 | 缺少统一监控/告警与可视化运营面板 | 增加 delivery dashboard（失败率、DLQ、重放） |

**OpenClaw 方向总体结论**：你们的“平台底座”强，但“渠道生态规模 + 即插即用产品化”偏弱。

---

## B. Hermes 路线：学习效率/成本/越用越顺（学习闭环）

| 能力项 | 分数 | 你们现状（证据） | 主要差距 | 下一步（最短路径） |
|---|---:|---|---|---|
| Trigger Eval（触发评测） | 3 | 已有 suite/run/results/metrics + A/B compare + suggest + apply（含写 SKILL.md / change-control） | live 仍是“阈值模拟”，未读取真实 routing 决策 | 做真 live：以 routing_decision/skill_candidates_snapshot 作为 ground truth 输入 |
| Quality Eval（执行质量评测） | 2 | 已有 quality_cases + 规则评分骨架 + 结果落库 | 缺少语义 grader、证据链（evidence）与回归门禁策略 | 引入 grader（可先 rule+LLM 混合），并把质量回归接入 apply gate |
| 学习沉淀载体（技能/SOP/模板） | 2 | 目前沉淀主要是：description/trigger_conditions、suite config | 沉淀还不够“结构化可复用”：缺 SOP 总结、工具链模板化、失败样本自动转用例 | 自动把失败样本→新增 eval case；把成功 run→提取 SOP/模板（半自动即可） |
| 成本治理（token/回合/工具调用） | 1 | 现有 run/syscall 体系可观测，但“成本指标”未作为一等公民暴露 | 缺：成本基线、回归检测、优化建议 | 在 execution_store 聚合 tokens/rounds/tool_calls，加入成本回归 gate |
| 在线学习信号（用户反馈/采纳率） | 1 | 有 runs、audit、gateway，但缺少显式“用户采纳/纠错”信号模型 | Hermes 的关键是线上闭环，不只是离线 eval | 增加 feedback API：accept/reject/edit；把反馈转成 eval 与建议 |
| 漂移控制（变更→回归→回滚） | 3 | change-control + autosmoke + approval gate + evidence pack 已形成强闭环 | 需要把“eval 回归”纳入默认策略 | apply 前强制：Trigger Eval + Quality Eval + 安全扫描（可配置策略 any/all） |

**Hermes 方向总体结论**：你们的“学习治理闭环”框架非常强，但缺少两块：**真实在线路由评测** 与 **成本/反馈信号体系化**。

---

## C. Superagent 路线：安全/治理/合规（可控与可审计）

| 能力项 | 分数 | 你们现状（证据） | 主要差距 | 下一步（最短路径） |
|---|---:|---|---|---|
| 权限/审批（HITL） | 3 | ApprovalManager + approvals API + 可配置 gate_policy（autosmoke/approval any/all） | 需要更标准化的“敏感操作目录”与默认策略 | 建立操作分类与默认规则（tool/skill/connector） |
| 审计与证据包 | 3 | audit_logs + change-control evidence 导出（json/zip）+ syscalls 事件完备 | 证据包可再“产品化摘要” | evidence pack 增加一页摘要：变更点、审批、冒烟、扫描、评测对比 |
| 供应链/签名门禁（技能） | 2 | 有 skill_signature_gate，支持 trusted pubkeys、未验证需审批 | 未覆盖“依赖/工具调用供应链风险” | 把 tools/capabilities 纳入签名与变更审查 |
| 输入输出安全扫描（DLP/注入） | 1~2 | 有 SecurityScanner（API key/凭据/PII/注入模式等）模块 | 关键差距：扫描是否进入默认关键路径（gateway/tool/memory/connector） | 先做“只告警+审计事件”，再升级为“阻断+审批” |
| 红队/攻击测试（持续回归） | 1 | 有 autosmoke 框架，但偏功能性冒烟 | 缺少安全基准集（prompt injection/data exfiltration/tool misuse） | 新增 security_eval_suite + job 化定期跑 + 失败告警 |
| 数据脱敏/最小披露 | 1 | 具备审批与扫描基础，但缺少系统性脱敏策略与落点 | 企业最常问：数据出入站如何脱敏 | connector 出站脱敏策略（regex+allowlist）+ evidence 记录 |

**Superagent 方向总体结论**：你们的治理/审计/审批是优势；主要差距是 **把安全扫描与红队评测“接入默认路径并可回归”**。

---

## 总体差距雷达（主观汇总）

| 维度 | 你们当前相对水平 | 关键短板一句话 |
|---|---|---|
| 生态/入口（OpenClaw） | 中等 | 缺“多渠道适配体系 + 开箱即用产品形态” |
| 学习/效率（Hermes） | 较强 | 缺“真实在线学习信号 + 成本治理 + 真 live 路由评测” |
| 安全/治理（Superagent） | 很强 | 缺“安全扫描/红队变成默认管道与回归门禁” |

---

## 90 天路线图（建议）

### P0（2 周）：把“现有优势”固化成默认门禁
1) apply gate 增加可配置：Trigger Eval + Quality Eval + 安全扫描（三者 any/all）  
2) evidence pack 增加 summary（变更点/审批/冒烟/评测/扫描结果概览）

### P1（4~6 周）：补齐 Hermes 的关键缺口
1) Trigger Eval 真 live：读取 routing_decision/skill_candidates_snapshot 做评测  
2) 成本指标：tokens/rounds/tool_calls 聚合 + 回归检测  
3) feedback 信号：accept/reject/edit → 自动转用例/建议

### P2（6~12 周）：补齐 OpenClaw 的产品化与生态
1) Channel Adapter SDK + 官方 Slack/飞书/企微模板  
2) Skill catalog（发现/依赖/版本兼容/评分/使用量）  
3) “一键接入渠道 + 一键安装技能包 + 一键冒烟 + 一键上线”的工作流

