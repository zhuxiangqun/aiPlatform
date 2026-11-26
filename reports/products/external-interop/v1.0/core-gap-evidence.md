---
doc_type: Report
doc_id: EXT_INTEROP_V10_CORE_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 外援互通 v1.0 附录 N Core（X01–X06）代码证据盘点；非 certified
---

# 外援互通 v1.0 — Core 差距证据（测量）

> **性质**：测量报告。  
> **刷新**：2026-11-26 收口 X01–X06（含 X02 fail-closed + X04 syscall 证据）。

## 总判定

| 问题 | 结论 |
|---|---|
| 能否宣称 `core_ready`？ | **测量态：X01–X06 均为 exists**；正式 `core_ready` 仍须非作者复核 |
| 能否宣称 `certified`？ | **否** |

## X01–X06

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| X01 Manifest + checksum | **exists** | `compute_asset_tree_checksum`；`finalize_*_compat` 写 `checksum`/`manifest.checksum` | — |
| X02 L0 解析 fail closed | **exists** | `_read_skill_manifest`；缺/坏 frontmatter → `tier=blocked` + `interop.manifest_invalid` + `half_import`；测试 `test_missing_skill_md_fail_closed_x02` | Agent/Tool 同类严格解析可 Extended 对齐 |
| X03 claimed/verified 分离 | **exists** | `enrich_compat_claim_tiers`；宣称>验证 → `tier_claim_illegal`；§C.1 映射表 | — |
| X04 PolicyGate 不绕过 | **exists** | `sys_skill_call`：`PolicyGate()`（`skill.py:102`）+ COMPAT `is_skill_schedulable`（:148-155）；`sys_tool_call`：`PolicyGate()`（`tool.py:92`）+ `is_tool_schedulable`（:124-139） | 诚实锁：PolicyGate≠handler 内容审查（compat 注释已声明） |
| X05 ImportReport + 审计 | **exists** | `wrap_install_report` | — |
| X06 半导入禁止 | **exists** | `apply_majority_import_gate`：majority-blocked 或 half_import/跳级 → failed | — |

## 复现命令

```bash
pytest aiPlat-core/core/tests/unit/test_skills/test_asset_compat_tiers_x03.py -q
rg -n 'PolicyGate|is_skill_schedulable|is_tool_schedulable' \
  aiPlat-core/core/harness/syscalls/skill.py \
  aiPlat-core/core/harness/syscalls/tool.py | head -20
```
