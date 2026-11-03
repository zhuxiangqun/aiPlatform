# OIDC / 租户最小路径 v0（本地）

> Honesty: **≠ 企业完整 realm** · **≠ staging OIDC** · `process_split_authorized=false`

## In-scope 最小可跑路径

| 路径 | 说明 | 证据 |
|------|------|------|
| A6 本地 JWT | `AIPLAT_EVAL_REQUIRE_AUTH` + HS256；无 token → 401；跨租户 → 404 | [`A_LOCAL_CLOSEOUT.md`](./A_LOCAL_CLOSEOUT.md) |
| B4-S Keycloak profile | `compose/docker-compose.b4s-local.yml` profile `keycloak`；JWKS soft probe | [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md) · `b4s_local_rehearsal.sh` |

## Gate

```bash
bash packages/aiplat-evaluation/scripts/oidc_minimal_v0_gate.sh
# 默认：文档+compose+脚本存在性；可选 AIPLAT_EVAL_OIDC_LIVE=1 拉 Keycloak JWKS
```

## Out-of-scope

完整企业 realm / HA / 生产 SLO / staging host 上的真实 IdP —— 见 SCORE_SCOPE §三 out-of-scope。
