# Pi D3 — 运维面约定（骨架）

1. `GET /healthz` 保持 `product_id=pi` · `deploy_unit=edge`。  
2. D3 可附加只读字段（如 `admin_pack` / `d3_prep`），不得破坏 D1 契约必填。  
3. 证据/日志默认驻留设备；上云仅 enterprise opt-in。  
4. 告警出口不得在 `AIPLAT_ENTERPRISE=0` 时强制外联。  
