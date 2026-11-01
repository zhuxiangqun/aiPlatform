# EVAL_V1 E1 — Eval API surface inventory

- recorded_at: `2026-11-01`
- charter: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md)
- unfreeze: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)

## Finding

`registry/apps.yaml` 声明 `api_prefix: /api/platform/apps/eval`，但历史挂载为：

```text
app.include_router(eval_platform_router, prefix="/api/platform/apps")
```

因此真实路径落在 `/api/platform/apps/{kb-eval|code-review-gold|skill-evals|…}`，**缺少 `/eval` 段**。

## Platform surfaces（canonical 目标前缀 `/api/platform/apps/eval`）

| Module | Legacy path (shim) | Canonical path |
|--------|--------------------|----------------|
| kb_eval | `/api/platform/apps/kb-eval/*` | `/api/platform/apps/eval/kb-eval/*` |
| code_review_gold | `/api/platform/apps/code-review-gold/*` | `/api/platform/apps/eval/code-review-gold/*` |
| skill_evals | `/api/platform/apps/skill-evals/*` | `/api/platform/apps/eval/skill-evals/*` |
| prompt_eval | `/api/platform/apps/prompts/eval/*` | `/api/platform/apps/eval/prompts/eval/*` |
| runs_eval | `/api/platform/apps/runs/{id}/evaluate*` | `/api/platform/apps/eval/runs/{id}/evaluate*` |
| arena_wiring | `/api/platform/apps/arena/*`, `/wake-agent/*` | under `/eval/…` |

Mount: `aiPlat-platform/api/rest/routes.py` · router: `apps/eval/api/router.py`.

## Core legacy（shim / stub）

| Path | File | Note |
|------|------|------|
| `/api/core/kb-eval/*` | `core/api/routers/kb_eval.py` | stub / Not Implemented；FE vite 曾直指 core |
| `/api/core/evaluation/*` | `core/api/routers/compat.py` | LearningManager overview/policy；暂无 platform 对等资源 |

## E1 actions

1. Dual-mount eval router：canonical `/api/platform/apps/eval` + legacy `/api/platform/apps`.
2. Legacy 响应加 `Deprecation` + `Link` successor（指向 `/eval/…`）。
3. Core `kb-eval` 加 deprecation 指向 platform canonical；vite 代理改写到 platform（非 UI 页）。
4. 契约测试：canonical 可达；legacy 带 deprecation 头。
5. `compat` `/evaluation/*` 仅标记 deprecation（E2+ 再迁 overview）。

## Non-goals (E1)

- 不改 UI 页面；不迁 Learning overview 实现；不碰 A3/authorize。
