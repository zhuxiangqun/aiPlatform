# DIAGNOSIS_V1 C0 — manifest / apps.yaml 更新提案（不落地）

> C0/C1 出口确认前 **不修改** 真实 `capabilities.manifest.yaml` / `apps.yaml`。  
> 本文件必须贴合**真实文件形状**：`capabilities` 是 **list**；`apps.yaml` 的模块在 **`modules:` map** 下。

## 当前 vs 目标（诚实）

| 字段 | 当前（C0，未入册） | C1 目标 | 禁止现在写 |
|---|---|---|---|
| `current_autonomy` | **A0**（仅设计） | A2 | 直接写 A2 当现状 |
| `current_delivery` | **D0**/未入册 | D1 + `delivery_mode: cohost`（D1c） | 写 D1 当已交付 |
| `process_split_authorized` | n/a → false | false | true |
| `target` | — | A2/D1c → 远期 A3/D2 | 把 target 当 current |

## 提案：`capabilities.manifest.yaml`（list 项）

```yaml
  # 追加到 capabilities: 列表 —— 不是 map key
  - id: diagnosis
    label: Diagnosis Service
    deploy_unit: central
    current_autonomy: A0          # C0/C1 入册初期保持 A0，直到 C1 出口再升
    current_delivery: D1          # 仅在 C1 接线后；C0 不入册
    delivery_mode: cohost         # D1c
    target: A2/D2
    package: packages/aiplat-diagnosis
    platform_app: aiPlat-platform/apps/diagnosis
    charter: reports/five-products/modules/diagnosis/MODULE.md
    a3_adr: reports/five-products/ADR-DRAFT-diagnosis-d1.md
    a3_adr_status: draft
    process_split_authorized: false
    healthz: GET /api/platform/apps/diagnosis/healthz
    contracts_test: reports/five-products/modules/diagnosis/contracts/validate_sample.py
    notes:
      - "C0 design only until C1 unfreeze; no auto-remediation"
      - "D1c/cohost = healthz+API on central host; not independent process deploy"
      - "Do not claim diagnosis accuracy until ≥10 real evidence fixtures + seed eval"
```

**C0 阶段**：STATUS 仅 banner 标注 DIAGNOSIS_V1 C0；**能力表仍 5 行**（sync 继续绿）。

## 提案：`aiPlat-platform/registry/apps.yaml`（modules map）

```yaml
modules:
  # ... existing ...
  diagnosis:
    name: "诊断产品"
    description: "跨平台证据驱动诊断（Case/Evidence/Hypothesis/Report）；不自动修复"
    enabled: false   # C1 解冻接线前保持 false 或待 C1 置 true
    api_prefix: "/api/platform/apps/diagnosis"
    api_module: "apps.diagnosis.api.router"
    service_module: "core.apps.diagnosis.service"
    prompts_module: null
    domains: []
    agents: []
    skills: []
```

## 反转旧映射

- 删除/反转任何 `diagnosis → evaluation` 的 legacy `product.manifest` 映射（若仍存在）。
- Diagnosis **不**并入 Evaluation。

## 入册时机

| 时机 | 动作 |
|---|---|
| C0 合并 | 仅文档提案；**不**改真实 manifest |
| C1 解冻 + 代码接线 | `enabled: true` + capabilities list 追加；`current_autonomy: A0` |
| C1 出口达标 | 再评估升 `current_autonomy: A2` / 保持 D1c |
