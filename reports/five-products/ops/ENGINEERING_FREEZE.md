# Engineering freeze（本地工程轨）

- frozen_at: `2026-11-01`（初冻）
- **re_frozen_at**: `2026-11-01`（D3/E2E 关闭 + D2++ SOC + ADR v2 文档后）
- scope: five-products **local** packaging / D1–D3 local / Option B / E2E local
- `staging_ready`: **false**
- hard gates: **all false**（cutover / process_split / d3_production）

## Frozen means

本地工程增量已闭合（安装面、D2 pack、D3 本地验收、跨能力 E2E、compat/security、perf、packaging）。  
**本地五产品工程轨无必须任务；EVAL_V1 仍为显式解冻；DIAGNOSIS C1–C3 已出口 PASS。**  
再改须有明确缺陷、**已列 Still open**、复审驱动、或**显式解冻新范围**（可选 G2c self-consistency / Diagnosis fixture 硬化 / C4 需 staging）；禁止用本地证据推动 authorize。**G2b**：n=30 closeout 已完成、31–100 待双标；`accuracy_claim=false`（见 G2c/G2b closeout）。  

### 解冻史

| 时点 | 动作 |
|------|------|
| 初冻 | D1/D2 / packaging / Option B 收口 |
| [`ENGINEERING_UNFREEZE_D3_E2E.md`](./ENGINEERING_UNFREEZE_D3_E2E.md) | 解冻 D3 本地验收 + 跨能力 E2E |
| **本再冻结** | 上述两项已 PASS；Pi D2++ SOC schema 硬核；Field compose ADR → **v2 草案** |
| [`EVAL_V1`](./ENGINEERING_UNFREEZE_EVAL_V1.md) | 解冻评测 **E0–E5**（唯一 API/准确性/gate）；A3/生产仍冻 |
| [`EVAL_V1 UI preview`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md) | G2a locked 后解冻 `/eval` **local preview**（accuracy 仍禁） |
| [`DIAGNOSIS_V1 C0`](./ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md) | 解冻诊断 **C0**（产品定义/seed case/设计）；C1 代码另批；A3/生产冻 |
| [`DIAGNOSIS_V1 C1`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) | 解冻诊断 **C1**（D1c MVP）；无自动修复；A3/生产冻 |
| [`DIAGNOSIS_V1 C1 closeout`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) | **C1 PASS**（#513/#514）；盲测 fixture 出口 |
| [`DIAGNOSIS_V1 C2`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) | 解冻诊断 **C2**（Eval/Ontology 加深 + 置信度/unknown·stale；无自动修复）；G2b 仍冻 |
| [`DIAGNOSIS_V1 C2 closeout`](./DIAGNOSIS_V1_C2_CLOSEOUT.md) | **C2 PASS**（#516）；report.v1；保持 A0 |
| [`DIAGNOSIS_V1 C3`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md) | 解冻诊断 **C3**（D2/D3 本地收口）；G2b / A3 仍冻 |
| [`DIAGNOSIS_V1 C3 closeout`](./DIAGNOSIS_V1_C3_CLOSEOUT.md) | **C3 PASS**（#518）；D2 pack local；保持 A0/D1c |
| [`EVAL_V1 E6`](./ENGINEERING_UNFREEZE_EVAL_E6.md) | 解冻评测中心 UI v1；[`E6 closeout`](./EVAL_V1_E6_CLOSEOUT.md) **PASS**；G2b/accuracy 仍冻 |
| [`EVAL_V1 E7`](./ENGINEERING_UNFREEZE_EVAL_E7.md) | 解冻 D2/D3 本地收口；[`E7 closeout`](./EVAL_V1_E7_CLOSEOUT.md) **PASS**；split 仍 false |
| [`EVAL G2c decision`](./ENGINEERING_DECISION_EVAL_G2C_SELF_CONSISTENCY.md) | **Accepted**：claim 降级为 self-consistency；**不开 G2b**；禁止 accuracy |
| [`DIAGNOSIS C3.5`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C35_FIXTURE_HARDENING.md) | adversarial fixtures + metrics subset；[`C35 closeout`](./DIAGNOSIS_V1_C35_CLOSEOUT.md) **PASS** |
| [`EVAL G2c`](./ENGINEERING_UNFREEZE_EVAL_G2C.md) | self-consistency / intra-rater；[`G2C closeout`](./EVAL_V1_G2C_CLOSEOUT.md) **PASS**；≠ accuracy |
| [`EVAL A3 local`](./ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md) | 本地独立进程/DB 验证（A0–A6）；**Closed PASS** #529；`process_split` 仍 false |
| [`EVAL A3 B0 JWKS`](./ENGINEERING_UNFREEZE_EVAL_A3_B0_JWKS.md) | 本地 RS256 JWKS 校验（fixture/URL）；**Closed PASS** #531 |
| [`EVAL A3 B1-L/B2-L local`](./ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md) | 本机开发独立 API/Worker；staging=验收闸门非开工证；`process_split` 仍 false |

- ❌ **仍不解冻**：staging_ready / production_signed / 任何 authorize 成功 / accuracy 宣称 / 自动修复 / A3 **生产拆分**（A3 **local** 已解冻；**G2b prep** 已解冻但 accuracy 仍禁，见下表）  
- 计划同步：工程方案 **V2.2** + [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) + [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)

### Active unfreeze

| 范围 | 文档 | 允许 | 禁止 |
|---|---|---|---|
| EVAL_V1 | [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md) | E0–E5 + G2a local gate | A3 / staging / authorize / accuracy |
| EVAL_V1 UI preview | [`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md) | `/eval` local preview（E6 承接） | accuracy / 外部 gate |
| EVAL_V1 E6 | [`ENGINEERING_UNFREEZE_EVAL_E6.md`](./ENGINEERING_UNFREEZE_EVAL_E6.md) | **Closed PASS** — 见 [`EVAL_V1_E6_CLOSEOUT.md`](./EVAL_V1_E6_CLOSEOUT.md) | accuracy / κ / 外部 gate / G2b / A3 |
| EVAL_V1 E7 | [`ENGINEERING_UNFREEZE_EVAL_E7.md`](./ENGINEERING_UNFREEZE_EVAL_E7.md) | **Closed PASS** — 见 [`EVAL_V1_E7_CLOSEOUT.md`](./EVAL_V1_E7_CLOSEOUT.md) | authorize / accuracy / G2b / A3 生产拆分 |
| DIAGNOSIS_V1 C1 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C1_CLOSEOUT.md`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) | 自动修复 / A3 / staging / authorize |
| DIAGNOSIS_V1 C2 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C2_CLOSEOUT.md`](./DIAGNOSIS_V1_C2_CLOSEOUT.md) | 自动修复 / A3 / staging / authorize / G2b accuracy |
| DIAGNOSIS_V1 C3 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C3_CLOSEOUT.md`](./DIAGNOSIS_V1_C3_CLOSEOUT.md) | 自动修复 / A3 / staging / authorize / G2b accuracy / 静默开 C4 |
| DIAGNOSIS_V1 C3.5 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C35_FIXTURE_HARDENING.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C35_FIXTURE_HARDENING.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C35_CLOSEOUT.md`](./DIAGNOSIS_V1_C35_CLOSEOUT.md) | 准确率宣称 / remediate / A3 / staging |
| EVAL_V1 G2c | [`ENGINEERING_UNFREEZE_EVAL_G2C.md`](./ENGINEERING_UNFREEZE_EVAL_G2C.md) | **Closed PASS** — 见 [`EVAL_V1_G2C_CLOSEOUT.md`](./EVAL_V1_G2C_CLOSEOUT.md) | accuracy / 把 intra κ 写成 inter-annotator |
| EVAL G2b prep | [`ENGINEERING_UNFREEZE_EVAL_G2B_PREP.md`](./ENGINEERING_UNFREEZE_EVAL_G2B_PREP.md) | **Open (prep)** — 30 条包 + κ 脚本；等人；`accuracy_claim=false` | `accuracy_claim=true` / 同人冒充第二人 / authorize |
| EVAL A3 local | [`ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md`](./ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md) | **Closed PASS** — A0–A6 本地独立验证（#6 local JWT ✅）；[`A_LOCAL_CLOSEOUT.md`](../../../packages/aiplat-evaluation/docs/a3/A_LOCAL_CLOSEOUT.md) | `process_split_authorized=true` / staging / authorize / production_signed |
| EVAL A3 B0 JWKS | [`ENGINEERING_UNFREEZE_EVAL_A3_B0_JWKS.md`](./ENGINEERING_UNFREEZE_EVAL_A3_B0_JWKS.md) | **Closed PASS** #531 — RS256 JWKS（`AIPLAT_EVAL_JWKS_JSON`/`_URL`）；HS256 仍为默认 | staging_ready / authorize / production_signed / Keycloak 集群宣称 |
| EVAL A3 B1-L/B2-L | [`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](./ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md) | **Closed PASS (local)** — B1–B3-L/S1/P1/LLM/microVM-prep/contract（#561）；**P1 canonical #562**；**live LLM smoke**；**P1 dimensions v1**；**S1 live_llm #566**；**session_eval v0 #567**；**local_track_closeout v1**；证据 `environment=local`；下一 staging / 第二标注者 | `process_split_authorized=true` / staging_ready / production_signed / 把 local 标成 staging / microVM runtime / G2b accuracy / 再堆 stack 层 |

## Verify

```bash
bash scripts/ops_engineering_freeze_check.sh
bash scripts/five_products_gate.sh   # 需本机 listen（非沙箱）
```

## Still open（非本 freeze）

| 项 | 说明 |
|----|------|
| 真实预发 | 11-08/15/22 → continue_defer；复审改为 **事件驱动** [`STAGING_REVIEW_EVENT_DRIVEN.md`](./STAGING_REVIEW_EVENT_DRIVEN.md)；11-29 **cancelled** |
| live → sign → authorize | [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) |
| Field compose 长驻 | 草案 **v2** → **继续 Draft**（[`ADR-DRAFT-fde-field-compose.md`](../ADR-DRAFT-fde-field-compose.md) · 不实施） |
| D2++ deeper SOC | ✅ 本地 schema 硬核已闭合；真实 SIEM/webhook 仍须 staging |
| 日历复审 | **停止空转**；有主机再审 |

## Evidence index

见 [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) · [`G0_CLOSEOUT.md`](../G0_CLOSEOUT.md) · [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · [`OPTION_B_LAST_RUN.md`](./OPTION_B_LAST_RUN.md)
