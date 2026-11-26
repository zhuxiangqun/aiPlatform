---
doc_type: Standard
status: active
authority: canonical
doc_id: EVAL_SYS_V10_WHITEPAPER
purpose: 定义 aiPlat 评测系统 v1.0 目标架构与强制要求
scope_in: 评测对象、协议、入口唯一性、准确性支柱、门禁、符合性认证（附录 N）
scope_out: 具体实现状态声明、业务域内容、非评测子系统、A3 生产 SLA 细节
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat 评测系统技术白皮书 v1.0

> **版本**：v1.0.0 · 2026-11-26  
> **状态**：已批准（`status: active`）；**2026-12-01 生效**  
> **性质**：技术标准（`authority: canonical`）  
> **构成**：正文 + 规范性附录 + `schemas/`（标准包，三者同版本）  
> **批准**：`ADR-EVAL-SYS-v1.0-2026-11-26.md`  
> **诚实边界**：标准批准 ≠ 实现 certified；不宣称无范围、无证据的「更准」。

---

## 标准声明

### 效力

- **当前**：草案，供评审与实施计划引用；
- **批准后**：须记录 Architecture Review / Security / Product（作者不得单独批准）；
- **实现符合性**：必须按第 16 章单独认证，不能以「读过标准」代替。

### 构成

标准包 = **正文 + 规范性附录 + `schemas/`**。附录中的字段名、错误码、符合性清单与正文同等效力。

### 冲突

- 本标准与实现文档冲突：以本标准（批准后）为准；
- 本标准与代码冲突：代码是当前事实，须 ADR 修正标准或实现；
- 无法满足：走 ADR 例外，记录范围、期限与补偿。

---

## 文档地图

| 正文 | 内容 | 对应附录 |
|---|---|---|
| 0–2 | 一页概览、痛点、原则 | — |
| 3 | 业务/技术架构 | A |
| 4 | 评测对象与协议 | B |
| 5 | 唯一入口与调用契约 | C |
| 6 | 准确性五支柱 | D/O |
| 7 | Case Pack / Gold Set | E |
| 8 | Judge / 校准 | F/O |
| 9 | 门禁与回归 | G |
| 10 | 评测中心 UX | H |
| 11 | 安全与多租户 | I |
| 12 | 独立服务边界（A3） | J |
| 13 | 质量与声明边界 | O |
| 14 | 路线图 | — |
| 15 | 迁移与采用 | — |
| 16 | 符合性认证 | N |
| 17 | 实施参考（非规范） | — |
| 18 | 结论 | — |

> 阅读顺序：决策者 0–3、13–16、18；架构师全篇；工程师 4–12 + 附录。

---

## 0. 先看一页

评测系统要解决的不是「又一个跑分页面」，而是：

> **同一套契约下，能证明对不对、为什么错、该改什么、能不能挡住回归。**

失败模式：

- **入口不唯一**：多条 API/页面各跑各的，金标接错路径；
- **有协议无准确**：交换格式有了，但无 gold / 校准 / 方差；
- **有分数无归因**：一个总分回答不了「升模型还是改 SOP」；
- **无证据宣称更准**：无人工标签却对外说 accuracy。

aiPlat 评测系统目标链路：

> **对象契约 → 唯一执行入口 → 可复现金标 → Judge 校准 → 门禁 → 可归因报告 →（可选）独立服务。**

---

## 1. 七类痛点（摘要）

1. 多入口并行（platform eval / core evaluation / kb-eval / prompts eval）；  
2. Gold set 缺失或不可复现；  
3. Judge 未校准仍当真理；  
4. 门禁与评测脱节；  
5. UI 分散，无评测中心；  
6. 把 FDE 客户验收误当成评测；  
7. 把 A3 进程拆分当成 v1 前置。

---

## 2. 三条原则

| # | 原则 |
|---|---|
| 1 | **先准再中心**：准确性与唯一 API 先于评测中心 UI / 独立服务 |
| 2 | **无标签不宣称 accuracy** | 单人复核可跑门禁，但不报 κ / 不对外 accuracy |
| 3 | **评测 ≠ 验收**：评测挡回归；FDE 签收挡交付；二者不得互换入口 |

---

## 3. 架构

### 3.1 逻辑分层

```text
Experience     评测中心 / 诊断页（redirect）
Contract       Evaluation Plan / Case Pack / Protocol
Execution      唯一 Runner（经 CoreFacade）
Evidence       Trace / 报告 / 金标指纹
Governance     Gate / Policy / 租户隔离
```

### 3.2 入口唯一（MUST）

- Canonical HTTP：`/api/platform/apps/eval`；
- Core 旧路径仅允许 shim，禁止新能力绕过；
- 所有金标与门禁必须调用同一 Runner 契约（附录 C）。

---

## 4. 评测对象

v1.0 **MUST** 支持：

- Agent；
- Skill；

v1.0 **SHOULD** 支持：

- Tool / MCP（与外援互通标准对齐）；
- Prompt / Workflow（显式 Plan，禁止静默空跑）。

对象契约见附录 B；禁止无 `sample_manifest` 的 Plan 冒充执行清单。

---

## 5. 唯一入口与调用契约

- Plan 是选题真相；`compile-plan` 失败 MUST fail closed；
- `sample_manifest` 是唯一执行清单；空/缺 MUST 失败；
- 指纹分离：`plan_id` / `manifest_hash` / `execution_fingerprint`；
- 结果 MUST 可归因到维度分 + 证据引用（附录 D）。

---

## 6. 准确性五支柱

| 支柱 | MUST / SHOULD |
|---|---|
| 可测 | 与人工一致、P/R/F1、稳定性方差；κ 仅双人标注后 |
| 可归因 | 维度分 + 对照实验槽位 |
| 可复现 | 固定种子 / 指纹 / 数据集版本 |
| 可行动 | 失败分类 + 修复建议结构 |
| 可门禁 | 未达标 MUST NOT 宣称「更准」或放行对外 gate |

---

## 7–8. Case Pack 与 Judge

- Case Pack：canonical hash + 执行前 live hash；scoped registry；ACL；
- `generated+claim_eligible` MUST 拒；
- Judge 默认非真理；校准报告见附录 O；未校准 Judge MUST NOT 单独满足 Phase Gate。

---

## 9. 门禁

- 发布/PR 回归是首场景；
- Gate 结果 MUST 绑定 plan/manifest 指纹；
- 套件绿 ≠ accuracy claim ≠ production_signed。

---

## 10. 评测中心

- Canonical UI：`/eval`（批准后）；旧页 redirect；
- Preview UI 不得对外宣称 accuracy；
- 禁止把诊断页冒充评测中心认证面。

---

## 11. 安全与多租户

- 评测请求 MUST 透传 tenant/actor；
- 跨租户金标 MUST 拒绝或显式授权；
- 评测执行 MUST 走 PolicyGate（工具/技能调用）。

---

## 12. 独立服务（A3）

- v1.0 **不强制** process_split；
- A3 须另批 ADR + staging；本标准只定义边界：拆分不得复制第二套协议语义。

---

## 13. 质量与声明边界

禁止声明：

- 无人工标签的 accuracy；
- 无范围限定的「通用更准」；
- 用 FDE 签收代替评测门禁，或反之。

允许声明：

- 范围限定、可复现的 benchmark；
- 「门禁通过（指纹=…）」类工程结论。

---

## 14. 路线图（摘要）

```text
Draft → Core 可认证（唯一入口+金标+门禁）
     → Extended（校准/多对象/评测中心）
     → Operational（A3/SLA/生产 authorize）
```

---

## 15. 迁移

- 旧 core eval 路径 → shim → 删除时间表写入 ADR；
- 旧金标包 → Case Pack 迁移脚本；失败 fail closed。

---

## 16. 符合性认证

- 机读权威：附录 N；
- `exists` / `core_ready` ≠ `certified`；
- 认证须非作者批准记录（对齐知识体系审批纪律）。

---

## 17. 实施参考（非规范）

见 `docs/architecture/plans/evaluation-system-v1.0-implementation-plan.md`。

---

## 18. 结论

评测系统标准把「准、唯一、可挡、可归因」写成契约；没有证据不得宣称更准；没有唯一入口不得宣称评测中心完成。
