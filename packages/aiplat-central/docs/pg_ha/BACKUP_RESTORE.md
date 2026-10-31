# PG 备份 / 恢复

- 日备：`pg_dump` / 快照（运维选定）  
- 恢复：新实例 restore → 连接串切换 → 冒烟 `/api/core/healthz`  
- RPO/RTO：由运维在切流前填入 `CUTOVER_CHECKLIST.md`
