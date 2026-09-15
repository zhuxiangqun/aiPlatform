# AI FDE 半步：受控应用闭环设计

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-AIFDE-LOOP-2026-09` |
| 版本 | v0.2 |
| 状态 | 设计稿；**对照半步已合代码后修订** |
| 关联 | [`fde-workbench-evolution-plan.md`](../architecture/plans/fde-workbench-evolution-plan.md) Phase 4B · [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) D6 · [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md) T15/T16/V06 · `audit_schema.v1.yaml` |
| 定位 | 把 Evolve 从「能排队」推进到「过审后可受控应用 + 反向 KPI + 观测窗」 |
| 设计作者 | Oliver Zhu |

---

## 0. 目标与非目标

**目标：**
- Agent 可提出配置变更提案，经白名单校验 + HITL 后受控应用。
- 应用后进入观测窗，反向 KPI 可见。
- 异常时可回滚到上一稳定版本。
- 全程审计，不静默写 ABox / Ontology。

**非目标：**
- 任意改配置 / 写库。
- 自动合并到主分支。
- 替代人审。
- 用 pass_rate 当唯一 KPI。

---

## 0.1 现状对照（代码事实，2026-09-15）

| 设计项 | 半步已有 | 缺口（本设计要补） |
|--------|----------|-------------------|
| 白名单 + evaluate/enqueue | ✅ `evolve_proposal_gate.py` | 与设计 YAML 键表对齐文档化 |
| HITL approve/reject | ✅ | — |
| apply → `fde_evolve_applied_config.json` + before snapshot | ✅ | 观测窗 `observation_until` 字段 |
| 人工 rollback + survival 秒 | ✅ | 自动/阈值触发；canary/Quality 联动 |
| D6 reject/rollback/mean_survival API+UI | ✅ 计数 | 观测窗结束也记存活；quality_score 序列 |
| 状态机 `observing` / `stable` | ❌ 现为 applied/rolled_back | 扩展状态 |
| `platform_action:…:evolve_apply` 经 Registry | ❌ 现为 FDE service 直写文件 | 可选收敛（避免第二执行路径） |
| `evolve_observation` 表/文件 | ❌ 仅 metrics 计数 JSON | 按设计落观测记录 |
| 自动回滚 | ❌ | §5 |

**结论：** 半步已越过「只排队」；本设计把 V06/T15/T16 从 `pilot` → `production`。

---

## 1. 状态机

```
draft
  → evaluated          # 白名单 + Eval 门
  → enqueued           # 进入 HITL 队列
  → approved           # 人审通过
  → applied            # 受控应用
  → observing          # 观测窗
  → stable             # 存活
  → rolled_back        # 回滚
  → closed

rejected → closed
evaluation_failed → closed
apply_failed → rolled_back
```

**终态：** `stable` / `rolled_back` / `closed` / `rejected` / `evaluation_failed`。

**与现状映射：** `auto_recorded`≈evaluated 旁路；`pending_hitl`≈enqueued；`approved`/`applied`/`rolled_back`/`rejected` 已有；新增 `observing`/`stable`。

---

## 2. 数据模型

### 2.1 `evolve_proposal`

| 字段 | 类型 | 说明 |
|------|------|------|
| proposal_id | TEXT PK | ULID |
| tenant_id | TEXT | |
| domain_id | TEXT | |
| action_namespace | TEXT | platform_action |
| target_config_key | TEXT | 白名单键 |
| current_value | TEXT | JSON |
| proposed_value | TEXT | JSON |
| rationale | TEXT | Agent 理由 |
| eval_report_ref | TEXT | Eval 报告 |
| status | TEXT | 状态机 |
| created_at | TEXT | |
| decided_at | TEXT | |
| approver_id | TEXT | |
| reject_reason | TEXT | |

> 现状：JSON 文件队列 `$AIPLAT_HOME/fde_evolve_proposals/`。迁移到表可选；**先扩 JSON 字段再表化**，避免双写。

### 2.2 `evolve_applied`

| 字段 | 类型 | 说明 |
|------|------|------|
| applied_id | TEXT PK | ULID |
| proposal_id | TEXT FK | |
| config_patch_ref | TEXT | `fde_evolve_applied_config.json` |
| before_snapshot | TEXT | JSON（现状 `applied_snapshot`） |
| after_snapshot | TEXT | JSON |
| applied_at | TEXT | |
| applied_by | TEXT | |
| rollback_ref | TEXT | |
| observation_until | TEXT | 观测窗结束 |

### 2.3 `evolve_observation`

| 字段 | 类型 | 说明 |
|------|------|------|
| observation_id | TEXT PK | |
| applied_id | TEXT FK | |
| metric_name | TEXT | reject_rate / rollback_rate / mean_survival / quality_score |
| metric_value | REAL | |
| baseline_value | REAL | |
| window_start | TEXT | |
| window_end | TEXT | |
| verdict | TEXT | ok / warn / breach |

### 2.4 审计

每次状态迁移写 `approval_event`（**现状缺口：无独立轨迹表**）；每次 apply / rollback 写 `action_audit`，建议 action 名：
- `platform_action:fde-delivery:evolve_apply`
- `platform_action:fde-delivery:evolve_rollback`

> 半步可继续 service 路径，但须在台账标 `pilot`；升 `production` 前至少二选一：Registry 执行 **或** 等效 audit.v1 嵌入。

---

## 3. 白名单与 apply 规则

### 3.1 允许键

```yaml
allowed_keys:
  - "prompt_extra.*"
  - "model_config.temperature"
  - "model_config.max_tokens"
  - "retry_policy.max_retries"
  - "cache_ttl_seconds"
```

### 3.2 禁止键

```yaml
forbidden_keys:
  - "policy_gate.*"
  - "auth.*"
  - "database.*"
  - "sandbox.*"
  - "audit.*"
```

### 3.3 apply 实现

- 只生成 `fde_evolve_applied_config.json`，不直接改运行配置。
- 受控加载器读取该文件，重启或热加载生效。
- 不写 ABox / Ontology。
- 每次 apply 前后写 `before_snapshot` / `after_snapshot`。

---

## 4. 反向 KPI

| 指标 | 定义 | 用途 |
|------|------|------|
| reject_rate | rejected / (approved + rejected) | 规则是否回写 |
| rollback_rate | rolled_back / applied | 批准质量 |
| mean_survival | 平均 applied → rolled_back **或观测窗结束** | 真实稳定性 |
| pass_rate | approved / total | **仅仪表盘参考，不得单独作 KPI** |

---

## 5. 回滚触发（RACI）

| 触发条件 | 动作 | 责任人 |
|----------|------|--------|
| 观测窗内 quality_score 下降 > 阈值 | 自动回滚 | 系统 |
| rollback_rate 连续 N 次超阈值 | 自动回滚 + 暂停 Evolve | 系统 + 人审 |
| canary 异常 | 自动回滚 | 系统 |
| 人审手动回滚 | 回滚 | FDE |
| 存活时间 < 最小阈值 | 标记为 unstable，进入人审 | 系统 |

**半步默认：** 仅「人审手动回滚」已接线；其余为 Phase 4B+ 实施项。

---

## 6. 与现有组件对接

| 组件 | 用途 |
|------|------|
| ActionRegistry | apply / rollback 作为 platform_action（目标态） |
| PolicyGate | apply 前置决策 |
| HITL / pending_approvals | approved 前置（客户 Action 已有；Evolve 现用文件队列） |
| ActionStore.action_audit | 审计 |
| Eval 门 | evaluated 前置（`evolve_proposal` + change_surface） |
| canary API | 观测窗数据源 |
| Quality Bus | quality_score 数据源（⑧ 现未挂） |

---

## 7. UI（⑧ Tab）

- Evolve 队列：proposal 列表 + 状态 + 一键审。（✅）
- Applied 列表：applied_id + 观测窗 + 指标 + 回滚按钮。（部分：回滚有；观测窗 UI 缺）
- 反向 KPI 卡：reject_rate / rollback_rate / mean_survival。（✅）
- pass_rate 仅小字参考。（✅ 文案）

---

## 8. 验收标准

- [ ] 至少 1 个提案走完 draft → … → applied → **observing** → **stable**。
- [ ] 至少 1 次回滚演练成功。（半步人工路径可先勾）
- [ ] 反向 KPI 在 UI 可见，数据源真实。（半步计数可先勾；观测窗质量分待勾）
- [ ] 无静默写 ABox / Ontology。
- [ ] 审计记录完整，可回放。
- [ ] pass_rate 未单独作 KPI。
- [ ] 台账 T15/T16/V06 成熟度升为 `production`。

---

## 9. 落地顺序

1. ~~白名单校验 + proposal 队列~~（半步已有）
2. ~~HITL 队列接通~~
3. ~~apply 生成 config patch~~
4. **观测窗 + observation 记录 + observation_until**（下一步）
5. **回滚触发（canary / quality 阈值）**
6. UI Applied 列表 + 观测态；台账升级

---

## 10. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Agent 改到白名单外 | 注册校验 + runtime 校验 |
| apply 后无观测 | 观测窗强制 |
| 回滚失败 | 回滚演练 + 双版本快照 |
| pass_rate 变 KPI | UI 声明 + 决策记录 D6 |
| 静默写 ABox | 禁止 + 守卫 |
| 双执行路径（service vs Registry） | 台账标 pilot 直至收敛 |

---

## 11. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-09-14 | 初稿（设计） |
| v0.2 | 2026-09-15 | 入库；增 §0.1 现状对照；落地顺序标已完成项 |
