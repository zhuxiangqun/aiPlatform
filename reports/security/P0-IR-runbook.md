---
doc_type: Report
---

# P0-IR：基本事件响应（止损卡）

> 改进方案 v2.2 · P0-IR（非完整 IR 演练；演练在 P1-IR）  
> 目标：出事了找谁、怎么停、怎么回滚 — **24h 可达**

---

## 1. 联系人（单一真相源）

**SoT 文件（勿把真实手机写进公共树）：**

| 路径 | 用途 |
|---|---|
| `security/ir/contacts.example.yaml` | 模板 |
| `security/ir/contacts.local.yaml` | 本地填写（`*.local.yaml` 已 gitignore） |
| 或 `AIPLAT_IR_CONTACTS_PATH` / `~/.aiplat/security/ir_contacts.yaml` | 覆盖路径 |

校验：

```bash
python3 scripts/security_ir_contacts.py          # filled → exit 0
python3 scripts/security_ops_audit.py            # 含联系人 + fail-closed
```

| 角色（YAML key） | 说明 |
|---|---|
| `security_owner` | Security Owner |
| `platform_oncall` | Platform On-call |
| `ops_infra` | Ops / Infra |
| `exec_sponsor` | Exec Sponsor（升级） |

**禁止：** 联系人仍空 / TBD 时将 P1-IR 演练标 `pass`。

---

## 2. 止损步骤（按序）

1. **确认影响面**：租户 / 端点 / Agent / 工具 / 密钥是否外泄。  
2. **停流量**：网关限流 / 下线受影响路由 / 暂停相关 builder 发布。  
3. **关钥匙**：轮换或吊销 API key、JWT 签发密钥、MCP/插件 token。  
4. **硬门恢复**：确认 `AIPLAT_HARD_FLOOR_DISABLED` 未在无 UNTIL 窗内开启；必要时强制 unset。  
5. **fail-closed**：生产/预发设 `AIPLAT_PROFILE=production` 且勿用无期限的 fail-open。切流步骤见 [`P0-2-fail-closed-cutover.md`](./P0-2-fail-closed-cutover.md)；干跑 `python3 scripts/security_ops_audit.py --profile-matrix`。  
6. **保留证据**：审计日志、attack-sim 报告、`artifact.security.json`、变更单号。

---

## 3. 回滚路径

| 变更类型 | 回滚 |
|---|---|
| 错误发布的生成 App | 回滚上一 `deploy_dir` / 停 daemon_jobs 会话 |
| Policy fail-mode 误配 | 恢复上一 env；prod open 须带 `AIPLAT_POLICY_FAIL_OPEN_UNTIL` |
| Hard-floor 逃生误开 | 删除 `AIPLAT_HARD_FLOOR_DISABLED*` 或等 UNTIL 过期 |
| 恶意 Skill/MCP | 从 allowlist 移除；吊销签名信任 |

---

## 4. 24h 可达检查

- [ ] `python3 scripts/security_ir_contacts.py` exit 0  
- [ ] On-call 渠道实测可达（月度抽检）  
- [ ] 本文件路径已知：`reports/security/P0-IR-runbook.md`

**P1-IR 演练剧本**：[`P1-IR-tabletop-drill.md`](./P1-IR-tabletop-drill.md)（场景 + 记分；真人推演后才可标 pass）。  
**不做（留给 P2-3）**：正式对外漏洞披露与认证路径。
