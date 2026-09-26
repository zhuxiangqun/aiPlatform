# Org L5 Charter — 组织级（单线）企业大脑补齐

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-CHARTER-2026-09` |
| 版本 | **v1.5**（http_json 出站门禁已接线；**Phase C 见独立 Charter**） |
| 日期 | 2026-09-18 |
| 状态 | ☑ P0–P4 · ☑ D4 关闭 · ☐ M4 · ☑ Phase C C1–C5 · ☑ C1.5 YAML（`m4_claim_allowed` 恒 false） |
| 关联方案 | 会话方案「补齐至 L5」；Phase C：[`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) |
| 关联决策 | [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |
| 关联试点 | [`ORG_L5_PILOT_SPEC.md`](./ORG_L5_PILOT_SPEC.md) |
| 关联开工 | [`ORG_L5_PHASE0_KICKOFF_CHECKLIST.md`](./ORG_L5_PHASE0_KICKOFF_CHECKLIST.md) |
| 关联 Phase C | [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md)（渠道入站 · Interface · 岗位） |
| 关联 V 波 | [`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md)（V0–V5 已落地；不替代 M4） |
| 关联 E 波 | [`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md)（E2 已落地；不替代 M4） |
| 关联 H 波 | [`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md)（H0–H5 已落地；H4 沙箱开、live 拒；H5 人批才登记；提效不放权） |
| 与 FDE 关系 | **并行不替代**；FDE 管现场控制台边界；Org L5 管「单业务线组织任务周闭环」 |

---

## 0. 一句话

把 aiPlat 从 **L3 Agents（代执行）+ 企业大脑原型话术**，补齐到 **可验收的「单条业务线组织级闭环」**（有条件称组织级 L5）；**不**一次宣称全域企业大脑。

---

## 1. 名词对齐（防混号）

| 名称 | 含义 | 本文是否指它 |
|------|------|:------------:|
| OpenAI L5 Organizations | AI 能执行复杂**组织**任务 | ✅ |
| 生产角色「企业大脑」 | 表中 L5 角色 | ✅ 目标角色；达标前称「原型 / 单线」 |
| 工厂「L5 发布流水线」 | `release_engine` 金丝雀发布 | ❌ **不是**本文 |
| Action 阶梯 Lv4 / P2-L5 | Action 自动闭环门 | ❌ 仅复用，不混称 |

---

## 2. L5 验收定义（必须同时满足）

| # | 条件 | 关闭证据 |
|---|------|----------|
| A | 一条真实业务线上，组织任务可 **≥2 个模拟周次** 复跑 | OrgRun 日志 + 周报 API |
| B | **定位 → 受控取数/写回 → Action 过闸 → 审计可回放** | fetch/write + ActionStore |
| C | **OrgGoal + SLA + 例外 HITL + 失败归因** | Pilot Spec 状态机冒烟 |
| D | **业务代理 KPI** 与动作挂钩（非材料补齐率） | weekly 报告三指标 |
| E | 对外话术诚实：未达标不称全域 L5 / 企业大脑已达成 | CAPABILITIES + PPT B 节同步 |

**未满足 A–E 时**：对外仍为 **L3 + 企业大脑原型**。

---

## 3. 非目标（否定清单）

1. 星邺式补齐率 / 准确率 / 人天 KPI  
2. 一体化数据治理套件产品化  
3. 默认放开无门控多 Agent 舰队  
4. `governance/locate` 内直连客户库任意 SQL  
5. 静默改 TBox / 绕过 PolicyGate / 无审计写生产  
6. 以 `fde-delivery` 自指会话冒充「企业业务组织闭环」  
7. 并行铺满 it-ops + data-gov + lock + retail 四线  

---

## 4. 工作流与阶段（摘要）

| 工作流 | 内容 | 阶段 |
|--------|------|------|
| W2 Connector I/O | locate → fetch；写回只经 Action | Phase 1 |
| W1 Org Runtime | OrgGoal / OrgRun / 分解 | Phase 2 |
| W4 Exception Policy | 例行自动 / 例外 HITL | Phase 2 |
| W3 Org Memory | Run 摘要 / 例外判例检索 | Phase 3 |
| W5 Outcome Eval | KPI 周报 | Phase 3 |
| W6 Fleet Gate | 白名单 multi + handoff 硬门 | Phase 4 |
| W7 Field Ops | 客户沙箱/真线 Runbook | Phase 4 |

依赖：`W2 → W4 → W5`；`W1` 与 W2 可部分并行但 **OrgRun 调真 I/O 前 W2 须绿**；`W6` 最后。

---

## 5. 已决决策（详见 Decision Record v1.0）

| ID | 决议 | 状态 |
|----|------|------|
| D1 | 主试点域 = **it-ops** | ☑ 已决 2026-09-18 |
| D2 | KPI = MTTA / 根因标注率 / 例外占比 | ☑ 已决 |
| D3 | Phase 1–3 **禁止**写非沙箱生产系统 | ☑ 已决 |
| D4 | 新模块 **`platform/apps/org`**（不塞进 FDE 巨型页） | ☑ 已决 |
| D5 | data-gov **只读 fetch** 薄切片（无第二条 OrgGoal） | ☑ 已决 |

---

## 6. 复用底座（禁止重建）

- Ontology：YAML + `VersionedOntologyStore` + `GraphIndex` + Action YAML  
- 执行：`AsyncActionRegistry` / PolicyGate / HITL / Action 阶梯  
- 入轨：`abox_connector`（webhook / `table_map`）— **扩展** fetch/write  
- 治理竖切：`governance-loop` / `quality` / `locate`  
- 学习：`ontology_case_learning`（evolve 仍提案门）  
- 编排：Pipeline + `stage_handoff`（默认 single）  
- 审计：`audit_schema.v1` + ActionStore  
- 现场：FDE 契约体系（控制台边界不变）

---

## 7. 归属与接口铁律

| 规则 | 要求 |
|------|------|
| 配置驱动 | 域差异进 seed YAML / OrgGoal 配置；harness **禁** `if domain_id == "it-ops"` 业务分叉 |
| HTTP | `aiPlat-platform/apps/org/api/` |
| 无 HTTP 逻辑 | `aiPlat-core/core/apps/org/service/`（或暂挂 `fde/service` 仅 Phase 1 薄扩展时须在决策记录注明迁移债） |
| 门面 | 一律 `CoreFacade` |
| 文档同步 | 新公共符号 → `AIPLAT_CAPABILITIES.md` + `capability_registry.yaml` |
| 成本阶梯 | 优先扩展 connector + Pipeline；Org Runtime 须有试点 Goal 消费者 |

---

## 8. 里程碑话术

| 里程碑 | 对内 | 对外可说 |
|--------|------|----------|
| M0 Charter+决策签字 | P0 生效 | 仍 L3 + 原型 |
| M1 W2 绿 | 定位+受控取数 | 「本体定位+受控取数竖切」 |
| M2 双周 OrgRun 绿 | 组织任务闭环 | 「单域组织任务闭环（试点）」 |
| M3 KPI 周报绿 | 业务后果 | 「带业务后果的组织 Agent」 |
| M4 客户沙箱/真线 | W7 | **有条件**称「组织级（单线）L5」 |
| 全域多线 | 未立项 | **不称**企业大脑已达成 |

---

## 9. 粗工期（一人全职量级）

| 阶段 | 人日 |
|------|------|
| P0 立项文档 | 3–5（本文已覆盖大部分） |
| P1 W2 | 8–12 |
| P2 W1+W4 | 12–18 |
| P3 W3+W5 | 8–12 |
| P4 W6 平台侧 | 5–10 |
| P4 客户侧 | 另计 |

---

## 10. Go / No-Go

| 项 | 填写 |
|----|------|
| 是否以本 Charter 为基线继续？ | ☑ **Go** |
| 条件（若有） | Phase 1 须 Kickoff §F 另宣布 |
| 签字（架构 / 产品） | 会话确认 |
| 日期 | 2026-09-18 |

**P0 生效**：☑ 2026-09-18（五问已决 + Kickoff §E）。  
**Phase 1 开工条件**：P0 已生效；宣布 §F 后方可改码。
