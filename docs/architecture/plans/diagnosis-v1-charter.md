# DIAGNOSIS_V1 Charter — 诊断产品（第六能力）

> **文档类型**：Product / Design Charter  
> **状态**：**Accepted for C0** · 2026-11-01  
> **范围**：诊断产品 v1（本地工程 + 产品设计）；不含 A3、生产 staging/authorize/SLA  
> **解冻**：[`ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md)  
> **上游计划**：[`five-capability-independent-engineering-plan.md`](./five-capability-independent-engineering-plan.md) V2.2  
> **目标架构**：[`ai-platform-five-products-target-architecture.md`](./ai-platform-five-products-target-architecture.md) §5.5  
> **现状**：[`STATUS.md`](../../../reports/five-products/STATUS.md)  
> **本文件不是**：实施记录；不代表 `process_split` / `staging_ready` / `production_signed` 解冻。

---

## 0. 一句话

**诊断产品回答“为什么坏、坏在哪、证据是什么、下一步怎么办”；它不拥有源事实，不自动修复。**

```
证据接入 → 关联 → 发现/假设 → 可追溯报告 → 建议/受控任务
              （不做默认自动修复）
```

---

## 1. 产品边界变更

当前：

- `capabilities.manifest` **没有 diagnosis**；
- 旧 `product.manifest` 把 `diagnosis` 映射到 `evaluation`；
- `apps.yaml` 没有 diagnosis app；
- 代码里是 core `/diagnostics/*` + 管理端 20+ 页面，属于**内部工具箱**，不是产品；
- 目标架构 §5.5 已定义“诊断”为跨平台 AI 质量与运行保障产品，但只有定义 + ADR 草案。

**本 Charter 的决定**：

> 诊断成为 **第六个能力**，与 Evaluation 并列，不合并。

| 能力 | 回答 |
|---|---|
| Evaluation | 好不好（分数/排序/gate） |
| Diagnosis | 为什么/哪里/证据/怎么办 |
| Testing | 跑检查 |
| Remediation | 通过目标 API 修复（后置） |
| FDE | 客户验收/交付真源 |
| aiPlat / Pi / Ontology | 控制面 / 边缘 / 知识 |

**C0 只写产品定义/证据模型/seed case；C0 出口才更新 manifest。**

---

## 2. 锁定决策

| # | 决策 | 内容 |
|---|---|---|
| D1 | 能力数 | **第六个能力**：diagnosis（与 evaluation 并列） |
| D2 | 首发场景 | **① run 失败诊断；② 版本回归诊断** |
| D3 | 自动修复 | **不做**；只出建议/受控任务；修复由目标产品 API 执行 |
| D4 | 事实所有权 | 不拥有源事实；只保留证据引用/诊断报告 |
| D5 | 首版证据源 | aiPlat / Pi / FDE / Evaluation；Ontology/外部后置 |
| D6 | 首版形态 | **D1c cohost**；A3 独立服务后置 |
| D7 | 入口 | canonical `/api/platform/apps/diagnosis`；UI `/diagnosis` |
| D8 | 旧工具箱 | `/diagnostics` 保留为工程工具；不直接包装成产品 |
| D9 | 准确度 | 20–30 个已知根因 seed case；Top-1 ≥70%、Top-3 ≥85% |
| D10 | 不确定 | 无证据 → `unknown`；过期 → `stale`；禁止无证据结论 |
| D11 | 生产 | `process_split` / staging / authorize 全部仍冻 |

---

## 3. 目标与非目标

### 3.1 目标

1. **可解释**：每个结论有 evidence ref、版本、时间、置信度。
2. **可追溯**：从报告回到 run/trace/version/日志。
3. **可行动**：建议能落到模型/路由/SOP/工具/配置/数据。
4. **可跨产品**：首版 aiPlat/Pi/FDE/Evaluation，后续 Ontology/外部。
5. **可产品化**：Case/Report/API/UI 稳定，A3 只差 ADR/staging。

### 3.2 非目标

- 不做评测打分/排序（Evaluation 负责）；
- 不做 FDE 客户验收；
- 不做自动修复/跨平台写；
- 不做“所有外部 AI 产品”的通用诊断；
- 不做第一版全自动根因；
- 不做多租户/计费/SLA；
- 不做 A3 进程拆分。

---

## 4. 能诊断什么

| 类别 | 能诊断 | 需要的证据 |
|---|---|---|
| **Run 失败** | 工具错、路由错、SOP 漏、上下文缺失、模型选错、超时、成本异常、策略拒绝 | run、trace、syscall、context、tool result、eval report |
| **版本回归** | v1→v2 变差；Bundle/配置/模型/提示词变化 | 版本快照、baseline、A/B 评测、diff |
| **跨产品链路** | aiPlat 发布 → Pi 执行 → FDE 验收 → Evaluation 评分，哪一段断 | 各产品 Evidence、run_id/trace_id/version |
| **知识/RAG**（C2） | 召回差、文档漂移、本体覆盖不足/冲突 | 检索日志、doc/wiki 版本、本体统计 |
| **部署/配置**（C2） | Pi/Field/PG/HA health、config drift、升级/回滚失败 | healthz、部署记录、配置快照 |
| **安全/治理**（C2） | 策略拒绝、审计异常、不安全输出、越权 | policy decision、audit、安全扫描 |
| **业务影响**（后置） | 只有接入业务 telemetry 才能谈 | 业务指标、转化/工单 |

**限制**：不保证 100% 根因；只给“证据 + 假设 + 置信度 + 建议”。

---

## 5. 产品对象

| 对象 | 说明 |
|---|---|
| `DiagnosisCase` | 一次诊断（场景/目标/版本/状态） |
| `EvidenceRef` | 证据引用（source/kind/id/version/time） |
| `Finding` | 现象/位置/严重度/置信度 |
| `Hypothesis` | 候选根因（含支持/反证） |
| `Recommendation` | 建议/受控任务（不直接执行） |
| `DiagnosisReport` | 可追溯报告（含 unknown/stale） |

**每个 Finding/Hypothesis 必须有 evidence ref；没有就标 `unknown`。**

---

## 6. 目标架构

```
Evidence Sources
  aiPlat / Pi / FDE / Evaluation / Ontology(later)
        ↓ read-only adapters
Evidence Graph / Case Store
        ↓
Detectors / Correlation
  version diff, trace topology, tool errors, context gaps,
  policy denies, cost/latency anomalies
        ↓
Hypothesis Engine
  rules first; LLM only explains with citations
        ↓
Diagnosis Report
  findings / hypotheses / confidence / unknown-stale / recommendations
        ↓
API / UI / (controlled remediation later)
```

### 6.1 代码归属

| 层 | 位置 |
|---|---|
| REST | `aiPlat-platform/apps/diagnosis/api/` |
| 业务逻辑 | `aiPlat-core/core/apps/diagnosis/service/` |
| 通用检测 | `aiPlat-core/core/harness/diagnosis/`（仅通用） |
| 包装/部署 | `packages/aiplat-diagnosis/` |
| 契约 | `packages/aiplat-diagnosis/contracts/` |
| UI | `aiPlat-management/frontend/src/pages/Diagnosis/` |
| 注册 | `aiPlat-platform/registry/apps.yaml` |
| 门面 | 平台访问 core 走 `CoreFacade` |

### 6.2 唯一 API 资源

| 资源 | 说明 |
|---|---|
| `/diagnosis-cases` | 创建/查看 case |
| `/diagnosis-cases/{id}/evidence` | 证据引用 |
| `/diagnosis-cases/{id}/findings` | 发现 |
| `/diagnosis-cases/{id}/hypotheses` | 假设 |
| `/diagnosis-cases/{id}/report` | 报告 |
| `/diagnosis-cases/{id}/recommendations` | 建议/受控任务 |
| `/diagnosis-cases/{id}/unknown-stale` | 不确定标记 |

### 6.3 数据

- `diagnosis_cases`
- `evidence_refs`
- `findings`
- `hypotheses`
- `recommendations`
- `diagnosis_reports`

本地 SQLite；PG 后置；不复制源事实。

---

## 7. MVP 范围（C1）

| 项 | 内容 |
|---|---|
| 场景 | run 失败；版本回归 |
| 证据源 | aiPlat / Pi / FDE / Evaluation |
| Seed | 20–30 个已知根因 case |
| 输出 | Case + evidence graph + findings + hypotheses + report |
| UI | `/diagnosis` 列表/详情/报告 |
| 运行 | D1c cohost |
| 修复 | **无**；只建议 |
| 不确定 | unknown/stale 一等公民 |

### 7.1 验收指标

| 指标 | 目标 |
|---|---|
| Top-1 根因准确率 | ≥ 70% |
| Top-3 根因命中率 | ≥ 85% |
| 证据完整率 | ≥ 90% |
| 无证据结论 | **0** |
| unknown/stale 正确率 | ≥ 90% |
| 诊断耗时 | < 10 分钟/案 |
| 建议可执行率 | ≥ 70%（人工评估） |

---

## 8. 工作分解与路线图

| 阶段 | 内容 | 工期 | 解冻 |
|---|---|---|---|
| C0 | Charter + 证据模型 + 20–30 seed case + API/UI 设计 + manifest 提案 | 2 周 | ✅（seed/schema/设计已落；待排期确认） |
| C1 | D1c MVP：aiPlat/Pi/FDE 证据、case、report、`/diagnosis` | 4–6 周 | C0 出口后 |
| C2 | Evaluation/Ontology 接入、版本回归、置信度、unknown/stale | 4–6 周 | C1 后 |
| C3 | D2/D3 本地收口、文档/安全/性能 | 3–4 周 | C2 后 |
| C4 | A3 独立服务 | staging 后 | 后置 |

**MVP：约 10–14 周；A3 另计。**

---

## 9. 对现有计划的影响

1. 能力数 **5 → 6**：aiPlat / Pi / Ontology / Evaluation / FDE / **Diagnosis**。
2. C0 出口更新：`capabilities.manifest` + `modules/diagnosis/MODULE.md` + `apps.yaml` + `STATUS`。
3. 删除/反转 `product.manifest` 的 `diagnosis → evaluation` 旧映射。
4. 新增解冻：`ENGINEERING_UNFREEZE_DIAGNOSIS_V1`；生产门继续冻。
5. 现有 `Diagnostics` 页面/端点作为证据采集器/工具箱，不直接包装成产品。
6. 工作量增加约 **10–14 周**；需与 EVAL_V1 排优先级。

---

## 10. 角色与投入

| 角色 | 职责 |
|---|---|
| 你 | 决策、seed case/根因标注、验收、优先级 |
| 我 | 产品设计/证据模型/API/UI/引擎/报告 |
| 领域专家 | seed case 根因复核（按需） |

成本：模型调用 + 标注/复核人力；无服务器采购。

---

## 11. 风险与止损

| 风险 | 止损 |
|---|---|
| 根因难 | 先 20–30 个已知根因 case；Top-1 <50% 停 |
| 无证据 | unknown/stale；禁止编结论 |
| LLM 幻觉 | 规则优先；LLM 只解释且必须引用 evidence |
| 证据接入难 | 首版只接 aiPlat/Pi/FDE/Eval；不扩外部 |
| 与 Evaluation 重叠 | Evaluation 打分；Diagnosis 解释；不合并 |
| UI 膨胀 | 只做 Case/Report；旧 Diagnostics 不搬 |
| 自动修复风险 | C1–C2 不做；后置需 ADR/权限 |
| 第六能力过重 | 先 C0；C0 出口再决定是否进 C1 |
| 单人 workload | 与 EVAL_V1 串行，不并行开两条重轨 |

**停止条件**
- 找不到 20 个已知根因 case → 停在 C0。
- Top-1 < 50% → 不宣称诊断准确，改规则/缩小场景。
- 出现无证据结论 → 停 LLM 结论，回规则。
- 证据接入不可用 → 缩到单产品（aiPlat）。

---

## 12. 今后需要做的事（v1 之后）

1. 扩证据源：Ontology、外部 AI 产品、业务 telemetry。
2. 扩场景：知识/RAG、部署/配置、安全/治理、业务影响。
3. 受控修复：通过目标 API，带权限/审批/回滚（ADR）。
4. A3 独立服务：进程/DB/部署/回滚。
5. 诊断知识库/runbook 自动推荐。
6. 与 Evaluation gate 联动：诊断失败 → 回退/修复 → 复评。
7. 多租户/配额/审计/SLA（商业启动后）。
8. 诊断质量度量：根因准确率、证据完整率、时间、建议采纳率。

---

## 13. C0 出口条件

- [x] 第六能力决策。
- [x] 两个首发场景。
- [x] 不自动修复。
- [x] 证据源/边界/指标定义。
- [ ] 20–30 个 seed case 清单 + 根因标签。
- [ ] 证据 schema v0。
- [ ] `/api/platform/apps/diagnosis` + `/diagnosis` UI 设计稿。
- [ ] manifest/module/apps.yaml 更新提案。
- [ ] 与 EVAL_V1 的排期确认。

C0 只产出文档/设计，不改业务代码；C1 起才动 API/UI。

---

## 14. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-01 | v1.0 | 初版：第六能力；run 失败 + 版本回归；不自动修复；证据驱动；D1c 先行 |
