# Org Phase C Charter — 渠道入站 · Interface 一等化 · 岗位治理

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-CHANNEL-INTERFACE-CHARTER-2026-09` |
| 版本 | **v1.6**（C1.5 Interface YAML 权威 · M4 未签） |
| 日期 | 2026-09-18 |
| 状态 | ☑ **C0–C5** · ☑ **C1.5 YAML** · ☐ M4 客户签收 |
| 关联 | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) · [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md) |
| 决策 | D6–D10 见 Decision Record §5 |

**纪律**：C1–C5 与 C1.5 已落地。Interface 权威是 `interfaces/{ref}.yaml`；`connector.live` 只读兼容，不双写。`m4_claim_allowed` 恒 false。本文不授权写生产、不开放第二渠道、不宣称 L5。

---

## 0. 一句话

在 **Org L5 单线 it-ops 闭环（沙箱）** 之上，补齐：**协作入口能下任务 → 本体可回放调度证据 → Interface 白名单执行 → 岗位可治理 → 用量可审计（不计费）**；客户真线签收（M4）**独立跟踪**，不挡平台侧 C 波关闭。

---

## 1. 与 Org L5 / 两张图的关系

| 来源 | 取 | 弃 |
|------|----|----|
| Org L5 Charter A–E | 全部继承；不推翻 | — |
| 渠道→数字员工→本体→业务系统 | 入口统一、能力调度、知识沉淀、系统执行 | 多线 CRM/财务/HR；另起 OntoStar 品牌 |
| 英伟达五层 / Token 租赁叙事 | 「管 Agent / 目标闭环」；用量账本打底 | 能源芯片栈；本期计费 SKU；App 消亡 |

---

## 2. 可验收定义（C0–C5）

| # | 条件 | 关闭证据 |
|---|------|----------|
| **C0** | 一次自然语言任务，**本体语义调度可回放** | 同一 `trace_id` 下可见 **Object / Action / Interface / Skill / PolicyGate**（各至少一次命中或显式 skip 原因），**不只** OrgRun 创建 |
| **C1** | ≥1 协作渠道：NL → 触发同一 OrgGoal Run | 入站日志与 OrgRun **同源 `trace_id`** |
| **C2** | 本体侧可声明 Interface；Agent **禁止**绕过 | seed + 单测；未登记 host / 任意 SQL → 拒绝 |
| **C3** | it-ops：定位 → fetch → Action 过闸 → 审计可回放 | ActionStore + 周报 ≥1 模拟周 |
| **C4** | 例外 HITL；周报绑 MTTA / 根因率 / 例外比 | weekly API + 面板 |
| **C5 包** | **M4 现场签收包就绪**（清单/门禁/Runbook） | 文档 + `field-ops/checklist`；**≠** 客户已签字 |

**话术门禁**

| 完成态 | 对外可说 | 不可说 |
|--------|----------|--------|
| 平台 C 波（C0–C4 + C5 包） | 协作入口触发组织任务（试点）；受控接口登记 | 全域数字员工；L5 已达成；已按 Token 售卖 |
| M4 客户真线 + 人工签收 | **有条件**组织级（单线）L5 | 全域企业大脑 |

未满足 C0：不得对外写「本体语义调度」，只称「渠道→组织任务竖切」。

---

## 3. 非目标

1. 重做语义网产品 / 第二品牌引擎  
2. 同步接 CRM + 项目 + 财务 + HR  
3. Token 价目表 / 对外计费 SKU  
4. 默认放开无门控多 Agent  
5. 拆掉 FDE/治理签收台  
6. harness 硬编码企微/飞书业务分叉  
7. C2 同时开第二入站渠道  
8. 将客户真线当作平台侧 C 波硬依赖  

---

## 4. 工作流（W8–W12）

| ID | 名称 | 交付物 | 阶段 |
|----|------|--------|------|
| W8 | Interface 一等化 | InterfaceSpec + fetch/Action 只认登记项 | **C1** |
| W9 | Channel → Org Ingress | 单渠入站 → `org_run_goal`；回写卡片 | **C2** |
| W10 | DigitalPost | 可治理岗位契约 | **C3** |
| W11 | 用量账本 | Run/Action/token 归因；异步不阻塞 | **C4** |
| W12 | M4 签收包 | 清单/门禁就绪；客户线独立 | **C5 包** |

依赖：`W8 → W9`；`W10`∥`W9` 轻量；`W11` 不阻塞 W9；W12 客户侧另跟踪。

---

## 5. D6 首渠裁定（仓库证据）

**决议：首渠 = 飞书（入站 `lark` · 出站 `feishu`）· 单开 · 不开企微入站。**

| 证据 | 结论 |
|------|------|
| 本机 `AIPLAT_FEISHU_WEBHOOK` / `AIPLAT_WECOM_WEBHOOK` | 均 **unset**（无法用「现网已配」决胜） |
| `AIPLAT_FDE_NOTIFY_CHANNELS` 默认 | `"feishu,wecom,slack"` — **飞书列首位**（`fde_notifier.py`） |
| MessagingGateway | `GatewayChannel.FEISHU` + `AIPLAT_FEISHU_WEBHOOK` 与企微对称注册（`server.py` / `messaging.py`） |
| 入站适配器 | `LarkAdapter` 解析 `message_id` / `chat_id` / `open_id`；`WeComAdapter` 更薄 |
| 代码示例 | `agents.py` Gateway 示例用 `channel="feishu"` |

**命名铁律（C2 必守）**

| 方向 | 规范 ID | env / 类型 |
|------|---------|------------|
| 入站 | `lark`（`ChannelType.LARK`） | app `channels/adapters/lark.py` |
| 出站通知 | `feishu`（`GatewayChannel.FEISHU`） | `AIPLAT_FEISHU_WEBHOOK` |
| Org Ingress | 内部统一 `channel=feishu`，映射 `lark↔feishu` | 禁止双写两套业务逻辑 |

企微保留出站能力与适配器存在性；**Phase C 入站白名单仅飞书**。

---

## 6. InterfaceSpec 契约（W8）

### 6.1 权威与迁移（D7）

| 阶段 | 权威存放 | 规则 |
|------|----------|------|
| **C1** | `connector.json` → `live`（单源） | 禁止第二写源 |
| **C1.5** | `AIPLAT_HOME/interfaces/{interface_ref}.yaml`（种子 `workspace_seeds/interfaces/`） | ☑ **2026-09-18** 落地；无 YAML 时旧 `live` **只读兼容**；禁止双写 |

### 6.2 字段（C1 必须落盘；执行可渐进）

| 组 | 字段 | C1 执行 |
|----|------|:------:|
| 标识 | `interface_ref`, `domain_id`, `version`, `enabled` | ✅ 校验 |
| 传输 | `adapter=http_json`, `allowed_hosts`, `path_template`, `base_url_env` | ✅ 已有路径强化 |
| 契约 | `input_schema`, `output_schema` | ☑ 落盘；校验可先 warn |
| 绑定 | `bound_action_ids[]` | ☑ 落盘；Action 侧校验逐步加 |
| 运行 | `timeout_sec`, `retry`, `rate_limit`, `idempotency_key_path` | timeout ✅；其余可 stub |
| 安全 | `auth` 仅 env/密钥引用；租户字段 | ✅ 禁明文 |
| 审计 | `audit_fields[]`, `error_codes` | ☑ 落盘 |

**禁止**：Agent/Skill 自带 `base_url` 覆盖白名单；locate 内嵌客户 SQL；未登记 Interface 的出站。

### 6.3 与现网代码衔接

- 消费点：`org_live_adapter.fetch_live_http` / 未来 write adapter  
- 门禁：`live_io_gates` + Org L5 书面解锁双门  
- 默认：`enabled=false`、空 `allowed_hosts` → `declared` 不足，不出站  

---

## 7. 渠道入站安全专章（W9 / C2 开工前必读）

缺任一条 → **不得宣布 C2 联调完成**。

| # | 要求 | 说明 |
|---|------|------|
| 1 | Webhook 签名校验 | 飞书 encrypt/signature 按官方；失败 401/403 |
| 2 | 重放保护 | timestamp + nonce；窗口外拒绝 |
| 3 | 身份映射 | 渠道路用户 → `tenant_id` / `actor_id`；未映射拒绝 Run |
| 4 | 白名单 | 渠道 ∈ 首渠；岗位 ∈ DigitalPost.channel_allowlist |
| 5 | 消息幂等键 | `channel + message_id`（或等价）→ 同一键不重复创建 OrgRun |
| 6 | 多轮澄清 | 最小卡片：确认 / 取消；取消不建 Run |
| 7 | 失败回执 | 明确错误文案回渠道；禁静默 |
| 8 | 超时 / 重试 | 入站 ACK 与异步执行分离；重试遵守幂等 |
| 9 | 会话映射 | `chat_id`/thread ↔ `run_id` 可查表 |
| 10 | 唯一业务入口 | 只产 Ingress 事件 → `CoreFacade.org_run_goal` / HITL resume；**禁**渠道直写库 |

归属：HTTP 入站在 `aiPlat-app` 或 `platform` 薄代理；业务在 `core/apps/org`；门面 `CoreFacade`。

---

## 8. DigitalPost 岗位契约（W10）

```text
DigitalPost {
  post_id, title, version, enabled, scope (tenant/domain),
  domain_id,
  org_goal_id | goal_template,
  skill_whitelist[],
  interface_refs[],          # 接口白名单
  data_scope[],              # 数据域权限
  exception_policy,
  channel_allowlist[],       # 含 feishu
  quota_hooks[],             # 挂现有 tenant quota，可空
  sla { timeout, escalate },
  audit_requirements[],
}
```

岗位 = **可治理组织岗位**，不是 Goal 触发别名。

---

## 9. 用量账本（W11 / D8）

| 规则 | 要求 |
|------|------|
| 范围 | Run / Action / LLM token 归因（跟 `trace`） |
| 写入 | **异步**、幂等、可重放 |
| 失败 | **不阻塞** OrgRun |
| 禁止 | 价目表、发票、对外 SKU |
| API | 对内 `GET …/org/usage/weekly`（2026-09-18 已落地；`billing` 恒 null） |

---

## 10. M4 解耦（W12）

| 轨道 | 完成定义 |
|------|----------|
| **平台侧 C 波** | C0–C4 绿 + M4 **签收包**就绪 |
| **M4 话术** | 客户沙箱/真线 + 人工签收（独立看板） |

客户工期按乐观×**1.5～2** 预期，不写死 2–6 周。

---

## 11. 粗工期（含缓冲）

| 阶段 | 人日（一人，含缓冲） |
|------|----------------------|
| C0 本文 | 已覆盖 |
| C1 W8 | 8–12 |
| C2 W9 | 12–18 |
| C3 W10 | 6–10 |
| C4 W11 | 6–10 |
| 平台侧合计 | **约 12–18 人周** |
| C5/M4 客户 | 另计 |

---

## 12. Go / No-Go

| 项 | 值 |
|----|-----|
| 是否以本 Charter + 评审增补为 Phase C 基线？ | ☑ **Go**（会话 2026-09-18） |
| D6–D10 | ☑ 已决（见 Decision Record §5） |
| C1 开工 / 落地 | ☑ **2026-09-18** 宣布开工并落地（InterfaceSpec + API + 单测） |
| C1.5 落地 | ☑ **2026-09-18** YAML 权威；`POST /org/interfaces/{domain}/materialize` 只写 home yaml |
| C2 开工 / 落地 | ☑ **2026-09-18** `POST /org/channels/feishu/events`；签名/重放/身份/确认门/幂等/岗位渠道白名单；只调 `org_run_goal` |
| C3 开工 / 落地 | ☑ **2026-09-18** DigitalPost：`GET /org/posts`；入站须过数据域/契约门；确认时带 `org_goal_id` |
| C4 开工 / 落地 | ☑ **2026-09-18** `GET /org/usage/weekly`；异步幂等账本；失败不阻塞 OrgRun；`billing=null` |
| C5 签收包 | ☑ **2026-09-18** [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)；`field-ops/checklist` 的 `c5_pack_ready`；**≠** 客户已签字 |
| M4 | 客户真线 + 双签另跟踪；`m4_claim_allowed` 恒 false |

**宣布用语（C0）**：  
> Org Phase C C0 于 2026-09-18 生效；首渠飞书（lark/feishu）；Interface 先 connector.live 单源；用量账本做薄不阻塞入站；第二业务系统不做；M4 客户线独立跟踪；对外仍为 L3 + 单线组织闭环（沙箱），直至 M4 签收。

**宣布用语（C1）**：  
> Org Phase C1（W8 Interface 一等化）于 2026-09-18 落地：`connector.live` 为 InterfaceSpec 单源；`GET /org/interfaces*`；live fetch 只认有效 Spec + 双门解锁；默认 enabled=false；对外仍非 M4。
