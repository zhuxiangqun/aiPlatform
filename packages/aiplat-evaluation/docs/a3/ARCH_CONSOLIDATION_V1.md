---
doc_type: Reference
---

# EVAL 架构收口 v1（相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md) §二）

> Gate: `scripts/arch_consolidation_v1_gate.sh`  
> Honesty: **≠** `process_split_authorized` · **≠** 拆仓必要条件 · 本切片只冻结 + 防回潮

## 目标（首版架构 5/5）

| # | 条件 | v1 本切片 |
|---|------|-----------|
| 1 | 单一 canonical API `/api/platform/apps/eval` | ✅ 单挂 |
| 2 | Legacy 仅 shim / Deprecation | ✅ Middleware **308 redirect**（无业务双挂） |
| 3 | Contracts SSOT = package | ✅ `packages/aiplat-evaluation/contracts/`；reports 仅 shim |
| 4 | 产品根 package | ✅ [`PRODUCT_ROOT_V1.md`](./PRODUCT_ROOT_V1.md)（monorepo 声明；ops 在 core service = 共享层，非第二产品根） |
| 5 | platform 薄适配 | ✅ kb/prompt/runs/skill 已薄 |
| 6 | core 无 eval 专属业务层 | ✅ 无 HTTP 业务层；`service/*` = 共享 ops；**core `kb_eval` stub 已删**；Central = `deprecated_for_engineering` |
| 7 | 独立 build/test/release | ✅ `package.json` + `release:check` + CODEOWNERS（完整外部 release 未钉） |

## 当前拓扑（代码事实）

```
Clients
  ├─ /api/platform/apps/eval/*     ← CANONICAL（唯一业务 mount）
  ├─ /api/platform/apps/{kb-eval,…} ← 308 → canonical（EvalLegacyDeprecationMiddleware）
  └─ /api/core/kb-eval/*            ← 308 → canonical（EvalCoreLegacyDeprecationMiddleware）

platform/apps/eval/api/*  ← 薄 HTTP + RBAC → CoreFacade
packages/aiplat-evaluation/app/*  ← Worker/store/scoring canonical
core/apps/eval/service/* + harness evaluation ← Central AgentEvalResult legacy_7dim
```

证据：

- 单挂：`aiPlat-platform/api/rest/routes.py` `include_router(.../eval)` **恰好 1**
- Redirect：`apps/eval/api/legacy_shim.py` · `core/api/routers/eval_legacy_shim.py`
- 计分双路径：`packages/.../app/scoring/composite.py` vs `core/harness/evaluation/eval_types.py` `legacy_7dim`

## Freeze（本切片强制）

1. **禁止新增** `aiPlat-core/core/api/routers/*eval*` 文件（基线仅允许：`eval_legacy_shim.py`）。
2. **禁止**再增加第二处 `eval_platform_router` `include_router`（基线恰好 **1**：canonical only）。
3. **禁止**新代码把 Central `legacy_7dim` 标成 engineering canonical（P1 仍以 package `build_composite` 为准）。
4. 新 eval HTTP 能力必须挂在 **`/api/platform/apps/eval`**；legacy 别名只允许经 redirect middleware（显式表）。

## v1.1 / v1.2 进度

| 模块 | 状态 |
|------|------|
| `platform/.../kb_eval.py` | ✅ 薄 → `kb_eval_ops` + CoreFacade |
| `platform/.../prompt_eval.py` | ✅ 薄 → `prompt_eval_ops` + CoreFacade |
| `code_review_gold.py` / `arena_wiring.py` | ✅ CoreFacade 薄路由 |
| `platform/.../runs_eval.py` | ✅ 薄 → `runs_eval_ops` + CoreFacade |
| `platform/.../skill_evals.py` | ✅ 薄 → `skill_evals_ops` + CoreFacade |
| platform `sqlite3` | ✅ **清零** |
| flat mount | ✅ **卸除**（308 redirect 表） |
| core `kb_eval.py` stub | ✅ **已删** |
| contracts SSOT | ✅ package；reports JSON 清零 |
| CODEOWNERS / release:check | ✅ |

## 后续切片

| 切片 | 内容 |
|------|------|
| v1.1c | 下沉 `runs_eval` / `skill_evals` — ✅ |
| v1.2 | 卸 flat mount + 删 core kb_eval stub — ✅ |
| v1.3 | contracts 单包 SSOT + CODEOWNERS + package release — ✅ |
| v1.4 | PRODUCT_ROOT_V1 + `deprecated_for_engineering` + scorecard **5.0** — ✅ |

## 非目标

- 不设 `process_split_authorized=true`
- 不要求拆独立 git 仓
- 不静默重加权 Central historical grades
