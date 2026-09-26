# M4 现场签收包（Phase C5）· it-ops 签收准备

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-M4-SIGNOFF-PACK-2026-09` |
| 版本 | **v1.2** |
| 日期 | 2026-09-20 |
| 状态 | ☑ **签收包就绪** · ☐ 客户未签字 · ☐ 不得称 L5 |
| 关联 | [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md) · [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) · [`ORG_L5_LIVE_UNLOCK.md`](./ORG_L5_LIVE_UNLOCK.md) · [`ORG_L5_PILOT_SPEC.md`](./ORG_L5_PILOT_SPEC.md) |

**本文不是签收。** `c5_pack_ready=true` 与 `GET …/org/signoff/prep` 的准备度只表示平台侧材料可送审。`m4_claim_allowed` 恒为 `false`。

---

## 1. 平台侧已齐（自动项）

| 项 | 关闭证据 |
|----|----------|
| 运行手册 | `docs/contracts/ORG_L5_RUNBOOK.md` |
| Phase C 契约 | `docs/contracts/ORG_CHANNEL_INTERFACE_CHARTER.md` |
| 本签收包 | 本文 |
| IO 默认沙箱 | `AIPLAT_ORG_IO_MODE` 非 `live` |
| Fleet 默认拒绝 | `allow_fleet=false` |
| InterfaceSpec | `workspace_seeds/interfaces/it-ops.monitor.fetch.yaml`；`enabled=false` |
| DigitalPost | `it-ops.alert.pilot` 绑定 `goal-it-ops-alert-sla` |
| 飞书单渠 | 确认门开；第二渠道关闭；密钥未配不算失败 |
| 用量账本 | `GET /org/usage/weekly`，`billing=null` |

机器可读：`field_ops_checklist()["c5_pack_ready"]` · `GET /api/platform/apps/org/signoff/prep`。

---

## 2. it-ops 验收标准（可联调 → 可送审）

送客户审阅前，下列项应全部为真。仍不等于双签。

| # | 标准 | 如何核 |
|---|------|--------|
| A1 | 平台签收包齐套 | `GET …/field-ops/checklist` → `c5_pack_ready=true` |
| A2 | 至少 1 次 OrgRun，周报可出数 | `GET …/goals/goal-it-ops-alert-sla/weekly` → `run_count≥1` |
| A3 | 三 KPI 可看（可为空值，不可伪造） | 同上：`mtta_seconds` / `root_cause_rate` / `exception_ratio`；准备度闸门 `kpis_visible` |
| A4 | 待批快照可打开 | `GET …/approvals/inbox`；提案快照含 Diff；准备度闸门 `inbox_readable` |
| A5 | 证据包可导出 | 试点页「导出签收证据」或 `GET …/signoff/evidence-pack?format=markdown` |
| A6 | 值班联系人已记 | `PUT …/signoff/progress` 后 checklist `oncall=true` |
| A7 | 价值基线已填（才显示节省人时） | 试点页写入基线；无基线不编数字 |
| A8 | 回滚演练做过一遍 | 试点页「记回滚演练」或 `PUT …/signoff/progress` 设 `rollback_drill_done=true`；准备度闸门 `rollback_drill` |

准备度汇总：`GET …/org/signoff/prep` → `prep_score`（八闸门）；`?format=markdown` 导出清单。`prep_complete` 只表示材料齐，**从不**把 `m4_claim_allowed` 设为 true。

---

## 3. 证据包用法

1. 身份：请求头带 `X-AIPLAT-ROLE`（operator/admin 等已映射角色）。
2. 导出：`GET /api/platform/apps/org/signoff/evidence-pack?domain_id=it-ops&goal_id=goal-it-ops-alert-sla&format=markdown`  
   或试点页「导出签收证据」。
3. 封面固定声明：**本包不是签字。m4_claim_allowed=false。客户尚未签收。**
4. 代表性 trace ≤ 5；缺步写「未发生」，不补假链路。
5. `billing` 恒为 null。

---

## 4. 价值基线填写引导

| 字段 | 含义 | 建议取数 |
|------|------|----------|
| `baseline_minutes_per_incident` | 历史单次告警人工处理分钟 | 近 4–8 周均值；没有就先估一个并标注来源 |
| `baseline_mtta_seconds` | 历史 MTTA（秒） | 监控/值班台账；没有就不填，平台只显示平台 KPI |

写入：`PUT …/org/value/baseline`（租户隔离）或试点页「写入基线」。  
试算（不落盘）：`GET …/org/value/roi-preview?trial_minutes_per_incident=&trial_mtta_seconds=` 或试点页「试算」。`baseline_source=what_if`，**不是**客户基线。  
**无基线 → 不显示节省人时。** 不得用行业均值冒充客户基线。

---

## 5. 回滚演练记录（模板）

| 步骤 | 动作 | 结果 | 日期 |
|------|------|------|------|
| 1 | 暂停 OrgGoal（`status=paused`） | ☐ | |
| 2 | `AIPLAT_ORG_IO_MODE=deny` | ☐ | |
| 3 | 确认无新 live 出站 | ☐ | |
| 4 | 恢复沙箱模式并记值班联系人 | ☐ | |

已 apply 的提案回滚另走 YAML 快照路径；无快照旧边不撤。

现场勾选后：`PUT …/signoff/progress` `{"rollback_drill_done": true}`（或试点页按钮）。只记结果，**不**由按钮自动 pause Goal 或改 `AIPLAT_ORG_IO_MODE`。

---

## 6. 客户线仍须人工（不计入 c5_pack_ready）

| 项 | 谁填 | 完成前 |
|----|------|--------|
| 值班 / 回滚联系人 | 试点 Owner | 清单 `oncall` 保持 false 直至写入 |
| Live 解锁书面 + env | 客户环境 Owner | `live_io_enabled` 仍为 false |
| 客户监控真线（非 stub） | 客户 | stub ≠ 生产 |
| 双签 | 客户 + 平台 | 下表勾选后，才允许单线「有条件 L5」话术 |

| 签收项 | 客户 | 平台 | 日期 |
|--------|:----:|:----:|------|
| 沙箱 OrgRun + HITL 走过一轮 | ☐ | ☐ | |
| 飞书入站签名与身份映射已配 | ☐ | ☐ | |
| Interface 白名单主机与基址已核 | ☐ | ☐ | |
| 周报三 KPI 看过 | ☐ | ☐ | |
| 回滚（暂停 Goal + `IO_MODE=deny`）演练 | ☐ | ☐ | |
| 同意对外只称单线、不称全域 | ☐ | ☐ | |

---

## 6.5 签收剧本（到送审；双签仍人工）

机器可读：`GET …/org/signoff/prep` → `playbook`；试点页闸门卡片可跳转对应区。

| 步 | 客户看什么 | 客户批什么 | 闸门 |
|----|------------|------------|------|
| 1 开跑并看周报 | 岗位开跑 → 周报三 KPI（可空） | 确认跑通一轮，不签 L5 | A2 A3 |
| 2 待批可打开 | inbox + 提案 Diff | 确认人批路径可读；本步不写活本体 | A4 |
| 3 基线与收益 | 试算 → 写入基线 → 价值卡 | 确认数字来自客户基线，非行业模板 | A7 |
| 4 值班与回滚 | 值班联系人 + 演练记录 | 确认演练做过；按钮只记结果 | A6 A8 |
| 5 导出送审 | 证据包 + 准备度清单 | 内部审计可看；材料齐 ≠ 已签收 | A1 A5 |
| 6 双签 | 上表勾选 | 客户+平台双签后才允许有条件 L5 话术 | 人工；程序不打开 m4 |

---

## 7. 话术

**材料齐、尚未双签时，对外只说：**  
协作入口可触发 it-ops 组织任务（试点）；接口已登记且默认关闭；it-ops 竖切可联调；交点是人批闸门；客户尚未签收。

**不可说：** 全域数字员工、L5 已达成、超级组织、已按 Token 售卖、live 已灰度自动合并。

辅助审阅（仍不签收）：缺口 Diff 预览、H1 提案 Diff、案例冷库、沙箱/live 通过率只读对照。
