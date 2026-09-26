# V 波 Charter — 竖切验收（不是新功能，不是 M4）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-V-WAVE-CHARTER-2026-09` |
| 版本 | **v1.0**（V0 契约） |
| 日期 | 2026-09-19 |
| 状态 | ☑ **V0–V5** · ☐ 不称 M4/L5 |
| 关联 | [`ORG_K_WAVE_CHARTER.md`](./ORG_K_WAVE_CHARTER.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |
| 决策 | D-V1–D-V7 见 Decision Record §7 |

**纪律**：本文件批准的是验收波。不重做接口 YAML、飞书入站、试点岗位、用量账本、周报 KPI、K1–K5、活 YAML 直写拒绝、舰队默认拒绝。不打开 `m4_claim_allowed`。即便 K5 已落地，也不说出错已变成规则。

---

## 0. 一句话

让一条 it-ops 记录能按同一个 `trace_id` 回放，缺步写明，批准不等于写入，回滚范围写明。做完仍只是：企业级控制台 + 一条带人批闸门的试点。

---

## 1. 与已落地能力

| 已有 | V 波怎么用 |
|------|------------|
| K1 信号 `trace_id` + `trace_origin=extraction_confirm` | 回放的第一步来源。不新造抽取 |
| 仲裁单可带 `trace_id`；无则 `trace_origin=arbitration_propose` | 继承规则以本文 §3 为准。现状尚未强制 |
| OrgRun `trace_id=run_id`、`trace_origin=run` | 直接跑的任务。禁止回填抽取单 |
| 案例复制 Run 上的 `trace_origin` | 不是独立来源 |
| K5 `auto_apply=false` | 保持。另加 §4 启动断言，防旧路径绕过 |
| `approve_proposal` | **V4 已改**。HTTP 只认 `X-AIPLAT-ROLE`，`decide_ontology_approval` 判一次。body 里的角色不是授权。批准不写活 YAML |
| `rollback_case_evolution` | 只回滚已挂上的 store 提案。V5 只明示，不扩大 |
| `c5_pack_ready` / `m4_claim_allowed=false` | 材料包就绪 ≠ 客户已签收 |

---

## 2. 非目标

不做：第二域、第二入站渠道、业务系统写回、对话微调、自动生成 `SKILL.md`、舰队拉起多 Agent、删除 `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY`、扩大回滚到仲裁边、一键把 `m4_claim_allowed` 设为 true、新角色名、删五组菜单、用本波替代 M4。

---

## 3. trace 契约（V1 开工前写死）

### 3.1 `trace_origin` 闭集

只允许这些值。新值视为契约破坏，回放不得猜测。

| 值 | 谁可以写 | 含义 |
|----|----------|------|
| `extraction_confirm` | 仅 K1 确认信号 | 链的唯一起点。此时还没有 OrgRun |
| `arbitration_propose` | 仅仲裁开单，且调用方没有传入 `trace_id` | 这条仲裁没有上游抽取 |
| `inherited` | 仲裁、案例、提案在抄到上游 `trace_id` 时 | 本身不是来源。`trace_id` 必须与上游逐字相同 |
| `run` | 仅直接 `run_org_goal`，且不是由 K1 信号触发 | `trace_id` 必须等于该次 `run_id` |

回放响应里可以用 `absent` 表示「该步未发生」。`absent` 不写入信号、仲裁、任务、案例、提案。

### 3.2 继承与冲突

1. 由上一步触发的下一步必须抄同一个 `trace_id`。另造 id 再声称同源，视为违约，不是合并。
2. `trace_origin=run` 的任务不得写回任何抽取信号，也不得把 `run_id` 填进更早的仲裁单。
3. 回放只做 **精确 `trace_id` 匹配**。禁止用时间、实体名、操作者把两条链拼成一条。
4. 同一步出现两个不同 `trace_id`：返回 `conflict`，不选赢家，不补记录。
5. `inherited` 但找不到上游：该步记「该步未发生」或 `conflict`，不得升格成 `extraction_confirm` 或 `run`。
6. 缺任何一步只记「该步未发生」。禁止为了五步齐全而插入占位业务记录。

### 3.3 读接口

V1 的回放是只读业务状态：不得写活 YAML、不得写图边、不得创建或修改 OrgRun、案例、提案、信号、仲裁单。

允许写一条审计读（同一租户，`kind=trace_replay_read`）。这条审计不是业务步骤，不得出现在五步链里充数。

---

## 4. 已知缺口：自动 apply 必须在启动时失败

代码事实（2026-09-19）：`ontology_case_learning._edge_auto_apply_enabled()` 读取 `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY`，默认 false。为 true 时，旧的案例学习路径会调用 `try_auto_apply_edge_proposal`。K5 的 `enqueue_repeat_failure_proposals` 本身不调用它。开关本波不删。

**强制条款（口头约定无效）**：组织任务启动与 K5 扫描启动时必须断言该开关为 false。不为 false 则拒绝本次启动，不跑任务、不出提案、不写本体。告警原因固定为 `edge_auto_apply_forbidden`。

实现顺序：这是 **V1 回放代码之前的第一笔执行码**。V0 只写本条，不改 Python。V1 回放不得先于该断言合并。

---

## 5. 权限矩阵

不新建角色名（沿用 D-K2）。上游只注入身份。同一动作的允许与否只判决一次。

### 5.1 现状（V0 不改）

| 动作 | 代码事实 |
|------|----------|
| 提案批准 | `VersionedOntologyStore.approve_proposal` 读 body 里的 `approver_role`，对照 `TIER_APPROVAL_ROLES`。edge 档默认含 `*`，任意角色字符串（含空）都可通过。**不是 PolicyGate** |
| 提案 apply | 另一次调用 `apply_proposal`。批准函数本身不写活 YAML |
| 组织任务 HTTP | `POST …/goals/{id}/runs` 直接 `org_run_goal`。该路由 **没有** PolicyGate，也没有岗位白名单。岗位校验在飞书入站，不在这个按钮上 |

上表是 V0 当时的事实。V2 起开跑先过 `authorize_console_run`。V4 起 HTTP 批准走 PolicyGate，不再把 body 角色当授权。
| 回放 | V0 当时尚不存在。V1 起为 `GET …/org/traces/{trace_id}`，只读 |

### 5.2 V2 入口（体验不能变成旁路）

新的组织试点入口只能调用已有 `POST …/goals/{id}/runs` 与已有周报、待批读接口。禁止面板私有的第二套开跑函数。

V2 必须在 **这一条已有路由** 上补上岗位白名单，并只做一次权限判决。只在前端藏起「平台设置」不算完成。飞书入站与企微只出站从状态接口读取，禁止写死在文案里。

### 5.3 V4 批准（在 V1 之后）

| 步 | 谁做 | 结果 |
|----|------|------|
| 身份 | 上游注入 actor | 不把 body 里的 `approver_role` 当作授权 |
| 判决 | PolicyGate 一次 | 无权限 → 拒绝，提案仍为 draft |
| 批准成功 | 只改提案状态为 approved | 活 YAML 哈希必须不变 |
| 写入 | 人再调已有 `apply_proposal` | 才允许在既有令牌内写文件 |

验收三条都要有测试：无权限批准被拒；有权限批准后活 YAML 哈希不变；K5 扫描不调用自动 apply。再加 §4：开关为 true 时 K5 与组织任务拒绝启动。

---

## 6. 回滚边界（V5 只明示）

| 可回滚 | 不可回滚 |
|--------|----------|
| 案例已挂上、且已 apply 的 `VersionedOntologyStore` 提案（`rollback_case_evolution` → `rollback_proposal`） | 本地草稿 `draft_local_*` / `k5_local_*` |
| | 仲裁 `apply_ticket` 经 `resolve()` 写下的边 |
| | 无提案 id 的案例 |

API 与面板必须同时写出这两列。禁止出现「一键撤回任意变更」。带快照的 merge 边可撤，没有快照的边不能撤。见 [`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md)。

---

## 7. 签收面板（V3）

`c5_pack_ready=true` 只表示材料包在。`m4_claim_allowed` 保持 false，直到客户沙箱真线与人工记录，且该记录不得由 V3 的按钮写入。V3 不提供签收按钮。

---

## 8. 阶段

| 阶段 | 内容 | 本文件状态 |
|------|------|------------|
| V0 | 本文 + Decision Record §7 | ☑ 2026-09-19 |
| V1-pre | §4 启动断言。先于回放合并 | ☑ **2026-09-19** `edge_auto_apply_block`；组织任务与 K5 扫描拒绝 |
| V1 | 只读五步回放。缺步标明。遵守 §3 | ☑ **2026-09-19** `GET …/org/traces/{trace_id}` |
| V2 | 侧边栏试点入口 + §5.2 后端校验 + 渠道状态来自接口 | ☑ **2026-09-19** `POST …/goals/{id}/runs` 先 `authorize_console_run`；入口 `/org/pilot` |
| V3 | 平台指标与待签收分列。无签收按钮 | ☑ **2026-09-19** `GET …/org/signoff`；价值看板分列。无写入 |
| V4 | §5.3。在 V1 之后 | ☑ **2026-09-19** `decide_ontology_approval` 一次；批准不写活 YAML；K5 不调用自动 apply |
| V5 | §6 的 API/UI 文案与测试。不扩大回滚 | ☑ **2026-09-19** `GET …/org/rollback/scope`；`k5_local_*` 与 `draft_local_*` 拒绝回滚 |

---

## 9. 宣布用语

> V 波 V0–V5 于 2026-09-19 收口。一条 it-ops 记录可按 `trace_id` 回放，缺步写「该步未发生」。控制台开跑先过岗位白名单。材料包与签收分开，没有签收按钮。提案批准只经 PolicyGate 一次，批准不写活 YAML。本体提案回滚不覆盖草稿。带 `edge_before` 的 merge 边由 E 波撤回，没有快照的边仍不能撤。对外只说：企业级控制台，加上一条带人批闸门的 it-ops 试点。不是超级组织，也不是 L5。即便 K5 已落地，也不说出错已变成规则。
