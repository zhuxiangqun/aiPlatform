# EVAL 产品根 v1（monorepo · ARCH v1.4）

> Honesty: **≠** 拆独立 git 仓 · **≠** `process_split_authorized`  
> Gate: `scripts/arch_consolidation_v1_gate.sh`（检查本文件 + contracts SSOT）

## 产品根声明

| 层 | 路径 | 职责 |
|----|------|------|
| **产品根** | `packages/aiplat-evaluation/` | worker / store(adapter) / scoring / sandbox / contracts / tests / chart / compose / package.json |
| **薄 HTTP** | `aiPlat-platform/apps/eval/api/` | RBAC + 转发 CoreFacade（无业务 SQL/LLM） |
| **共享 ops** | `aiPlat-core/core/apps/eval/service/` | 平台进程内 eval ops（kb/prompt/runs/skill/store）；**非**第二产品根 |
| **Central 遗留计分** | `core/harness/evaluation/` | `legacy_7dim` report-only；`deprecated_for_engineering=true` |

## 完成判定（首版架构 in-scope）

1. Contracts SSOT 仅在 package（reports 无 JSON 副本）  
2. HTTP 仅 canonical `/api/platform/apps/eval`（legacy 308）  
3. platform eval API 无 sqlite3 / 无厚业务  
4. CODEOWNERS 覆盖 package + reports shim  
5. `npm run release:check`（`package_release_check.sh`）可本地跑通  

拆仓 / 进程拆分 **不是** 本文件完成条件。
