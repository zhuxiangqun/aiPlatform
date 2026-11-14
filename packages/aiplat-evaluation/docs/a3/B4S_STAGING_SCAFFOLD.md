---
doc_type: Reference
---

# B4-S staging scaffold（≠ authorize）

> Unfreeze draft：[`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md) · `status=draft_blocked`  
> Template：[`templates/live-scaffold-b4s-staging-template.v0.json`](./templates/live-scaffold-b4s-staging-template.v0.json)  
> Live evidence 写入 `docs/a3/drills/`（gitignore；≠ 本模板）  
> Parent prep：[`B4S_PREP.md`](./B4S_PREP.md) · local runbook：[`B4S_RUNBOOK.md`](./B4S_RUNBOOK.md)

## scaffold ≠ authorize

| | Scaffold（本页） | Staging authorize |
|---|---|---|
| `environment` | `scaffold` | `staging` / `prod-canary` |
| `production_signed` | **false** | **true**（签完） |
| Chart `a3_process_split_authorized` | **false** | 仅 authorize 后 true |
| 独立 host | 未确认 | 已确认 |
| 本机 Docker B4-S | 可继续（≠ 本页证据） | 不可替代 |

## Host confirmation checklist（D2）

1. Separate VM/cluster（非开发本机）+ 持久盘  
2. PG PITR / base backup + restore 窗口  
3. JWKS IdP 可达  
4. Object store（MinIO/S3）可达  
5. 与 prod Central DB 网络隔离  

全部 ✅ 后：owner 改 unfreeze `status=active`，再填模板并跑 live。

## Sequence

1. Confirm host（本清单）  
2. Activate [`ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING.md)  
3. Fill / emit template（仍可 scaffold 直到 live）  
4. On real host：JWKS + object store + PITR backup/restore/rollback → sign live  
5. Only then：`bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize`

```bash
# Refresh unsigned template (refuses staging / production_signed without proof):
python3 packages/aiplat-evaluation/scripts/b4s_staging_scaffold_emit.py

# Must stay false until signed staging live:
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
```
