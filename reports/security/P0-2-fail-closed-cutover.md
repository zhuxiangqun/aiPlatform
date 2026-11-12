---
generated_at: 2026-11-11
doc_type: Report
---

# P0-2：Policy fail-closed 灰度切流（Ops）

> 配套：改进方案 §1.1 · `scripts/security_ops_audit.py`  
> **验收**：故障时真拒绝 + 配置审计可证明；**≠** `security_certification`

---

## 1. 目标状态

| 环境 | `AIPLAT_PROFILE` | 未设 `AIPLAT_POLICY_FAIL_MODE` 时 | 显式 `open` |
|---|---|---|---|
| production / staging / preprod | 必须设置 | **closed** | 必须带未过期 `AIPLAT_POLICY_FAIL_OPEN_UNTIL` |
| development / local | 可选 | ask | 允许（开发逃生） |
| 未设 profile | — | open（兼容） | — |

相关 env：

- `AIPLAT_PROFILE` / `AIPLAT_ENV`
- `AIPLAT_POLICY_FAIL_MODE` = `open|ask|closed`
- `AIPLAT_POLICY_FAIL_OPEN_UNTIL` = ISO-8601（prod/staging 开 open 的白名单窗）
- `AIPLAT_HARD_FLOOR_DISABLED` + `AIPLAT_HARD_FLOOR_DISABLED_UNTIL`（逃生须有窗）

---

## 2. 切流前（本地/CI 干跑）

```bash
# 期望矩阵应全 ok（closed/ask/open-with-until）
python3 scripts/security_ops_audit.py --profile-matrix

# 当前进程环境快照（advisory）
python3 scripts/security_ops_audit.py
```

---

## 3. 预发 → 生产步骤

1. **预发**设 `AIPLAT_PROFILE=staging`（勿留空）。  
2. 重启平台进程后跑：`python3 scripts/security_ops_audit.py` → `fail_closed.ok=true`。  
3. **故障注入验收**（预发）：人为让 PolicyGate 依赖短暂失败，确认 critical 路径 **拒绝**（closed）而非静默放行；保留审计日志。  
4. **生产**同样设 `AIPLAT_PROFILE=production`；禁止无 UNTIL 的 fail-open。  
5. 若临时 open：写变更单 + `AIPLAT_POLICY_FAIL_OPEN_UNTIL=<未来 ISO>`；到期自动回落 closed。  
6. 勾选本清单前：Owner 在变更系统留「预发故障拒绝 + 生产 profile 审计」证据链接。

---

## 4. 回滚

| 症状 | 动作 |
|---|---|
| 误开 open 无窗 | unset `AIPLAT_POLICY_FAIL_MODE` 或补 UNTIL；重启 |
| 过严导致业务中断 | 短期 open **必须**带 UNTIL + 变更单；事后复盘 |
| hard-floor 误关 | unset `AIPLAT_HARD_FLOOR_DISABLED*` |

---

## 5. 诚实锁

- `--profile-matrix` 通过 ≠ 生产已切流。  
- 本文件勾选 ≠ 安全认证。  
- 生产证据须来自真实 env 审计 + 故障拒绝记录。
