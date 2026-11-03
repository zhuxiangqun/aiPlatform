# EVAL 架构收口 v1（相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md) §二）

> Gate: `scripts/arch_consolidation_v1_gate.sh`  
> Honesty: **≠** `process_split_authorized` · **≠** 拆仓必要条件 · 本切片只冻结 + 防回潮

## 目标（首版架构 5/5）

| # | 条件 | v1 本切片 |
|---|------|-----------|
| 1 | 单一 canonical API `/api/platform/apps/eval` | ✅ 已挂；legacy 双挂仍在（见下） |
| 2 | Legacy 仅 shim / Deprecation | ✅ Middleware；❌ 尚未卸 `/api/platform/apps` 双挂 |
| 3 | Contracts SSOT = package | ⚠️ 部分；Central legacy_7dim 仍并存（[`P1_CANONICAL.md`](./P1_CANONICAL.md)） |
| 4 | 产品根 package | ⚠️ API 业务仍在 `platform/apps/eval/api/*` |
| 5 | platform 薄适配 | ❌ `prompt_eval` 等仍含业务 SQL/LLM |
| 6 | core 无 eval 专属业务层 | ⚠️ `core/apps/eval/service/*` + `core/api/routers/kb_eval.py` 残留 |
| 7 | 独立 build/test/release | ⚠️ package 可测；完整 release 未钉 |

## 当前拓扑（代码事实）

```
Clients
  ├─ /api/platform/apps/eval/*     ← CANONICAL（EvalLegacyDeprecation 不打 Deprecation）
  ├─ /api/platform/apps/{kb-eval,code-review-gold,...}  ← 同 router 双挂 + Deprecation headers
  └─ /api/core/{kb-eval,evaluation} ← core 残留 + EvalCoreLegacyDeprecationMiddleware

platform/apps/eval/api/*  ← 仍有业务实现（非纯转发）
packages/aiplat-evaluation/app/*  ← Worker/store/scoring canonical（独立进程路径）
core/apps/eval/service/* + harness evaluation ← Central AgentEvalResult legacy_7dim
```

证据：

- 双挂：`aiPlat-platform/api/rest/routes.py` `include_router(.../eval)` + `include_router(.../apps)`
- Shim：`aiPlat-platform/apps/eval/api/legacy_shim.py` · `aiPlat-core/core/api/routers/eval_legacy_shim.py`
- 计分双路径：`packages/.../app/scoring/composite.py` vs `core/harness/evaluation/eval_types.py` `legacy_7dim`

## Freeze（本切片强制）

1. **禁止新增** `aiPlat-core/core/api/routers/*eval*` 文件（基线仅允许已有：`kb_eval.py`、`eval_legacy_shim.py`）。
2. **禁止**再增加第三处 `eval_platform_router` `include_router`（基线恰好 2：canonical + legacy flat）。
3. **禁止**新代码把 Central `legacy_7dim` 标成 engineering canonical（P1 仍以 package `build_composite` 为准）。
4. 新 eval HTTP 能力必须挂在 **`/api/platform/apps/eval`**；若不得不加 legacy 别名，必须走 Deprecation middleware 可检测路径。

## v1.1 进度（本仓步进）

| 模块 | 状态 |
|------|------|
| `platform/.../kb_eval.py` | ✅ 已变薄 → `core.apps.eval.service.kb_eval_ops` + CoreFacade |
| `code_review_gold.py` / `arena_wiring.py` | ✅ 已是 CoreFacade 薄路由 |
| `prompt_eval.py` / `skill_evals.py` / `runs_eval.py` | ❌ 仍厚（sqlite / 大业务） |
| platform `sqlite3` allowlist | 仅 `prompt_eval.py`（gate 强制） |

## 后续切片

| 切片 | 内容 |
|------|------|
| v1.1b | 下沉 `prompt_eval` / `runs_eval` / `skill_evals` |
| v1.2 | 卸 flat mount（或只留显式 redirect 表）；core `kb_eval` stub 可删 |
| v1.3 | contracts 单包 SSOT + CODEOWNERS + package release |

## 非目标

- 不设 `process_split_authorized=true`
- 不要求拆独立 git 仓
- 不静默重加权 Central historical grades
