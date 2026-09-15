# FDE 工作台能力台账（模板）

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-LEDGER-2026-09` |
| 版本 | v0.1 |
| 关联 | [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md)（已填实例）· [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) · [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) |
| 维护人 | Oliver Zhu |
| 更新节奏 | 每 Phase 结束更新；重大变更即时更新 |
| 状态 | ☑ 草稿 · ☐ 评审中 · ☐ 生效 |

> **已填实例**见同目录 `FDE_WORKBENCH_CAPABILITY_LEDGER.md`（按本模板 §2/§3/§4 填充）。本文件保持空白结构，供复制开新周期。

---

## 0. 使用说明

1. 台账是**可审计的能力清单**，不是宣传页。每条能力必须有：成熟度、证据、消费方、缺口、Owner。
2. 成熟度枚举固定：`production` / `pilot` / `demo` / `stub-hidden` / `not-implemented` / `deprecated`。
3. 证据类型固定：`test` / `benchmark` / `contract` / `scan` / `manual` / `none`。
4. 证据必须可点进对应文件或报告；无证据写 `none`，不得留空。
5. 每 Phase 结束，由记录人更新；逾期两周未更新，标记为“停滞”。

---

## 1. 成熟度定义

| 成熟度 | 含义 | 允许的对外表述 |
|--------|------|----------------|
| `production` | 有 e2e 测试 / 压测 / 契约勾选，可演示可审计 | 可用 |
| `pilot` | 主路径可跑，边界条件未全测 | 谨慎使用，标注范围 |
| `demo` | 能点通，依赖种子/模板，非通用 | 仅演示，不承诺 |
| `stub-hidden` | 无真实数据源，已隐藏或诚实横幅 | 不得对外称“已接线” |
| `not-implemented` | 契约已定义，代码未落地 | 不得出现在 UI |
| `deprecated` | 已废弃，保留兼容或待清理 | 标注废弃日 |

---

## 2. Tab 级能力台账

| ID | Tab | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner | Phase |
|----|-----|------|--------|------|--------|----------|-------|-------|
| T01 | ① 业务认知 | 客户 Profile CRUD | _TBD_ | _TBD_ | Tab① | _…_ | _TBD_ | 0 |
| T02 | ① 业务认知 | 行业推断 | _TBD_ | _TBD_ | Tab① | _…_ | _TBD_ | 0 |
| T03 | ② 评估域 | 域成熟度 / 能力面 | _TBD_ | _TBD_ | Tab② | _…_ | _TBD_ | 0 |
| T04 | ③ 问题重构 | field_assessment | _TBD_ | _TBD_ | Tab③ | _…_ | _TBD_ | 0 |
| T05 | ③ 问题重构 | 多轮澄清对话 | _TBD_ | _TBD_ | Tab③ | _…_ | _TBD_ | 1 |
| T06 | ④ 验证价值 | 模板 / POC 切换 | _TBD_ | _TBD_ | Tab④ | _…_ | _TBD_ | 0 |
| T07 | ⑤ 交付 | 平台离线包 | _TBD_ | _TBD_ | Tab⑤ | _…_ | _TBD_ | 0 |
| T08 | ⑤ 交付 | 交付 session + HITL | _TBD_ | _TBD_ | Tab⑤ | _…_ | _TBD_ | 1 |
| T09 | ⑤ 交付 | Builder 链接 + Eval | _TBD_ | _TBD_ | Tab⑤ | _…_ | _TBD_ | 3 |
| T10 | ⑥ 护栏 | canary 状态 / 回滚 | _TBD_ | _TBD_ | Tab⑥ | _…_ | _TBD_ | 0 |
| T11 | ⑥b 预检 | 安全 dry-run | _TBD_ | _TBD_ | Tab⑥b | _…_ | _TBD_ | 4A |
| T12 | ⑦ 验收 | 签收硬门 | _TBD_ | _TBD_ | Tab⑦ | _…_ | _TBD_ | 4A |
| T13 | ⑦ 验收 | 客户 Action 执行 | _TBD_ | _TBD_ | Tab⑦ | _…_ | _TBD_ | 2 |
| T14 | ⑧ 运营 | Evolve 队列 | _TBD_ | _TBD_ | Tab⑧ | _…_ | _TBD_ | 4B |
| T15 | ⑧ 运营 | 受控 apply / rollback | _TBD_ | _TBD_ | Tab⑧ | _…_ | _TBD_ | 4B |
| T16 | ⑧ 运营 | D6 反向指标 | _TBD_ | _TBD_ | Tab⑧ | _…_ | _TBD_ | 4B |
| T17 | ⑨ 快速认知 | 48h 行业认知 | _TBD_ | _TBD_ | Tab⑨ | _…_ | _TBD_ | 0 |

---

## 3. 竖切级能力台账

| ID | 竖切 | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner | Phase |
|----|------|------|--------|------|--------|----------|-------|-------|
| V01 | Phase 0 | API 统一 / 否定清单 | _TBD_ | _TBD_ | 全站 | _…_ | _TBD_ | 0 |
| V02 | Phase 1 | 交付 session + audit 冻结 | _TBD_ | _TBD_ | Tab⑤ | _…_ | _TBD_ | 1 |
| V03 | Phase 2 | lock-service accept_order | _TBD_ | _TBD_ | Tab⑦ | _…_ | _TBD_ | 2 |
| V04 | Phase 3 | Builder 产物链接 | _TBD_ | _TBD_ | Tab⑤ | _…_ | _TBD_ | 3 |
| V05 | Phase 4A | 安全预检 + 签收硬门 | _TBD_ | _TBD_ | Tab⑥b/⑦ | _…_ | _TBD_ | 4A |
| V06 | Phase 4B | Evolve 受控应用 | _TBD_ | _TBD_ | Tab⑧ | _…_ | _TBD_ | 4B |
| V07 | Phase 5 | 第二客户域可复制 | _TBD_ | _TBD_ | Tab①/② | _…_ | _TBD_ | 5 |

---

## 4. 执行核级能力台账

| ID | 组件 | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner |
|----|------|------|--------|------|--------|----------|-------|
| E01 | AsyncActionRegistry | 注册校验 | _TBD_ | _TBD_ | 全站 | _…_ | _TBD_ |
| E02 | AsyncActionRegistry | 7 步执行 + audit | _TBD_ | _TBD_ | 全站 | _…_ | _TBD_ |
| E03 | WorkbenchRuntimeGuard | 规则 4/6/9 | _TBD_ | _TBD_ | 工作台 | _…_ | _TBD_ |
| E04 | PolicyGate | 三态决策 | _TBD_ | _TBD_ | Registry | _…_ | _TBD_ |
| E05 | HITL / pending_approvals | 审批 + 幂等恢复 | _TBD_ | _TBD_ | Registry | _…_ | _TBD_ |
| E06 | ActionStore.action_audit | audit.v1 字段 | _TBD_ | _TBD_ | 全站 | _…_ | _TBD_ |
| E07 | DomainRouter | 唯一域解析 | _TBD_ | _TBD_ | 全站 | _…_ | _TBD_ |
| E08 | architecture_guard | 5 条 FDE 规则 | _TBD_ | _TBD_ | CI | _…_ | _TBD_ |
| E09 | preflight Facade | dry-run + evidence | _TBD_ | _TBD_ | Tab⑥b | _…_ | _TBD_ |

---

## 5. KPI 数据源表（⑧ Tab 专用）

| KPI | 数据源 | 状态 | 替代方案 | Owner |
|-----|--------|------|----------|-------|
| 质量分 | Quality Bus | _TBD_ | _…_ | _TBD_ |
| Action 成功率 | ActionStore.action_audit | _TBD_ | _…_ | _TBD_ |
| canary 状态 | canary API | _TBD_ | _…_ | _TBD_ |
| Evolve reject_rate | evolve_proposal | _TBD_ | _…_ | _TBD_ |
| Evolve rollback_rate | evolve_applied | _TBD_ | _…_ | _TBD_ |
| Evolve mean_survival | evolve_observation | _TBD_ | _…_ | _TBD_ |
| 待审抽取 | extraction queue | _TBD_ | _…_ | _TBD_ |

---

## 6. 死 API / 无消费方清单

| API | 原消费方 | 当前状态 | 处理建议 | Owner |
|-----|----------|----------|----------|-------|
| _…_ | _…_ | 无消费方 | 归档 / 合并 / 删除 | _TBD_ |

---

## 7. 更新记录

| 日期 | 更新人 | 变更 |
|------|--------|------|
| 2026-09-15 | Oliver Zhu | 入库模板；实例见 `FDE_WORKBENCH_CAPABILITY_LEDGER.md` |
