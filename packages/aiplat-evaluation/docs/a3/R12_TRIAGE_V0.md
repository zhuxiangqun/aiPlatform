---
doc_type: Reference
---

# R12 · 对账差异分诊（v0）

> 源：[`R12_CAPABILITY_RECONCILIATION.md`](./R12_CAPABILITY_RECONCILIATION.md) · JSON evidence  
> 范围：tranche-1 `evaluation-system`  
> Honesty：tranche-1 H5=0 ≠ 全平台覆盖完成 ≠ Tier A 扩容

---

## 1. Join 口径（重要）

机器主键：`capability_registry.yaml` `provides` 符号。  
人类视图：`AIPLAT_CAPABILITIES.md` — **反引号 token ∪ 表格首列英文符号**（多数能力名不在反引号内；仅扫反引号会严重漏配）。

复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`

数量以最近一次脚本输出为准（见 reconciliation MD / `evidence/r12_*.json`）。

---

## 2. 分诊规则（执行）

| 类别 ID | 判定 | 默认处置 | 阻断 Tier A？ |
|---|---|---|---|
| **H1** | 对外宣称 / 发布门禁 / 安全相关 public API | 已在 CAPABILITIES 或须补行 | 是（缺则不得升 A） |
| **H1_candidate** | 疑似 public、尚未批白名单 | 本批已清零 → [`R12_H1_WHITELIST_V0.md`](./R12_H1_WHITELIST_V0.md) | 已登记 |
| **H2** | CoreFacade 纯 re-export / `*Error` / 私有 helper | 豁免至 **2027-02-14** | 否 |
| **H3** | 文档/ADR/面板文件名误进 join | 降为非能力叙述 | 否 |
| **H4** | 包内脚本 / 一次性工具 | 豁免至 **2027-02-14** | 否 |
| **H5** | 人类视图有、本域 registry 无的可调用能力（严格 `eval_`/`aiplat_eval_`/`*SubjectAdapter` 等形） | 补 registry 或删夸大文档 | 视宣称 |
| **H6** | 含 eval 样词但**不属**本域对账分子（形状不符，**或已登记在其他 registry domain**） | `out_of_tranche`；不计入 H5 清零 | 否 |

H5 噪声过滤：文件扩展名 / ADR / Panel / 路径 / **尾下划线文档词干**（如 `eval_`）→ H3；非严格形状 → H6；**跨域已登记** → H6。

H5 open：**0**（2026-11-14：补 5 SubjectAdapter；`eval_code_generator`/`eval_protocol`/`eval_sets`→H3；`eval_retrieval`→H4）。跨域已登记仍走 H6，不计入清零缺口。

Tier 初稿：[`TIER_MATRIX_V0.md`](./TIER_MATRIX_V0.md)（`A_candidate` ≠ 已授权 Tier A）。  
元评测家族清单：[`META_EVAL_FAMILY_CHECKLIST_V0.md`](./META_EVAL_FAMILY_CHECKLIST_V0.md)。

---

## 3. Owner

| 角色 | 职责 |
|---|---|
| 评测 owner | H1 白名单已落（见 [`R12_H1_WHITELIST_V0.md`](./R12_H1_WHITELIST_V0.md)）；签豁免到期 |
| 平台文档 | H3/H5 噪声降级 |
| 工程 | 维护 join 口径 + triage 过滤器 |

---

## 4. 退出标准（tranche-1 清零）

```text
H1_candidate：0 open（升 H1 已登记，或降 H2 豁免）✅
H2/H4：全部有豁免+到期日或已登记人类视图 ✅
H3/H5：已处置（H5 open=0）✅
H6：out_of_tranche 保留（跨域/形状不符；不计入 H5）
报表：按类别分列，禁止只报一个覆盖%
```
