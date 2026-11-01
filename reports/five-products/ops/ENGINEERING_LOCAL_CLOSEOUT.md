# 工程侧 Local Staging 收口（2026-11-01）

> **范围**：零预算 `environment=local` 演练。  
> **非范围**：`staging_ready`、`production_signed`、任何 `*_authorize` 成功路径。

## 结论

| 维度 | 状态 |
|------|------|
| PG/HA local staging + OIDC | **PASS** · `local_signed` |
| Ontology A3 local | **PASS** · `local_signed` |
| Evaluation A3 local | **PASS** · `local_signed` |
| Pi D3 local | **PASS** · `local_signed`（本收口纳入） |
| Pi D1 hermetic regression | **PASS**（另见 `PI_D1_LOCAL_REGRESSION.md`） |
| Pi D2 admin pack | **PASS**（`PI_D2_ADMIN_LOCAL.md` · enterprise 默认 off） |
| FDE Field D1 install/meta/backup/rollback | **PASS**（`FDE_FIELD_LOCAL_REGRESSION.md` · `INSTALL_META` 已生成） |
| STATUS↔manifest sync | **PASS**（`scripts/check_five_products_status_sync.py`） |
| 四轨 `ready_to_authorize` | **false** |
| 硬门 cutover / process_split / d3_production | **false** |

工程路径在 local 级别已可重复验证；**不能**据此宣称生产切流/拆分/D3 就绪。

## 复跑

```bash
bash scripts/ops_local_rehearse_tracks.sh
# 含 Docker PG+Keycloak：
AIPLAT_LOCAL_INCLUDE_PGHA=1 bash scripts/ops_local_rehearse_tracks.sh
bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh
bash packages/aiplat-fde/scripts/d1_local_regression.sh
bash scripts/ops_live_status.sh --json   # 期望全部 ready_to_authorize=false
```

## 下一步（非本收口）

1. 真实预发：[`STAGING_READY.md`](./STAGING_READY.md) → `staging_ready=true`  
2. 按 [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) live → sign → authorize  
3. 复审日：[`LOCAL_DEFER.md`](./LOCAL_DEFER.md) **2026-11-08**

## 禁止回退

- 用 `local_signed` 冒充 `production_signed`  
- 手改 checklist 🟨→✅  
- 假造 staging DSN/OIDC  
