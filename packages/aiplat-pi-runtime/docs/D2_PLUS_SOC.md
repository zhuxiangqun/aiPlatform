# Pi D2++ — deeper SOC（本地深化 · 非生产授权）

> **冻结 Still open**：允许文档/本地 file-sink 深化；不打开 `d3_production_authorized`。  
> 生产 SOC 出口仍见 D3 checklist #5 与 [`d3/LIVE_DRILL_EVIDENCE.md`](./d3/LIVE_DRILL_EVIDENCE.md)。

## 已有（D3 local）

- `d3_soc_local_rehearsal.sh` — file-sink only，enterprise opt-in  
- checklist #5 本地 → 🟨  

## D2++ 本地加深（本文件范围）

| 项 | 说明 | 状态 |
|----|------|------|
| 事件 schema 固定字段 | `kind` / `severity` / `actor` / `environment=local` | ✅ `d3_soc_local_rehearsal` 写出 + `d2_soc_deeper_check` 硬核 |
| 默认外联关闭 | `AIPLAT_ENTERPRISE=0` 时无强制 webhook；证据禁 HTTP(S) | ✅ |
| 与 D2 admin 关系 | D2++ 不替代 `d2_admin_check`；叠加证据 | ✅ |

```bash
bash packages/aiplat-pi-runtime/scripts/d3_soc_local_rehearsal.sh
bash packages/aiplat-pi-runtime/scripts/d2_soc_deeper_check.sh
```

## 非目标

- 真实 SIEM/webhook 出口（须 staging live）  
- checklist 🟨→✅  
- `d3_authorize` 成功路径  
