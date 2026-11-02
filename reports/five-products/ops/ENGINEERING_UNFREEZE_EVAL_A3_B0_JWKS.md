# Engineering unfreeze — EVAL_A3 B0（本地 JWKS / RS256）

- **decided_at**: `2026-11-02`
- **status**: **Active** — B0 local JWKS only
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md`](./ENGINEERING_UNFREEZE_EVAL_A3_LOCAL.md) Closed PASS
- **plan**: [`eval-a3-independent-service.md`](../../../docs/architecture/plans/eval-a3-independent-service.md) §10
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **production**: 仍冻结（`process_split_authorized=false` / `staging_ready=false` / authorize 禁止）

## 一句话

只解冻「standalone 能校验 RS256 JWKS JWT」的工程证据；**不解冻** staging / Keycloak 集群 / 生产拆分授权。

## 允许

| 允许 | 禁止 |
|---|---|
| `AIPLAT_EVAL_JWKS_JSON` / `AIPLAT_EVAL_JWKS_URL` 校验路径 | `process_split_authorized=true` |
| 本地/fixture RS256 签发与 401 测例 | staging_ready / production_signed / authorize |
| 文档与 CAPABILITIES 登记 | 真实 Keycloak 部署宣称 / 生产切流 |
| HS256 路径保留（A6 默认） | 静默开 B1+（staging PG / live drill） |

## 允许的代码面

- `packages/aiplat-evaluation/app/auth.py`（及直接调用方）
- `packages/aiplat-evaluation/tests/test_b0_*.py`
- 对应 ops/plan 文档行

## 退出条件

| 结果 | 动作 |
|---|---|
| JWKS fixture 接受合法 RS256；错误 kid/issuer → 401 | B0 closeout；**不**自动进 B1 |
| 仍只能 HS256 | B0 失败；不宣称 OIDC 就绪 |
| 范围到 staging/authorize | 停；另开 B1 解冻 |

## Outcome

- **In progress / shipping** — `jwks_enabled` + `AIPLAT_EVAL_JWKS_JSON` RS256 path；bad kid/issuer → 401；`process_split_authorized=false`。
