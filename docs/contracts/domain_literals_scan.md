# Domain 字面量存量扫描报告

| 字段 | 值 |
|------|-----|
| 版本 | **v1.1（Phase 5 关闭）** |
| 扫描日期 | 2026-09-14（初扫） / **复扫 2026-09-14** |
| 范围 | `aiPlat-core/core/harness/**/*.py`（排除 `**/tests/**`） |
| 模式 | `"fde-delivery"` \| `"lock-service"` \| `"supply-chain"` |
| 关联 | `FDE_GUARD_REGISTRY_LANDING.md` §2.2；守卫 `fde_domain_literals`（**error**） |
| 签字 | Oliver Zhu / 2026-09-14 |

---

## 1. 总量（Phase 5 复扫）

| 口径 | 计数 |
|------|------|
| harness grep 命中（含 docstring/示例/排除模块） | **11** |
| AST 守卫报告（allow_if + 排除文件后） | **0** |
| 行为分叉 `domain_id == "…"` / Compare | **0** |
| 守卫 severity | **error**（CI 阻断新增） |

> AST=0 表示行为分叉与非豁免字面量已清零；grep 残留主要为 docstring/示例与已排除模块（`prompt_loader` / `domain_router` / `builtin_*` 等）。

---

## 2. 残留分类（非行为分叉）

| 分类 | 处置 | 状态 |
|------|------|------|
| 常量 / frozenset 白名单 | 保留（守卫 allow） | ✅ `PLATFORM_TRACKING_DOMAIN` / tracking frozenset |
| DomainRouter / load 调用参数 | 保留 | ✅ |
| docstring / 示例 | 改占位或 noqa（非阻断） | ⏳ 可选卫生 |
| `prompt_loader` 域键默认表 | 排除于 AST；方向仍为域 YAML `llm_prompt` | ⏳ 不阻塞 Phase 5 |
| **行为分叉** | **必须清零** | ✅ **0** |

---

## 3. 升 error 关闭项

| 条件 | 状态 |
|------|------|
| 行为分叉类 = 0 | ✅ |
| AST issues = 0 | ✅ |
| severity → error | ✅ `fde_workbench.py` `level = "error"` |
| D2 决策关闭 | ✅ 见 `FDE_DECISION_RECORD.md` |

---

## 4. 复扫命令

```bash
rg -n '"fde-delivery"|"lock-service"|"supply-chain"' aiPlat-core/core/harness \
  --glob '*.py' -g '!**/tests/**'

PYTHONPATH=aiPlat-core python3 -c "
from pathlib import Path
from core.management.arch_guard_rules.fde_workbench import FdeDomainLiteralsAstCheck
c = FdeDomainLiteralsAstCheck()
assert c.level == 'error'
print(len(c.check(Path('.'))))
"
```

---

## 5. 修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-14 | 初扫；warning 节奏 |
| v1.1 | 2026-09-14 | Phase 5：升 error；AST=0；行为分叉=0；关闭 D2 |
