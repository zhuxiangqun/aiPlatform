# Org L5 现场运行手册（W7 / Phase 4）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-RUNBOOK-2026-09` |
| 版本 | **v1.2** |
| 日期 | 2026-09-20 |
| 关联 | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) · [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) |
| 状态 | Phase 4 交付物 · Phase C 渠道专章见 Channel Charter · **不**自动开启 live IO |

---

## 1. 范围

本手册覆盖 **it-ops 单线组织闭环** 的现场/客户沙箱操作：沙箱 fetch、OrgRun、HITL、周报、Fleet 门禁。  
**不覆盖**：生产库任意 SQL、无门控多 Agent、全域企业大脑宣称。

---

## 2. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `AIPLAT_ORG_IO_MODE` | `sandbox` | `sandbox` / `readonly_graph` / `deny`；`live` 走 http_json 白名单，门未齐则 `live_blocked` |
| `AIPLAT_ORG_IO_WRITE` | 关 | 与 `connector.io.allow_write` 双门；默认 dry-run blocked |
| `AIPLAT_ORG_IO_LIVE_UNLOCK` | 关 | 书面解锁意图之一；单独设置 **不** 出站 |
| `AIPLAT_ORG_LIVE_BASE_URL` | 空 | live 基址（须落在 `connector.live.allowed_hosts`） |
| `AIPLAT_ORG_LIVE_TOKEN` | 空 | 可选 Bearer（`auth.type=bearer_env`） |
| `AIPLAT_HOME` | `~/.aiplat` | OrgGoal / Run / memory 存储根 |

---

## 3. 日常操作（沙箱）

1. FDE⑦ 种 it-ops 教学图（或 Path B 入轨）  
2. 打开管理端 **组织试点** `/org/pilot`（或工厂 / FDE 的 Org L5 面板）  
3. 触发 OrgRun（week w1/w2）→ 出现 `needs_hitl`  
4. 批准 / 拒绝 HITL  
5. 查看周报 KPI + 组织记忆检索  
6. 取数规范入口：`POST /api/platform/apps/org/connectors/fetch`（返回可含 `customer_sandbox` stub）  
7. 签收准备（材料齐 ≠ 已签收）：按 [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) §6.5 剧本；试点页看八闸门卡片 / 导出清单；或 `GET …/signoff/prep`  
8. 包就绪核对：`GET …/field-ops/checklist` → `c5_pack_ready`（仍不是双签）  

---

## 3.4 H 波提效（H0–H5 · 不是放权）

入口：管理端 `/org/pilot`。

| 能力 | 接口 | 注意 |
|------|------|------|
| 待批 inbox / 快照 | `GET …/org/approvals/inbox` · `…/approvals/{kind}/{id}/snapshot` | 只读；提案快照含 Diff；批准仍走既有路由 |
| 签收证据包 | `GET …/org/signoff/evidence-pack?format=markdown` | 封面声明不是签字；`m4_claim_allowed=false` |
| 签收准备度 | `GET …/org/signoff/prep` | 八闸门卡片（如何核/责任/跳转）+ `playbook`；`format=markdown` 可导出；从不打开 m4 |
| 可审计收益 | `GET …/org/value/translation?tenant_id=` | 基线：`AIPLAT_HOME/org/tenants/{id}/value_baseline.yaml`；无基线不显示节省人时 |
| 基线试算 | `GET …/org/value/roi-preview` | `simulation=true`；不落盘；不是客户基线 |
| H4 队列自动通过 | `GET …/org/approvals/auto-rules` · `POST …/org/approvals/auto-pass` · `GET …/auto-audit` | 无规则文件时沙箱开；live 拒绝并记次数；只改队列；含沙箱/live 通过率对照；admin 扫与审计；不写活本体；非灰度 |
| H5 技能草稿 | `GET/POST …/org/skills/drafts` · `POST …/drafts/{id}/approve` | 人批才登记市场；不写 SKILL.md；不自动上架 |

**不在本波默认打开**：live IO；打开 `m4_claim_allowed`。显式 `approval_rules.yaml` 的 `enabled: false` 可关掉沙箱 H4。

## 3.5 S 波短板（不是 M4）

| 能力 | 接口 |
|------|------|
| 扫队列 | `POST …/org/approvals/auto-pass`（试点页「扫一遍队列」） |
| 价值基线 | `PUT …/org/value/baseline` |
| 领域模板 | `GET/POST …/org/domain-packs`（动作草稿在 `org/action_drafts`，不登记） |
| 值班记录 | `PUT …/org/signoff/progress`（`m4_claim_allowed` 仍 false） |
| 回滚演练记录 | 同上 `rollback_drill_done`；不自动改 Goal/IO |
| 联合健康度 | `GET …/org/health/joint`（只读；无案例不报覆盖率；无注入不报命中率；含冷库数） |
| 缺口草稿 | `POST …/org/ontology/gap-drafts`（进 K5 账本；不 apply） |
| 缺口 Diff 预览 | `GET …/org/ontology/gap-previews`（只读；确认后才起草） |
| 案例冷库 | `POST …/org/ontology/cases/archive-cold` · `GET …/cases/cold`（移出注入；不删） |

---

## 3.5 Phase C 渠道（C0 冻结 · C2 前只读）

- 首渠：**飞书**（入站 `lark` / 出站 `feishu`，见 Channel Charter §5）  
- 出站通知 env：`AIPLAT_FEISHU_WEBHOOK`（与企微对称，但入站本期不开企微）  
- 入站安全/幂等/映射：见 [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) §7  
- 岗位：`GET /api/platform/apps/org/posts`（DigitalPost，不是 Goal 别名）  
- 入站：`POST /api/platform/apps/org/channels/feishu/events`（须签名；默认拒绝未映射用户）
- 事件预演：`POST /api/platform/apps/org/events/preview` 只接受 `event_preview.yaml` 白名单；干跑；`live_started` 恒 false；不推渠道  
- 用量：`GET /api/platform/apps/org/usage/weekly?domain_id=it-ops&week=`（账本，无价目；失败不阻塞 OrgRun）  
- 签收包：[`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)；`GET /api/platform/apps/org/field-ops/checklist` 看 `c5_pack_ready`（不是 M4）  
- Interface：种子 `workspace_seeds/interfaces/*.yaml`；覆盖 `AIPLAT_HOME/interfaces/{ref}.yaml`；`POST /api/platform/apps/org/interfaces/{domain}/materialize` 只写 home，不写 `connector.live`  

---

## 4. Fleet（W6）

- 默认 `allow_fleet=false`  
- 预检：`GET /api/platform/apps/org/fleet/gate?domain_id=it-ops`  
- 显式打开：`POST /goals/{id}/fleet` body `{"allow": true}` 后仍须 gate 全绿  
- 即使 gate 通过，**Phase 4 执行器仍走 single OrgRun**（舰队 spawn 未产品化）  
- 沙箱演练：`POST /api/platform/apps/org/rehearsals` 只记交接和一次干跑；`fleet_started` 恒 false  
- 强制：`stage_handoff` 五字段；禁止 peer `execute()`

---

## 5. Live 解锁意图（诚实边界）

若需记录「准备对接客户系统」：

1. 填写并保存 [`ORG_L5_LIVE_UNLOCK.md`](./ORG_L5_LIVE_UNLOCK.md)（模板）  
2. `export AIPLAT_ORG_IO_LIVE_UNLOCK=1`  
3. `GET /org/field-ops/live-unlock` → `status=acknowledged` 且 **`live_io_enabled=false`**

**禁止**：在未立项 live adapter 前把 `AIPLAT_ORG_IO_MODE=live` 当作已接通生产。

---

## 6. 值班与回滚

| 项 | 填写 / 动作 |
|----|-------------|
| 值班联系人 | 试点页「记录值班」或 `PUT …/signoff/progress`：`oncall_name` + `oncall_contact` |
| 回滚 Owner | 同上可选 `rollback_owner` |
| 回滚演练 | 按签收包 §5 真做后：试点页「记回滚演练」或 `rollback_drill_done=true`（**不**由按钮自动 pause Goal / 改 IO） |
| 回滚动作（真做时） | 暂停 OrgGoal（`status=paused`）；`AIPLAT_ORG_IO_MODE=deny`。已 apply 提案另有 JSON diff，撤回仍用 YAML 快照 |
| 事故升级 | ________________ |

核对：`GET …/signoff/prep` 闸门 `oncall` / `rollback_drill`；`m4_claim_allowed` 仍恒 false。

---

## 7. 对外话术

- 已完成：单线组织闭环（沙箱）P0–P3 + P4 门禁/手册  
- **未**宣称：OpenAI L5 Organizations 全域达成 / 企业大脑已上线  
- M4 有条件话术仅在客户沙箱真线 + [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) 双签后使用。签收包就绪本身不算签收。
