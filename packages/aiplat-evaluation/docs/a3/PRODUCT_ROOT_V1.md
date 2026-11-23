---
doc_type: Reference
---

# EVAL 产品根 v1（monorepo · ARCH v1.4）

> Honesty: **≠** 拆独立 git 仓 · **≠** `process_split_authorized`  
> Gate: `scripts/arch_consolidation_v1_gate.sh`（检查本文件 + contracts SSOT）

## 产品根声明

| 层 | 路径 | 职责 |
|----|------|------|
| **产品根** | `packages/aiplat-evaluation/` | worker / store(adapter) / scoring / sandbox / contracts / tests / chart / compose / package.json |
| **薄 HTTP** | `aiPlat-platform/apps/eval/api/` | RBAC + 转发 CoreFacade（无业务 SQL/LLM） |
| **共享 ops** | `aiPlat-core/core/apps/eval/service/` | 平台进程内 eval ops（kb/prompt/runs/skill/store）；**非**第二产品根；维护 UI 全量 store 仍在此 |
| **Central 遗留计分** | `core/harness/evaluation/` | `legacy_7dim` report-only；`deprecated_for_engineering=true` |
| **计分/Claim 口径地图（对外 SSOT）** | [`SCORING_AND_CLAIM_MAP.md`](./SCORING_AND_CLAIM_MAP.md) | package composite vs legacy；scoped≠product `accuracy_claim` |
| **Store 诚实面** | [`STORE_SURFACE_V0.md`](./STORE_SURFACE_V0.md) | standalone API = sets/reports/jobs；schema 8 实体为 forward shape |
| **G2b 改判** | [`G2B_RE_REVIEW_PROCEDURE.md`](./G2B_RE_REVIEW_PROCEDURE.md) | 预注册重审规程；不自动开 accuracy_claim |
| **P2 staging 总览** | [`P2_STAGING_ROADMAP.md`](./P2_STAGING_ROADMAP.md) | P0/P1 之后 → host → live → authorize；`ready_to_authorize` 仍 false |

## 完成判定（首版架构 in-scope）

1. Contracts SSOT 仅在 package（reports 无 JSON 副本）  
2. HTTP 仅 canonical `/api/platform/apps/eval`（legacy 308）  
3. platform eval API 无 sqlite3 / 无厚业务  
4. CODEOWNERS 覆盖 package + reports shim  
5. `npm run release:check`（`package_release_check.sh`）可本地跑通  

拆仓 / 进程拆分 **不是** 本文件完成条件。
