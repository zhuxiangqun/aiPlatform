# E3 复核 — 维护区断链修复（2026-10-23）

> E2 扩面后暴露 **7** 条 fail 断链；修链优先，0 删除。

| 源 | 原链接 | 裁定 |
|----|--------|------|
| `manuals/getting-started.md` | `api-reference.md` | → `../API/api-reference.md` |
| `knowledge-system.md` | `architecture/memory-lifetime-and-model-lock.md` | 目标未落地 → `system-architecture-contract.md` + CAPABILITIES/`task_model_lock` |
| `manuals/development.md` | `../TESTING_GUIDE.md` | → `testing.md` |
| `manuals/development.md` | `../UI_DESIGN.md` ×2 | → `../design/ui-design.md` + `ui-implementation-status.md` |
| `architecture/execution-decision-matrix.md` | `fixtures/completion_receipt_vectors.json` | 未落地 → `test_completion_receipt.py` + `completion_receipt.py` |
| 同上 | `memory-lifetime-and-model-lock.md` | → `system-architecture-contract.md` Sticky 行 |

旁路：`execution_seal.py` docstring、`packages/.../HYBRID_ENTERPRISE.md` 同向修链。

**验收**：`python3 scripts/verify_doc_links.py` → fail broken = 0。
