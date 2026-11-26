---
doc_type: Report
doc_id: EXT_INTEROP_V10_EXT_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 外援互通 v1.0 附录 N Extended（X07–X09）代码证据盘点；非 certified
---

# 外援互通 v1.0 — Extended 差距证据（测量）

> **性质**：测量报告。  
> **刷新**：2026-11-26 Extended X07–X09 收口后。

## 总判定

| 问题 | 结论 |
|---|---|
| X07–X09 测量 | **exists** |
| 正式 extended_ready / certified | **否** |

## X07–X09

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| X07 L1 沙箱试调用 | **exists** | `run_l1_sandbox_trial`；`skill_run_l1_sandbox_trial`；`test_asset_compat_x07_x08.py` | 真隔离 microVM 属 Operational |
| X08 L2 语义探针 | **exists** | `set_semantic_probe_result` 显式；禁自动升 L2 | — |
| X09 资产目录 UX | **exists** | `build_interop_asset_catalog` / `normalize_interop_catalog_row`；Workspace Skills/Agents/Tools/MCP 可用性列展示 claimed/verified tip；`test_asset_compat_x09_catalog.py` | 独立 Catalog 页未单开（目录能力已在四工作区列表） |

## 复现命令

```bash
pytest aiPlat-core/core/tests/unit/test_skills/test_asset_compat_x07_x08.py \
  aiPlat-core/core/tests/unit/test_skills/test_asset_compat_x09_catalog.py -q
```
