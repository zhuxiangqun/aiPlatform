---
doc_type: Reference
title: 评测计分与 Claim 口径地图（对外 SSOT）
status: active
authority: supporting
created: 2026-11-23
updated: 2026-11-23
---

# 评测计分与 Claim 口径地图（对外 SSOT）

> **唯一对外引用入口**（工程内部细节仍见各子文档）。  
> Honesty：本页防误读，**不**升级 `accuracy_claim` / 安全认证 / A3 拆分授权。  
> 信任边界总论：[eval-trust-boundary-lab-vs-cert.md](../../../../docs/architecture/plans/eval-trust-boundary-lab-vs-cert.md)  
> 硬化总方案：[interop-eval-trust-hardening.md](../../../../docs/architecture/plans/interop-eval-trust-hardening.md) B 轨

## 1. 一句话

**可信的是「这次怎么跑、用了哪条计分路径、命中了什么」；不可信的是「成果物已准确 / 可上线 / 已安全认证」。**

## 2. 口径对照表

| 对象 | 路径 / 权威 | 可用于 | 不可用于 |
|------|-------------|--------|----------|
| package **`build_composite`** | `packages/aiplat-evaluation/app/scoring/composite.py`；工程 SSOT（ARCH clause 77） | 同配置工程回归、A/B；须同时看 `weights_used` + 有数据的 family | 准确率认证；family 覆盖不同时的跨对象排名 |
| Central **`legacy_7dim`** | `core/harness/evaluation/`；`deprecated_for_engineering=true`；**永久 report-only** | 历史对照 | 工程门禁、对外准确率、冒充 package composite |
| **scoped G2b** `accuracy_claim` | G2b attestation / closeout；限定 benchmark | 该 benchmark 上的限定声明 | 产品级 accuracy、安全认证、FDE 签收 |
| **product** `accuracy_claim` | 产品级总开关；默认 **false** | 仅显式升级流程通过后 | 默认状态；不可由 scoped 自动推导为 true |

### 强制展示规则

任何对外 UI / API 展示 `composite` / `score` 时：

1. 标明 `scoring.path` ∈ `{package_build_composite, legacy_7dim}`。
2. 若有 package composite：展示 `weights_used` 与 `family_scores`（缺维 family 为 null = 未测，不是 0 分）。
3. `accuracy_claim` 默认 false；scoped true **不得**改写为 product true。

## 3. 双 composite 终态（诚实冻结）

- **保留双路径**：禁止把 `legacy_7dim` 权重改成 package 公式（clause 77）。
- 新门禁 / 新 UI **只认** `build_composite`。
- legacy 仅显式请求或历史页可见；徽章文案：**「历史口径·非工程」**。

Family 重归一化含义：只测 quality 时 composite≈quality；测 quality+efficiency 才是加权分。因此 **composite 不天然可跨对象排名**（与信任边界文档一致）。

**B-P5（已接线）**：调用 `build_composite(..., composite_profile_id="engineering_v1")` 时，
固定要求 `quality`+`efficiency`；缺维 → `incomplete=true` 且 `score=null`，**禁止**把部分 family
静默重归一化当完整可比分。未传 profile 时保留历史重归一化行为（工程回归兼容）。

**B-P3（已接线）**：`engineering_score_accepted(scoring.path)` — 新门禁只认
`package_build_composite` / `build_composite`；`legacy_7dim` → false。

## 4. Claim 升级（scoped → product）

| 门 | 说明 |
|----|------|
| 数值门槛 | 以 G2b 现行 aggregate / closeout 为准（禁止本页手抄过期数字） |
| 双标 / κ | κ 是标注一致性，**不是**准确率 |
| Attestation | scoped accept ≠ product 认证 |
| 独立批准 | product 升级须显式流程；**scoped true 时 product 仍为 false** |

核对清单 API：`g2b_claim_unlock_checklist`（CoreFacade）。字段对齐（代码为准）：

| checklist 字段 | 含义 |
|----------------|------|
| `scoped_accuracy_claim` | 限定 benchmark 声明（可 true） |
| `accuracy_claim` | **product** 总开关；清单恒返回 false，直至显式升级流程 |
| `g2b_scoped_ready` / `g2b_scoped_blockers` | scoped AND 门 |
| `broader_trust_blockers` | arena / staging / 外审等更广信任门（≠ product 自动升级） |
| `not_accuracy_certification` | 恒 true 诚实锁 |

**一句话验收：`scoped_accuracy_claim=true` 时 `accuracy_claim`（product）仍为 false。**

## 5. Store 表面（勿混）

见 [`STORE_SURFACE_V0.md`](./STORE_SURFACE_V0.md)：契约 8 实体 shape ≠ standalone CRUD 全量；Central 仍为维护 UI SSOT。

## 6. 相关入口

| 文档 | 用途 |
|------|------|
| [`P1_CANONICAL.md`](./P1_CANONICAL.md) | package vs legacy 诚实门 |
| [`PRODUCT_ROOT_V1.md`](./PRODUCT_ROOT_V1.md) | 产品根声明 |
| [`G2B_ACCURACY_CLOSEOUT.md`](./G2B_ACCURACY_CLOSEOUT.md) | G2b 收口索引 |
| [`REPORT_COMPARE_V0.md`](./REPORT_COMPARE_V0.md) | 同 `composite_version` 才 comparable |
