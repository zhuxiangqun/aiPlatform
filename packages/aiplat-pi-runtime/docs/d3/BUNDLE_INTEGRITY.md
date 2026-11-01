# Pi D3 — Bundle 完整性（本地完备 · 生产待签）

> **本地**：`d3_local_rehearsal.sh` 可重复验证。  
> **生产**：须 staging/prod-canary live + 运维签字后 checklist #3 → ✅（见 [`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md)）。

## 策略

1. 安装/升级前校验 `agent_manifest.json` 存在与必填字段。  
2. 对 Bundle 目录写入 `SHA256SUMS`；切换 `bundles/current` 前校验。  
3. 校验失败：拒绝切换；保留上一版本指针。  
4. 离线可关严格校验（配置项，默认演练开启）。  

## 本地证据

```bash
bash packages/aiplat-pi-runtime/scripts/d3_local_rehearsal.sh
# → docs/d3/drills/local-rehearsal-*.json
#   bundle_checksum / corruption_detected / rollback_pointer
```

Checklist #3 本地 = **🟨**（≠ 生产 ✅）。
