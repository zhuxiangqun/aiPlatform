# aiPlat Control Plane v0（草案）

> Capability: **aiplat** · Central host · A1  
> Schema: `contracts/schemas/control_plane.schema.json` + `healthz.schema.json`

## 目标

宿主控制面最小交换：`bundle` / `identity` / `tenant` / `policy` / `run` / `status`。  
平台经 **CoreFacade** 访问 core；托管 Ontology / Evaluation，不吞其内部。

## v0 信封

| 字段 | 含义 |
|------|------|
| `schema_version` | 固定 `aiplat.control.v0` |
| `kind` | bundle \| identity \| tenant \| policy \| run \| status |
| `payload` | kind 正文 |
| `tenant_id` | 租户 |
| `refs` | 外部引用 |

## 非目标

- 不取代 Ontology / Eval / FDE 权威契约  
- PG/HA / 多租户进程拆分需 ADR  

## 验证

```bash
python3 reports/five-products/modules/aiplat/contracts/validate_sample.py
```
