# HA failover

1. 探测主库不可用  
2. 提升备库 / 切换 VIP  
3. 应用重连；确认租户读写  
4. 回切演练：主库恢复后按运维窗口回切  

**未记录 failover 演练：禁止宣称 HA 生产就绪。**

## 本地 ephemeral 演练（🟨，非生产）

逻辑 dump 模拟主→备切换与回切（**无** streaming replication / VIP / Patroni）：

```bash
bash packages/aiplat-central/scripts/pg_ha_ha_failover_rehearsal.sh
# 跳过：AIPLAT_PG_HA_SKIP_DOCKER=1
```

产出：`docs/pg_ha/drills/ha-rehearsal-*.json`；checklist **#4 → 🟨**；`cutover_authorized` 仍 false。  
生产类 live HA 仍须按本节 1–4 单独记录。
