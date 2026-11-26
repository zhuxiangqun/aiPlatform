---
doc_type: Index
doc_id: EVAL_SYS_V10_CONFORMANCE
status: active
purpose: 评测系统 v1.0 符合性资产说明
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
---

# Conformance（评测系统 v1.0）

本目录是**标准符合性参考资产**，不是已部署实现的认证证明。

- `approval-record-v1.0.pending.json` — 历史 pending
- `approval-record-v1.0.approved.json` — 标准包已批准（生效 2026-12-01）

```bash
python3 docs/standards/evaluation-system/v1.0/schemas/validate_schemas_v1.0.py
```

**诚实边界**：标准批准 ≠ `core_ready` 正式签字 ≠ `certified`。
