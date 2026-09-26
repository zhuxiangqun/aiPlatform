# H 波 Charter — 闸门效率与签收加速（不是放权，不是 M4）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-H-WAVE-CHARTER-2026-09` |
| 版本 | **v1.0**（H0 契约） |
| 日期 | 2026-09-19 |
| 状态 | ☑ **H0–H5** · ☐ 不称 M4/L5 |
| 关联 | [`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |
| 决策 | D-H1–D-H8 见 Decision Record §9 |

**纪律**：H0–H5 已落地。H4 无规则文件时沙箱开关打开，live 拒绝，仍不写活本体。H5 只出草稿包；人批后才登记既有市场，不自动上架，不写 SKILL.md。不打开 `m4_claim_allowed`。批准写路径不新增第二套。即便 K5 已落地，也不说出错已变成规则。证据包不是签字。价值卡不是签收。H4 自动只改队列状态，永不调用 `apply_proposal` / `resolve`。

---

## 0. 一句话

让待批一眼定夺，让签收证据一键导出，让收益按可审计数字翻译。人批闸门一条不拆。做完仍是：企业级控制台 + 一条带闸门的 it-ops 试点。客户尚未签收。

---

## 1. 与已落地能力

| 已有 | H 波怎么用 |
|------|------------|
| 抽取待审 / 仲裁单 / 提案 / HITL | H1 聚合为 inbox；批准仍走既有路由 |
| `replay_org_trace` | 快照与证据包引用同一条回放，不另造链 |
| `weekly_kpi` / `weekly_usage` | H2/H3 只读消费；`billing` 仍为 null |
| `customer_signoff_view` / C5 包 | H2 导出嵌入；签字栏留空 |
| `rollback_scope` | 证据包复用两列 |
| `authorize_console_run` / PolicyGate 批准 | 不改判决语义；快照无权限不给批 |
| E2 边回滚 | 不扩大；证据包只引用范围说明 |

---

## 2. 非目标

不做：第二域、第二入站渠道、生产舰队、自动 `apply_proposal` / `resolve`、删除 auto-apply 环境变量、全量 Event Sourcing、价目/发票/SKU、程序打开 `m4_claim_allowed`、新角色名、删五组菜单、Mock 客户全家桶（另立 M4 Sandbox Kit）、本波实现接口限流熔断代码（规则可先写在 §7，实现另迭代）。

必做：**H0–H3**。  
已另宣布并落地：**H4**（无规则文件时沙箱开关打开；live 拒绝）。  
已另宣布并落地：**H5**（草稿包 + 人批登记；不自动上架）。

---

## 3. 快照契约（H1 开工前写死）

### 3.1 只读组装

`GET …/org/approvals/inbox` 与 `GET …/org/approvals/{kind}/{id}/snapshot` 只组装已有记录。禁止为补全上下文调用 LLM。缺字段写「该信息未发生」或省略键，禁止编造。

种类闭集：`extraction` · `arbitration` · `proposal` · `hitl`。

### 3.2 性能

- 列表必须分页；默认页大小 ≤ 50；禁止全表/全文件无界扫描当列表。  
- 详情允许秒级延迟；超时返回 `status=partial` 与已凑齐字段，不得为凑齐而阻塞写入路径。  
- 快照结果可短 TTL 缓存；缓存失效不得改变业务状态。

### 3.3 安全与脱敏

- 身份只认 `X-AIPLAT-ROLE`（与 V4 一致）。空身份拒绝。  
- 无批准权限的角色可读脱敏快照，不可调用既有批准写路由。  
- 快照 API **必须**按角色做字段脱敏。原文摘录、内部草稿节点、密钥、凭证 env 名对应的值，对非 admin/approver 默认遮罩。内部审批 ≠ 全量明文。  
- 脱敏规则配置化；缺省从紧。

### 3.4 写路径不变

批准、驳回、确认、decide、apply 仍走既有端点。H1 不新增第二套写函数。批准后活 YAML 哈希必须仍可变仅当调用既有 `apply_proposal`——H1 的批准动作本身不写活 YAML。

---

## 4. 证据包契约（H2）

### 4.1 只读导出

`GET …/org/signoff/evidence-pack` 不改变业务状态。返回 JSON；可选 Markdown 渲染。封面固定：

> 本包不是签字。`m4_claim_allowed=false`。客户尚未签收。

### 4.2 客户可见边界

递给客户 CTO 的视图必须过滤：内部工程师草稿节点、内部沟通、平台调试字段。只保留业务事实、审批结果、KPI、用量摘要（无价目）、回放摘要、回滚范围、C5 自动/人工分列、空白双签表。

### 4.3 体积

代表性 `trace_id` **至多 5 条**（可用查询参数下调，不可上调突破契约上限）。Markdown 篇幅受控；超限截断并注明「已截断」。

### 4.4 预留字段

允许 `sandbox_mode` 布尔字段（默认 false）。本波不附模拟联调记录。将来 M4 Sandbox Kit 可写入该段；不得借此把 `m4_claim_allowed` 设为 true。

---

## 5. 价值翻译契约（H3）

### 5.1 公式与诚实

```
saved_person_hours = closed_runs × baseline_minutes_per_incident / 60
mtta_delta_seconds = baseline_mtta_seconds − current_mtta_seconds   # 仅当基线存在
```

禁止准确率口号。禁止 LLM 编「价值故事」。

### 5.2 基线

- 配置落在租户隔离路径（按 `tenant_id`）；禁止跨租户读取。  
- 响应必须带 `baseline_source`：`customer_provided` | `platform_default` | `missing`。  
- `missing` 时：不显示节省人时；文案可提示补充基线；`baseline_missing=true`。  
- 无基线宁可不显示，也不编数字。

### 5.3 与签收

价值卡不是签收。无按钮。不得改 `m4_claim_allowed`。

---

## 6. H4 / H5

### 6.1 H4 沙箱规则内自动通过（已宣布 · 无文件时沙箱开）

| 可自动 | 不可自动 |
|--------|----------|
| 队列状态：抽取确认、仲裁 decide（精确键、无跨域、阈值内） | `apply_proposal`、`resolve`、写 `_cross_domain`、写活 YAML |
| 仅沙箱 flag 打开时 | 生产 live IO |

熔断：单日自动通过率超过阈值（默认 **20%**）→ 自动关闭规则并告警，要求人工排查。  
`auto-audit` 仅 admin（或既有治理角色）可读；不对普通 FDE 开放。  
一旦「自动通过」路径调用了 `apply_proposal` 或 `resolve`，视为契约破坏，记最高级别审计并拒绝该次写入。

### 6.2 H5 技能人批打包（已宣布）

仅：`skill_candidate` → `AIPLAT_HOME/org/skill_drafts/*.json` → admin 人批 → `SkillMarketplace.register`。  
不写 `SKILL.md`。未人批不得登记。驳回不登记。

---

## 7. 接口限流（规则先写，实现另迭代）

H0 记录意图：合法 Interface 调用应具备限流与熔断，失败时降级而非崩进程。  
**本波不实现代码。** 不阻塞 H1–H3。

---

## 8. 阶段

| 阶段 | 内容 | 本文件状态 |
|------|------|------------|
| H0 | 本文 + Decision Record §9 | ☑ 2026-09-19 |
| H1 | 审批 inbox + 快照；分页；脱敏；既有写路径 | ☑ **2026-09-19** `GET …/org/approvals/inbox` + `…/snapshot` |
| H2 | 证据包导出；≤5 traces；客户可见过滤；`sandbox_mode` 预留 | ☑ **2026-09-19** `GET …/org/signoff/evidence-pack` |
| H3 | 价值翻译；基线租户隔离；`baseline_source` | ☑ **2026-09-19** `GET …/org/value/translation` |
| H4 | 规则内队列自动通过 + 熔断 | ☑ **2026-09-19** 无规则文件时沙箱开关打开；live 拒绝 |
| H5 | 技能人批打包 | ☑ **2026-09-19** 草稿包；人批后 `SkillMarketplace.register`；不写 SKILL.md |

---

## 9. 宣布用语

> H 波 H0–H5 于 2026-09-19 落地：待批快照、证据包、价值翻译、沙箱队列自动通过（无规则文件时沙箱开、live 拒）、技能草稿包（人批才登记）。人批闸门未拆；写活本体仍须人批 apply。这不是 M4，也不是 L5。
