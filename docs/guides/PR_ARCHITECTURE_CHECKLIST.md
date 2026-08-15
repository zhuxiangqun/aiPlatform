# PR Architecture Checklist

> 架构契约门禁要求：本文件必须存在（`.github/workflows/aiplat-contracts-guard.yml` 检查 `test -f`）。
> 每次 PR 合并前，对照以下清单逐项确认架构边界未被破坏。

## 1. 依赖方向（单向链）

- [ ] `aiPlat-app → aiPlat-platform → aiPlat-core → aiPlat-infra` 未被违反
- [ ] platform 未直接 `from core.apps.*` / `from core.harness.*`（必须经 CoreFacade）
- [ ] core 未 import platform/app
- [ ] infra 未被任何层反向依赖

## 2. 内核无关（Kernel-Agnostic）

- [ ] `core/harness/` 无业务角色名/阶段名/artifact key 硬编码
- [ ] 引擎行为分叉来自 `PipelineStageConfig` 字段，非 `if agent_id ==`
- [ ] 新增 prompt 走 `prompt_loader`，不在代码内嵌多行字符串

## 3. 接线完成度

- [ ] 新建文件有 ≥1 个非测试生产调用者
- [ ] 新增能力登记 `AIPLAT_CAPABILITIES.md` + `capability_registry.yaml`
- [ ] 无 `# TODO: wire` 死代码标记

## 4. 能力登记同步

- [ ] `python3 scripts/sync_registry_to_docs.py` 通过（registry ↔ docs 无漂移）
- [ ] `python3 scripts/verify_capability_consistency.py` 通过（三口径一致）
- [ ] `bash scripts/verify_doc_sync.sh --ci` 通过

## 5. 宪法测试

- [ ] `python3 -m pytest tests/constitution/` 全绿（0 failed）
- [ ] `bash scripts/architecture_guard.sh --quick` 无 FAIL

---

*由 aiplat-contracts-guard.yml CI 强制检查文件存在性；内容由 PR 作者对照核验。*
