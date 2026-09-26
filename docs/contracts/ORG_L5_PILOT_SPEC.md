# Org L5 Pilot Spec — it-ops 告警组织闭环（默认试点）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-PILOT-ITOPS-2026-09` |
| 版本 | **v1.0**（D1–D5 已决） |
| 日期 | 2026-09-18 |
| 状态 | ☑ 试点规格冻结 · 随 Phase 1 实施 |
| 主域 | **it-ops**（已决） |
| 薄切片 | data-gov 只读 `fetch`（D5 已决：做） |
| 关联 | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |

---

## 1. 用户故事（组织视角）

**作为** 运维负责人（组织角色，非单次 Chat 用户），  
**我希望** 系统按日程处理「开放告警 → 分诊 → 挂嫌疑 → 标根因」并留下周报，  
**以便** 团队只处理例外与升级，而不是每条告警手工点一遍演示按钮。

验收口吻（对内）：「同一 OrgGoal 连续两个模拟周次跑通，KPI 可出数。」

---

## 2. 范围边界

### 2.1 In Scope

| 项 | 说明 |
|----|------|
| 对象 | it-ops 告警实体及关联服务/中间件（GraphIndex） |
| 动作 | 已有种子：`triage_alert` / `link_suspect` / `mark_root_cause` |
| I/O | Phase 1：沙箱 connector `fetch`；写回默认只写 ABox；外系统 write 仅 stub |
| 编排 | 默认 **single** Agent 或单 Pipeline；multi 留 Phase 4 |
| UI | Org 目标/Run/周报页 + 深链 FDE⑦ / 治理面板；不重建执行台 |

### 2.2 Out of Scope（本试点）

- 自动改 it-ops.yaml 说明书（须提案门）  
- 真实 PagerDuty/工单生产写（D3=否，直至 W7 签字）  
- 全域 CMDB / 全量血缘  
- 数字员工编制 HR 流程  

---

## 3. 对象模型（最小）

### 3.1 OrgGoal（配置 + 运行时副本）

```yaml
# 种子示意 ~/.aiplat/org_goals/it-ops.yaml（实施时落地，本文仅契约）
goal_id: it-ops.alert_closure.weekly
domain_id: it-ops
title: 开放告警组织闭环
schedule: "0 9 * * 1"   # 或 manual
owner_role: ops_lead
kpi_refs: [mtta, root_cause_rate, exception_ratio]
allow_fleet: false
status: draft            # draft|active|paused|done|failed
steps:
  - id: locate_open
    kind: locate
    query_template: "open alert"
  - id: fetch_snapshot
    kind: fetch
    purpose: alert_status
  - id: triage
    kind: action
    action_id: customer_action:it-ops:triage_alert
    auto_if: action_level_allows
  - id: link
    kind: action
    action_id: customer_action:it-ops:link_suspect
    auto_if: action_level_allows
  - id: root
    kind: action
    action_id: customer_action:it-ops:mark_root_cause
    require_hitl_if: confidence_below_threshold
```

### 3.2 OrgRun

| 字段 | 说明 |
|------|------|
| `run_id` | 唯一 |
| `goal_id` | 外键 |
| `started_at` / `finished_at` | |
| `plan_snapshot` | 启动时冻结 steps（防配置中途漂移破坏审计） |
| `step_results[]` | status / entity_ids / action_audit_ids / error |
| `exceptions[]` | reason / hitl_ticket_id / resolution |
| `outcome_snapshot` | KPI 切片 |

### 3.3 状态机

```text
OrgGoal:  draft → active ⇄ paused → done
                 ↘ failed

OrgRun:   pending → running → succeeded
                      ↓
                   needs_hitl → running → …
                      ↓
                   failed / cancelled
```

---

## 4. 端到端主路径（Phase 1–2）

```text
1. Goal active（或手动 trigger）
2. 创建 OrgRun（冻结 plan_snapshot）
3. locate：GraphIndex 找 open 告警（复用 governance/locate 语义）
4. fetch：connector 拉沙箱快照（只读）
5. 对每个候选实体：
   a. dry-run Action（可选）
   b. 若策略允许 → execute triage / link / root
   c. 若需 HITL → needs_hitl，挂起 Run
6. 汇总 outcome_snapshot → 写周报缓冲
7. Run succeeded | failed（含归因码）
```

**硬禁止**：步骤 3–5 绕过 ActionRegistry 直接改客户库；locate 内嵌任意 SQL。

---

## 5. 例外策略矩阵（W4）

| 条件 | 行为 |
|------|------|
| Action 阶梯不允许自动 | HITL |
| `mark_root_cause` 且模型置信度 &lt; 阈值（配置） | HITL |
| fetch 失败 / 超时 | 重试 N 次 → escalate 例外 |
| 实体缺必填属性 | skip + 记入例外（不静默造数） |
| 同实体本周已 mark_root_cause | skip（幂等） |
| 补偿字段存在且 execute 失败 | 走 compensation 或标记 failed |

阈值与 N 一律配置，不进 harness 常量业务表。

---

## 6. KPI 定义（D2 建议）

| KPI ID | 名称 | 公式 | 数据源 |
|--------|------|------|--------|
| `mtta` | 分诊时延 | open→triaged 中位秒数（本 Run 窗口） | GraphIndex metadata / 状态变更审计 |
| `root_cause_rate` | 根因标注率 | `mark_root_cause` 成功数 / 已 triage 数 | ActionStore |
| `exception_ratio` | 例外占比 | HITL 次数 / 计划步数 | OrgRun.exceptions |

**禁止**作为本试点 KPI：材料补齐率、OWL「已验证」、Wiki 命中率冒充闭环质量。

周报：`GET …/org/goals/{goal_id}/weekly?week=` → 三指标 + Top 失败归因 + 待批例外列表。

---

## 7. API 草图（Phase 1–3，实施时经 CoreFacade）

| 方法 | 路径（建议前缀 `/api/platform/apps/org`） | 阶段 |
|------|------------------------------------------|------|
| GET | `/goals` | P2 |
| POST | `/goals/{id}/activate` | P2 |
| POST | `/goals/{id}/runs` | P2 |
| GET | `/runs/{id}` | P2 |
| POST | `/runs/{id}/resume`（HITL 后） | P2 |
| GET | `/goals/{id}/weekly` | P3 |
| POST | `/connectors/{domain}/fetch` 或挂现有 fde `…/governance/fetch` | P1 |

Phase 1 若暂挂 FDE 路由：须在 Decision Record 记 **迁移债**（迁到 `apps/org` 的 Deadline）。

---

## 8. 连接器契约（W2）

| 能力 | 输入 | 输出 | 安全 |
|------|------|------|------|
| `fetch_by_entity` | domain_id, entity_id, purpose | snapshot JSON + source | 只读；密钥仅 connector.json |
| `write_via_action` | 仅 Action handler 调用 | ack + external_ref | 禁 REST 裸写；D3 下仅 stub |
| `dry_run` | 同 write 载荷 | preview | 高风险默认 |

沙箱：`AIPLAT_ORG_IO_MODE=sandbox|deny|live`（live 仅 W7 签字后）。

---

## 9. 测试与冒烟

| 级 | 内容 |
|----|------|
| 单测 | fetch 无配置→明确错误；stub→OK；locate 不触网 |
| 契约测 | OrgRun 状态机非法迁移拒绝 |
| 回放 | 固定种子图跑 Run×2，KPI 字段非空 |
| 手工 | FDE⑦ 种 it-ops 教学图 → Org 手动 trigger → HITL 路径点一次 |

---

## 10. data-gov 薄切片（可选 D5）

**仅证明** connector 通用：`locate(积分流水)` → `fetch` 元数据只读。  
**不做** OrgGoal 周闭环（避免双线抢人）。  
关闭标准：1 个集成测试 + 文档一行诚实说明。

---

## 11. 与现有演示的关系

| 已有 | 试点如何用 |
|------|------------|
| FDE⑦ 种图 / 点 Action | 仍是人工验收台；OrgRun 是自动编排入口 |
| `governance/locate` | Run 步骤复用语义 |
| `governance/quality` | 不替代 it-ops KPI；可深链 |
| 案例学习 / evolve | Run 摘要可写入案例；evolve 不自动改 TBox |

---

## 12. 开放问题（Pilot 内）

1. 置信度阈值默认多少？建议 0.7，可配。  
2. 每周处理告警上限（防洪水）？建议 `max_entities_per_run=20`。  
3. MTTA 时间戳以 GraphIndex metadata 还是 ActionStore 为准？建议 **ActionStore 为主、metadata 为辅**。
