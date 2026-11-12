---
generated_at: 2026-11-11
doc_type: Report
---

# P2-3：正式 IR / 披露 / 认证路径（草案）

> 改进方案 v2.2 · P2-3（90+）  
> 前置：[`P0-IR-runbook.md`](./P0-IR-runbook.md) + [`P1-IR-tabletop-drill.md`](./P1-IR-tabletop-drill.md)  
> 诚实锁：草案 ≠ 已认证；`security_certification=false`

---

## 1. 正式事件响应（相对 P0/P1）

| 层级 | 内容 |
|---|---|
| P0 | 联系人 + 止损 + 回滚 |
| P1 | 桌面演练 + 记分 |
| **P2** | 分级（SEV）、对外沟通模板、法务/PR 升级、事后复盘强制字段 |

### 1.1 建议 SEV

| SEV | 定义 | 对外 |
|---|---|---|
| SEV-1 | 跨租户数据泄露 / 认证绕过 / 逃逸确认 | 按披露政策通知受影响方 |
| SEV-2 | 单租户高影响；签名/SBOM 门被绕过 | 视合同 |
| SEV-3 | 可缓解的配置/假绿 | 内部 |

### 1.2 强制复盘字段

- 时间线、影响面、根因、检测缺口、控制失效点  
- 关联证据：`artifact.security.json`、SBOM digest、attack-sim、P1-3/P1-4 报告  
- 认证状态：**不因复盘自动翻转**

---

## 2. 漏洞披露政策（草案要点）

1. 安全邮箱 / 渠道（填写）：`security@…`  
2. 90 天协调披露默认窗（可协商）  
3. 禁止在未修复时公开利用细节  
4. 感谢与 CVE 申请可选  

---

## 3. 认证路径（可选）

| 步骤 | 说明 |
|---|---|
| 选标准 | 如 ISO 27001 子集 / SOC2 控制映射（另开项目） |
| 证据包 | 仅含 `pass` 且 Subject 锁定、非 fixture/model_only |
| 独立审计 | 第三方；平台自评不得冒充 |
| 声明句 | 必须通过 `validate_claim_sentence_against_policy` 类门 |

**禁止：** 84 单测 / guest_sim / unsigned manifest / 无 SBOM 发布 → 写入认证声明。

---

## 4. 开放项（实施前填）

- [ ] 安全邮箱与法务联系人  
- [ ] 对外模板审阅  
- [ ] 认证是否立项（Exec Sponsor）  
