# 安全质量 26 维覆盖（人读摘要）

> **唯一真相源**：[security_quality_dimensions.yaml](./security_quality_dimensions.yaml)（`dimension_set_version=1.1`）  
> Crosswalk：[docs/security/security-dimension-crosswalk.md](../../docs/security/security-dimension-crosswalk.md)  
> 报告：`python3 scripts/security_dimensions_report.py`

## 字段含义

| 字段 | 含义 |
|---|---|
| `ledger_ok`（主） | YAML 可解析、恰 26 维、字段合法；**E 必须含 ≥1 条 V/T** |
| `schema_ok` | **`ledger_ok` 的兼容别名**（同值） |
| `accounted_ok` | **有主**：P0 有 owner；G 须 owner+gap+next（允许 G） |
| `release_ok` | **可发布**：accounted 且无未接受的 `release_blocking`（G 必须 `release_risk_acceptance`） |
| `coverage_ok` | **做完**：所有 P0 均为 E 且 gap 空 |
| `security_certification` | 恒 false |

```text
有主 ≠ 可发布 ≠ 做完 ≠ 认证
```

## ID 稳定

- **D07–D25 未重排**；追加 **D26** 承载成果物 authz。
- D06 收窄为**平台**授权；成果物 authz 在 D26。

## 三门禁

| 门 | CLI | 条件 |
|---|---|---|
| ledger | 默认 CI / `--ledger-gate` | `ledger_ok` |
| release | `--release-gate` | `ledger_ok ∧ accounted_ok ∧ release_ok` |
| claim | `--claim-gate` / `--strict-gaps` | `ledger_ok ∧ coverage_ok`（**仅**对外安全声明） |

## 当前缺口（摘要）

典型：`D03`（外部红队）、`D26`（成果物 authz pilot，`release_blocking=true`）、`D19`（供应链）。`release_ok`/`coverage_ok` 为 false 属诚实态。
