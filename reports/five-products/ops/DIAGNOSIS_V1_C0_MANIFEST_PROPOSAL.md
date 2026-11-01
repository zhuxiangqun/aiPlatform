# DIAGNOSIS_V1 C0 — manifest / apps.yaml 更新提案（不落地）

> C0 出口确认前 **不修改** `capabilities.manifest.yaml` / `apps.yaml`。

## 提案：第六能力

```yaml
# capabilities.manifest.yaml（提案片段）
diagnosis:
  autonomy: A2          # 目标；现状按 D1c 共宿，不宣称 A3
  delivery: D1          # D1c cohost 先；process_split=false
  delivery_mode: cohost
  package: aiplat-diagnosis
  healthz: /api/platform/apps/diagnosis/healthz
  notes: "C0 design only; C1 MVP; A3 deferred; no auto-remediation"
```

## 提案：apps.yaml

```yaml
# aiPlat-platform/registry/apps.yaml（提案）
- id: diagnosis
  api_prefix: /api/platform/apps/diagnosis
  module: apps.diagnosis
  product_id: diagnosis
```

## 反转旧映射

- 删除/反转任何 `diagnosis → evaluation` 的 `product.manifest` 映射（若仍存在）。
- STATUS 能力表在 **C0 出口确认后** 增加 Diagnosis 行；此前仅 banner 标注 C0。

## 模块文档

- 新增 `reports/five-products/modules/diagnosis/MODULE.md`（已起草骨架）。
