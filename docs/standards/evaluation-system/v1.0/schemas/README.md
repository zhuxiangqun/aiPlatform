---
doc_type: Index
doc_id: EVAL_SYS_V10_SCHEMAS
status: active
purpose: 评测系统 v1.0 机读 Schema 入口
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
---

# schemas/（定稿）

| 文件 | 内容 |
|---|---|
| `evaluation-system.v1.0.schema.json` | `$defs`：Plan / Case Pack / Result / Gate / fingerprints |
| `manifest-v1.0.json` | Schema 清单 |
| `conformance-checklist.yaml` | 附录 N 机读 |
| `conformance/` | 批准记录 |
| `validate_schemas_v1.0.py` | 包完整性校验（≠ 实现认证） |

字段权威：`../normative-appendix.md`。Schema 批准 ≠ 实现 certified。

```bash
python3 docs/standards/evaluation-system/v1.0/schemas/validate_schemas_v1.0.py
```
