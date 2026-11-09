# 安全质量 25 维覆盖（人读摘要）

> **唯一真相源**：[security_quality_dimensions.yaml](./security_quality_dimensions.yaml)  
> Crosswalk：[docs/security/security-dimension-crosswalk.md](../../docs/security/security-dimension-crosswalk.md)  
> 报告：`python3 scripts/security_dimensions_report.py`

## 字段含义

| 字段 | 含义 |
|---|---|
| `schema_ok` | YAML 可解析、恰 25 维、字段合法；**E 必须含 ≥1 条 V/T**（仅 D → schema 失败，禁止静默降级） |
| `coverage_ok` | 所有 `p0: true` 维无 `G`；O 有 owner+日期 |
| `security_certification` | 恒 false |

```text
E = evidence verified (code/test)
I = implemented, not independently verified
O = owned but open
G = gap / unowned
```

## 诚实锁

- `schema_ok=true` ≠ 安全覆盖通过。
- `coverage_ok=true` ≠ 认证。
- `--strict-gaps` 仅用于**发布门**（PR3 接线）；默认 CI 工程收口只要求 `schema_ok`。

## 当前缺口（摘要）

以 YAML 为准；典型 P0 `G`：独立验证（D03）。其余 P0 多为 I/O（威胁模型、跨租户、隔离真证、IR 演练等）。
