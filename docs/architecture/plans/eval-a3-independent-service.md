# EVAL_A3 Independent Service — 本地独立运行验证（A0 方案）

> **文档类型**：Design / Implementation Plan  
> **状态**：**A0–A6 A-local closeout PASS**（#6 本地 HS256 JWT ✅；Keycloak JWKS → B）· 2026-11-02 · [#529](https://github.com/zhuxiangqun/aiPlatform/pull/529)  

> **范围**：先证明 Evaluation **本地独立进程/DB/API**；不做生产拆分  
> **解冻**：[`ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md)  
> **A3 ADR**：[`ADR-EVALUATION-A3.md`](../../../reports/five-products/ADR-EVALUATION-A3.md)（Accepted 有条件）  
> **拆分清单**：[`SPLIT_CHECKLIST.md`](../../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md)  
> **EVAL 产品**：[`eval-v1-charter.md`](./eval-v1-charter.md)  
> **本文件不是**：生产拆分授权；`process_split_authorized` 仍为 false。

---

## 0. 一句话

**先在本地证明“评测离开 Central 也能活”，再谈 staging/生产拆分。**

```
A-local：独立进程 :8010 + 独立 DB + 独立 API + Central 停掉仍可读
B-prod ：staging + checklist + signed live → process_split_authorized=true
```

A-local **已完成**；B 需另开解冻（staging + 真实 OIDC/JWKS + checklist + signed live）。

---

## 1. 现状（A-local 后）

| 维度 | A-local 后 | 仍属 B |
|---|---|---|
| 运行 | standalone `:8010`（`run_local.sh`） | staging HA / Chart |
| 服务入口 | `packages/aiplat-evaluation/app/main.py` | 生产运维面 |
| API | canonical store 子集独立宿主；Central 可代理 | 全量 canonical + 生产切流 |
| DB | 独立 SQLite + migrations | staging PG / 生产迁移 |
| 健康 | `/healthz` `/readyz`；`process_split_authorized=false` | authorize |
| 认证 | 本地 HS256 Bearer + `tenant_id` | Keycloak JWKS |
| staging | `staging_ready=false` | B 前置 |

**结论**：本地已证明“独立运行”；生产拆分授权仍未开。

---

## 2. “独立运行”的 6 条标准

A-local 必须全部满足：

1. **独立进程**：`:8010` 启动，不依赖 Central 进程。
2. **独立 DB**：eval 自有 schema；不直读 Central/FDE/Ontology 表。
3. **独立 API**：canonical `/api/platform/apps/eval` 由 eval 服务提供；Central 只代理。
4. **独立认证**：standalone Bearer JWT（A-local：HS256）；不依赖 Central session。真实 Keycloak JWKS → B。
5. **故障域**：Central 停止后，eval 的已有报告/查询仍可用。
6. **独立运维**：可单独启动/停止/升级/回滚；有 healthz/readyz。

**注意**：A-local 仍不设 `process_split_authorized=true`；这是工程证据，不是生产授权。

---

## 3. 目标架构（A-local）

```
/eval UI
  → /api/platform/apps/eval
      → Central proxy（可选）
          → Eval Service :8010
              ├─ API (FastAPI)
              ├─ Eval Engine / Store
              ├─ eval DB (SQLite local / PG optional)
              ├─ Auth (A-local HS256 JWT; Keycloak JWKS → B)
              └─ healthz / readyz / metrics
```

### 3.1 代码布局（计划）

```text
packages/aiplat-evaluation/
  app/
    main.py              # FastAPI app + uvicorn entrypoint
    config.py            # AIPLAT_EVAL_* env
    api/                 # canonical routers
    service/             # eval logic (no core private imports)
    store/               # DB/repository/migrations
  migrations/
  tests/
  scripts/
    run_local.sh         # start :8010
    independence_check.sh
  chart/                 # local chart skeleton
```

### 3.2 数据归属

| 数据 | 归属 |
|---|---|
| eval_sets / tasks / runs / judgments / reports / gates / judges / labels | Evaluation |
| 源 run/trace/artifact | 各源产品；eval 只存 `EvidenceRef`/`ref` |
| Central 运行事实 | 不复制；只通过 API/证据引用 |

### 3.3 API

- canonical：`/api/platform/apps/eval`
- OpenAPI + `eval.protocol.v0` / report schema
- N-1 兼容
- 认证：Bearer JWT + `tenant_id` claim；无 token → 401；跨租户 → 404
- 健康：`/healthz`、`/readyz`

### 3.4 配置

| 变量 | 作用 |
|---|---|
| `AIPLAT_EVAL_SERVICE_URL` | Central 代理目标（默认空=cohost） |
| `AIPLAT_EVAL_DB_URL` | eval DB（本地 SQLite / PG） |
| `AIPLAT_EVAL_REQUIRE_AUTH` | `1`/`0`；standalone 默认要求 Bearer |
| `AIPLAT_EVAL_JWT_SECRET` / `AIPLAT_EVAL_JWT_ISSUER` | A-local HS256；B 换 JWKS |
| `AIPLAT_EVAL_PORT` | 默认 `8010` |
| `AIPLAT_EVAL_MODE` | `cohost` / `standalone` |

**Feature flag**：`AIPLAT_EVAL_MODE=standalone` 才启独立；默认 cohost，避免破坏现有部署。

---

## 4. 工作分解（A0–A5）

| 阶段 | 内容 | 交付 | 工期 |
|---|---|---|---|
| **A0** | 本方案 + 解冻 + API/DB 设计 | 本文档 | 3–5 天 |
| **A1** | 独立 FastAPI 入口 + healthz/readyz + 本地启动脚本 | `:8010` 可起 | 1 周 |
| **A2** | eval DB schema + migrations + 本地 store | 独立 DB | 1–2 周 |
| **A3** | canonical API 由独立服务提供；Central 代理/回退 | 双模式 | 1–2 周 |
| **A4** | 本地双进程独立性测试：Central down，eval 仍读 | 证据 | 3–5 天 |
| **A5** | 回滚/备份/文档/契约测试/收口 | A-local closeout | 3–5 天 |
| **A6** | 本地 Bearer JWT + `tenant_id` 隔离（401/404） | 验收 #6 | 1–2 天 |

**A-local 总工期：5–8 周**（不含 B）。**状态：A0–A6 已合入 main。**

---

## 5. 数据迁移（本地）

1. **盘点**现有 eval 表/文件/SQLite schema。
2. **导出**到独立 schema；保留 `source_id`/`created_at`/版本。
3. **回填**历史报告/评测集。
4. **对账**：数量、ID、分数、报告 hash。
5. **双读**：cohost 与 standalone 同时可读；比较结果。
6. **本地切换**：`AIPLAT_EVAL_MODE=standalone`。
7. **回滚**：切回 cohost；不删源数据。

**A-local 不做生产数据迁移**；B 才做。

---

## 6. 认证 / 租户

- **A-local（已交付）**：`app/auth.py` HS256 Bearer；`mint_local_token` 供脚本/测试；无 Central session。
- 所有 set/report 按 `tenant_id` 隔离；越权返回 **404**（非 403）。
- **B**：Keycloak JWKS / 真实 issuer；staging 用户体系。

---

## 7. A-local 验收

| # | 项 | 通过标准 |
|---|---|---|
| 1 | 独立启动 | `curl :8010/healthz` 返回 `product_id=evaluation` |
| 2 | Central 停止 | eval 的已有报告/查询仍可用 |
| 3 | 独立 DB | 报告写入 eval DB；不写 Central 表 |
| 4 | 无私有 import | eval service 不 import `core.harness` / Central 内部 |
| 5 | canonical API | `/api/platform/apps/eval` 直连/代理均可用 |
| 6 | 认证 | 无 token 401；跨租户 404 |
| 7 | 升级/回滚 | 可升级到新版本并回滚 |
| 8 | 契约 | eval protocol/report 测试绿 |
| 9 | 授权 | `process_split_authorized` **仍 false** |

**证据**：`local-eval-a3-independent-*.json`；`environment=local`；不签 production。

---

## 8. 非目标

- 不设 `process_split_authorized=true`。
- 不做 staging / production_signed / authorize。
- 不做生产数据迁移/切流。
- 不做 A3 生产 Chart/HA/备份演练（B 才做）。
- 不新开 EVAL 功能/accuracy 宣称。
- 不改变 UI 交互（现有 `/eval` 继续用）。

---

## 9. 风险与止损

| 风险 | 止损 |
|---|---|
| 仍依赖 core 私有 import | A1 起用 import guard；发现即停 |
| DB 迁移丢数据 | 先只读双跑 + 对账；不删源 |
| Central 代理破坏旧路径 | feature flag + 回退 cohost |
| 认证耦合 Central session | 直接校验 Bearer JWT；不接受平台 cookie |
| 双写不一致 | 先 dual-read，后 dual-write；有对账 |
| 范围膨胀到 B | 明确 A-local 不含 staging/authorize |
| 单人并行重轨 | A3 local 期间不新开 EVAL/Diagnosis 功能 |

**停止条件**
- eval 无法脱离 core 私有 import → 停在 A0/A1，先解耦。
- Central 停掉后 eval 不能读 → A4 失败，不宣称独立。
- 数据对账不一致 → 停切换。
- 任何 `process_split_authorized=true` 冲动 → 停，走 B。

---

## 10. B（分阶段；B0 ≠ 授权）

```
B0（本解冻）：本地 JWKS/RS256 校验路径 + fixture 测例
  → process_split 仍 false；无 staging 主机要求
B1+（另解冻）：真实 staging PG + Keycloak
  → 数据迁移/双跑/对账
  → split checklist 全 ✅
  → signed live
  → process_split_authorized=true
  → 生产切流/回滚
```

| 阶段 | 内容 | 解冻 |
|---|---|---|
| **B0** | `AIPLAT_EVAL_JWKS_JSON` / `AIPLAT_EVAL_JWKS_URL`；RS256 401 测例 | [`ENGINEERING_UNFREEZE_EVAL_A3_B0_JWKS.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B0_JWKS.md) |
| **B1+** | staging 主机、备份/PITR、HA、operator、变更窗口 | 另开；A-local/B0 完成 ≠ 可授权 |

**A-local / B0 完成 ≠ B 可授权。**

---

## 11. A0 出口 / A-local 收口

- [x] A-local 目标/边界/验收。
- [x] 独立进程/DB/API/auth 设计。
- [x] A1–A6 WBS（含本地 JWT）。
- [x] 非目标与停止条件。
- [x] 代码布局落地（`packages/aiplat-evaluation/app/`）。
- [x] 本地 DB（SQLite + migrations）；Keycloak → B。
- [x] 解冻 `ENGINEERING_UNFREEZE_EVAL_A3_LOCAL` **Closed PASS**。
- [x] A1–A6 合入 main（至 #529）；`process_split_authorized=false`。

---

## 12. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版：A-local 独立进程/DB/API 验证；B 后置；process_split 保持 false |
| 2026-11-02 | v1.1 | A0–A6 PASS：#6 本地 HS256；Keycloak JWKS 明确归 B；#529 合入 |
| 2026-11-02 | v1.2 | B0：本地 JWKS/RS256 路径解冻；仍禁止 authorize |
