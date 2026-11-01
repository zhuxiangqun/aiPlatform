# Engineering unfreeze — DIAGNOSIS_V1 C2（深度接入 + 置信度）

- **decided_at**: `2026-11-01`
- **status**: **Active — C2 only**（本 PR 解冻文档；**代码另开实现 PR**）
- **C1**: [`ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) · closeout [`DIAGNOSIS_V1_C1_CLOSEOUT.md`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) · #513/#514
- **charter**: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md) §4 / §8 C2
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: diagnosis（D1c 深化，仍 A0→评估 A2）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 为何选 C2（而非 EVAL G2b）

| 选项 | 阻塞 | 结论 |
|---|---|---|
| **EVAL G2b** | 需第二标注者 + κ；[`ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md) 已记「暂停 G2b，不阻塞 Diagnosis」 | 暂缓 |
| **DIAGNOSIS C2** | C1 已 PASS；charter 下一阶段为 Evaluation/Ontology 接入与置信度 | **本解冻默认路径** |

EVAL `/eval`：C1 期间的「冻结新功能」在 C1 closeout 后解除；G2b 仍未解冻（accuracy/外部 gate 禁）。C2 期间 EVAL 仅允许缺陷修复 + 既有 preview，**不开 G2b**。

## 目标

在 C1 D1c 之上深化诊断产品（仍 **cohost**、仍 **不自动修复**）：

1. **Evaluation / Ontology 只读适配加深**（EvidenceRef；不写源库）；
2. **版本回归（S2）** 置信度与反证字段产品化；
3. **unknown / stale** 一等公民：UI + API 明确暴露原因码；
4. **新场景子集（可选，C2 中期）**：知识/RAG、部署/配置、安全/治理 — 各 ≥2 真实脱敏 fixture 才报指标；
5. 保持 `accuracy_claim=false`；fixture 指标继续 **blind**。

## 允许的代码面

- `aiPlat-platform/apps/diagnosis/api/`
- `aiPlat-core/core/apps/diagnosis/service/`（adapters / engine / metrics / store）
- `packages/aiplat-diagnosis/`（contracts / fixtures）
- `aiPlat-management/frontend/src/pages/Diagnosis/`
- `STATUS.md` / MODULE / tests / capability notes（**不升 A2 当现状**，直至 C2 出口评估）

## 禁止

| 禁止 | 原因 |
|---|---|
| `POST …/remediate` / `auto_execute=true` | 产品边界：只建议 |
| 跨产品写 / 直读源 DB | 证据只读 |
| A3 进程/DB 拆分 | 需 ADR + staging |
| staging / `production_signed` / authorize | 生产门仍冻 |
| 宣称 accuracy / 外部 gate | 评测权威在 EVAL；诊断仅工程 fixture |
| 静默开 EVAL G2b | 需独立 unfreeze + 第二标注者 |
| 把 target A2 写成 current | C2 出口再评估 |

## Fixture / 指标（C2）

| 项 | 门槛 |
|---|---|
| 保留 C1 10 案回归 | Top-1≥70% · Top-3≥85% · bare=0（blind） |
| 新场景（若开） | 每场景 ≥2 real fixture 才进指标子集 |
| unknown/stale 正确率 | ≥90% |
| 证据完整率 | ≥90% |
| 单案耗时 | <10 分钟 |
| 自动修复 | **无** |

## C2 出口

| 项 | 门槛 |
|---|---|
| Eval/Ontology adapter | 至少各 1 条生产只读路径有非测试 caller |
| Report | 暴露 confidence + unknown/stale reason codes |
| UI | `/diagnosis` 展示置信度与不确定态 |
| Autonomy | 评估是否升 `current_autonomy: A2`（未达标则保持 A0） |
| Delivery | 保持 D1c；**不** `process_split_authorized=true` |
| Closeout | 新 `DIAGNOSIS_V1_C2_CLOSEOUT.md` + Outcome |

## 串行规则

- **DIAGNOSIS C2**：独占工程焦点；不并行开 EVAL G2b。
- **EVAL**：缺陷修复 + G2a preview OK；G2b / accuracy 仍冻。
- C2 完成后再评估 C3 或 EVAL G2b。

## 验证（解冻文档合入后、实现前）

```bash
python3 scripts/check_five_products_status_sync.py
bash scripts/ops_engineering_freeze_check.sh
# 实现 PR 另加：
# pytest aiPlat-core/core/tests/unit/test_diagnosis_v1_c1.py -q
# PYTHONPATH=aiPlat-core python3 -c "from core.apps.diagnosis.service.metrics import fixture_metrics; print(fixture_metrics(limit=10)['top1_rate'])"
```

## 回滚

- 禁用新增 C2 API/UI 开关或回退 adapters；
- 保留 C1 API/fixtures；
- 不触碰源产品数据。

## 变更控制

- 范围变化 → 新 unfreeze，不静默扩大。
- 任何 A3/staging/authorize/auto-repair/G2b accuracy → 不在本解冻内。
- 完成/中止 → 追加 Outcome，更新 `ENGINEERING_FREEZE.md`。

## Outcome

- `_pending_`（C2 出口填写）
