---
doc_type: Index
doc_id: FDE_SYS_V10_SCHEMAS
status: active
purpose: FDE 系统 v1.0 机读 Schema 入口
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
---

# schemas/（定稿）

| 文件 | 内容 |
|---|---|
| `fde-system.v1.0.schema.json` | signoff request/record / delivery artifact |
| `manifest-v1.0.json` | Schema 清单 |
| `conformance-checklist.yaml` | 附录 N 机读 |
| `conformance/` | 批准记录 |
| `validate_schemas_v1.0.py` | 包完整性校验 |

字段权威：`../normative-appendix.md`。部署边界仍受 ADR-09 约束。

```bash
python3 docs/standards/fde-system/v1.0/schemas/validate_schemas_v1.0.py
```
