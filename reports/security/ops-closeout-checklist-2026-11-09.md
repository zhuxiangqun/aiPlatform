# 安全改进方案 — Ops / 人审收口清单

> 配套：[`aiplat-security-improvement-plan-2026-11-09.md`](./aiplat-security-improvement-plan-2026-11-09.md)  
> 工程侧可用：`python3 scripts/security_plan_closeout_check.py`（默认不因 ops 待办失败）  
> 诚实锁：全部勾完也**不等于** `security_certification`

---

## 0. 工程关闭（CI）

- [x] `python3 scripts/security_plan_closeout_check.py` → exit 0（工程清单；≠认证）  
- [x] `python3 scripts/security_ops_audit.py` 已接线 CI（advisory；缺联系人时 `ok=false` 仍 exit 0）  
- [ ] `python3 scripts/security_ops_audit.py --strict`（仅在联系人+密钥齐备后）  
- [x] 相关单测绿（attack-sim / artifact / P1-* / P2-1 / ir_contacts / ops_audit）

## 1. P0 Ops

| # | 项 | Owner | 完成 |
|---|---|---|---|
| 1 | 生产/预发 `AIPLAT_PROFILE` + fail-closed 审计；open 须 UNTIL | Platform Security | [ ] |
| 2 | 填写 `security/ir/contacts.local.yaml`；`python3 scripts/security_ir_contacts.py` exit 0；On-call 抽检 | IR Lead | [~] 本地已从 example 落盘并通过校验；**须替换为真实 on-call 后再勾完** |
| 3 | Authz pilot：2 类 × ≥3 样本 + 负向 + Owner 书面退出 | Product Security | [ ] |

## 2. P1 Ops

| # | 项 | Owner | 完成 |
|---|---|---|---|
| 4 | P1-1 文本族真 live（Subject 锁定） | Eval + QA | [ ] |
| 5 | P1-1 工具/检索真环境（`AIPLAT_EVAL_P1_1_TOOLS/RETRIEVAL`） | Eval + QA | [ ] |
| 6 | P1-2 真人双盲标定样本 | Security Owner | [ ] |
| 7 | P1-3 对 staging 黑盒跑分并归档 | Platform Eng | [ ] |
| 8 | P1-IR 桌面演练记分 ≥5 | IR Lead | [ ] |
| 9 | P1-4 真 KVM GuestChannel；covered 仅人审 | Infra | [ ] |

## 3. P2 Ops

| # | 项 | Owner | 完成 |
|---|---|---|---|
| 10 | syft/cosign 或 Ed25519 公钥入库仪式 | Platform Security | [ ] |
| 11 | 发标外部渗透（P2-2 RFP） | Security Owner | [ ] |
| 12 | 安全邮箱 + 正式 IR/认证是否立项 | Exec Sponsor | [ ] |

---

**禁止：** 用本清单勾选代替第三方报告或认证声明。
