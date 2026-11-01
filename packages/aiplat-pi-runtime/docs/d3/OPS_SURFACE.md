# Pi D3 — 运维面约定（本地完备 · 生产待签）

> **本地**：文档 + healthz 契约 + D1 smoke。  
> **生产**：SLA / 值班面证据另见 live 演练。

## 约定

1. `GET /healthz` 保持 `product_id=pi` · `deploy_unit=edge`（D1 契约不可破）。  
2. D3 可附加只读字段（如 `admin_pack` / `d3_prep`），不得删除 D1 必填。  
3. 证据/日志默认驻留设备；上云仅 enterprise opt-in。  
4. 告警出口不得在 `AIPLAT_ENTERPRISE=0` 时强制外联（见 `d3_soc_local_rehearsal.sh`）。  
5. N-1 升级/回滚操作面：`d1_upgrade.sh` / `d1_rollback.sh`（D3 本地收口：`d3_n1_local_rehearsal.sh`）。

## 本地验证

```bash
bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh
bash packages/aiplat-pi-runtime/scripts/d3_local_closeout.sh
```

Checklist #4 本地 = **🟨**（≠ 生产 ✅）。
