# aiPlat 平台与成果物安全质量报告 v2（证据审计版）

> **版本**：v2.0 · 2026-11-09  
> **替代**：[v1 桌面评估](./aiplat-security-quality-report-2026-11-09.md)  
> **性质**：代码证据审计 / 非认证  
> **方法**：关键代码抽查 + 现有测试/脚本核对 + 文档交叉验证；**未做完整动态渗透、未做外部审计**  
> **诚实锁**：本报告只写“代码/测试能证明的”；不能证明的明确标 `UNVERIFIED`；`security_certification=false`。

---

## 0. 更正声明

v1 是“文档 + 代码锚点”的桌面评估，部分结论依赖 `AIPLAT_CAPABILITIES.md`、安全架构自评和自动渗透报告。

v2 在代码抽查中发现一个**实质性证据问题**：

> **`scripts/security-attack-sim.py` 在服务器不可达时会把连接失败计为 PASS，并在 0 个真实防御成功的情况下输出 “All defenses hold” 且退出码 0。**

因此：

- v1 中“自动渗透 10 场景”不能作为安全验证证据；
- `docs/security/security-pen-test-report.md` 的 “Actual” 列大量为空，不能作为通过证据；
- 任何“已通过渗透测试”的表述都应撤回或降级为“脚本存在，但结果不可信”。

---

## 1. 证据等级

| 等级 | 含义 | 本报告处理 |
|---|---|---|
| **V** | 代码/配置直接验证 | 可写“已实现” |
| **T** | 有可运行测试且本次执行 | 可写“已自测” |
| **D** | 仅有文档/能力表声明 | 只能写“声称” |
| **U** | 未验证/无法验证 | 必须写 `UNVERIFIED` |
| **A** | 自动脚本/报告 | 需先审脚本可信度 |

> 本报告不把 D 当 V，不把 A 当 T。

---

## 2. 关键代码发现

### 2.1 自动渗透脚本存在 false-pass

**文件**：`scripts/security-attack-sim.py`

| 行 | 问题 |
|---|---|
| 49–51 | 连接失败时 `PASS += 1`，不惩罚不可达 |
| 60–63 | S2 “Prompt injection” 只检查 HTTP 200，不检查 guard 是否命中 |
| 85–90 | S4 rate limit 无论结果都 `PASS += 1` |
| 102–103 | S7 “Sandbox escape” 只检查 401，不是逃逸测试 |
| 108–110 | S9 “Key leakage” 只检查 200，不检查泄漏 |

**实测**：

```bash
$ python3 scripts/security-attack-sim.py http://127.0.0.1:9
...
✅ All defenses hold (13/26 passed)
exit=0
```

服务器端口 9 不可达，脚本仍然判定“防御成立”。  
**结论：该脚本不能作为安全证据。**

### 2.2 PolicyGate 失败模式默认 open

**文件**：`aiPlat-core/core/harness/infrastructure/gates/policy_gate.py:291-315`

- `_parse_policy_fail_mode(..., default="open")`；
- `resolve_policy_fail_mode` 默认 open；
- 非关键路径固定 open；
- 注释写明 “default open, compat / dev”。

**结论：生产必须显式设置 `AIPLAT_POLICY_FAIL_MODE=ask|closed`，否则故障时可能放行。**

### 2.3 ApprovalGate hard floor 存在代码

**文件**：`approval_gate.py:9-11, 94-144, 262-300`

- CRITICAL 规则：删除、DROP、权限变更、force push、kill -9、shell 等；
- hard floor 不可被 session auto-approve；
- `AIPLAT_HARD_FLOOR_DISABLED=1` 是逃生开关；
- 代码有 `check_hard_floor`。

**结论：机制存在；是否在生产禁用逃生开关，未验证。**

### 2.4 SecretsManager 使用 AES-256-GCM

**文件**：`secrets_manager.py:1-84`

- `AESGCM.generate_key(bit_length=256)`；
- encrypt/decrypt 使用 AES-GCM。

**结论：加密实现存在；密钥生命周期/轮换/外部 KMS 未验证。**

### 2.5 PII Detector 存在

**文件**：`pii_detector.py:64-117`

- `PIIDetector.mask`；
- Presidio 可选 + 内置正则；
- 覆盖手机/身份证/邮箱/银行卡/地址/IP（文档声明）。

**结论：代码存在；全链路覆盖未动态验证。**

### 2.6 Audit SHA-256 链存在

**文件**：`governance/audit/logger.py:47-98`

- `AuditLogger`；
- `hashlib.sha256`；
- `verify_integrity`。

**结论：代码存在；外部锚/WORM 未验证。**

### 2.7 安全测试资产规模

| 资产 | 数量 | 证据 |
|---|---:|---|
| S1 live_llm 攻击包 | 25 | `s1_live_attacks.v0.json` / `S1_LIVE.md` |
| A7 safety cases | 8 | `workspace_seeds/eval/agent_capability/cases/safety.json` |
| 自动渗透脚本 | 10 场景 | 但脚本不可信（见 2.1） |
| 外部渗透/认证 | 0 | 未见第三方报告 |

**结论：有测试资产，但规模和独立性不足。**

---

## 3. 证据矩阵

| # | 维度 | 状态 | 证据 | 说明 |
|---|---|---|---|---|
| 1 | 治理/威胁模型 | D | 安全架构/合规矩阵 | 有文档，无逐系统 threat model |
| 2 | 安全需求 | D | CAPABILITIES/文档 | 未逐项验证 |
| 3 | 独立验证/红队 | U | 无第三方报告 | 自动脚本不可信 |
| 4 | 认证/合规 | U | EU AI Act 自评 | 非认证 |
| 5 | 身份认证 | D | OIDC/JWT/MFA 文档 | 未做端到端测试 |
| 6 | 授权/最小权限 | V | PolicyGate/ApprovalGate 代码 | 机制存在，生产配置未验证 |
| 7 | 租户/数据隔离 | U | 文档声明 | 无跨租户实测 |
| 8 | 隐私/生命周期 | D | PII 代码/文档 | retention/删除未验证 |
| 9 | 密钥/凭据 | V | AES-GCM 代码 | 密钥管理未验证 |
| 10 | 审计 | V | SHA-256 链代码 | 外部锚未验证 |
| 11 | 输入/注入 | D | 6 条正则声明 | 未做对抗测试 |
| 12 | 输出处理 | D | CodeAuditor 文档 | 未做下游注入测试 |
| 13 | 模型/系统提示 | D | PromptAudit 文档 | 无系统提示泄漏专项 |
| 14 | 工具/Agent | V/D | RiskClass/Approval 代码 | 沙箱弱/旁路未验证 |
| 15 | 记忆/RAG | D | provenance 文档 | 无投毒测试 |
| 16 | 多 Agent | U | deferred | 未实现/未测 |
| 17 | 运行时隔离 | U | microVM 钩子 | 无 Linux/KVM 实测 |
| 18 | 供应链 | D | 签名/扫描文档 | 无 SBOM/证明 |
| 19 | 成果物安全 | D | builder/conformance 文档 | 无逐应用验收 |
| 20 | 审计/IR/合规 | D/U | 文档/自评 | 无外部审计/演练 |

---

## 4. 修正后的平台评估

### 4.1 可以确认

- PolicyGate/ApprovalGate 机制存在；
- SecretsManager 使用 AES-GCM；
- PII Detector 存在；
- AuditLogger 有 SHA-256 链；
- S1 25 条、A7 8 条测试资产存在；
- hard floor 代码存在。

### 4.2 不能确认

- 生产配置是否 fail-closed；
- 租户隔离是否全链路；
- Prompt injection 是否能挡住；
- microVM 是否能隔离；
- 生成物是否逐应用安全；
- 自动渗透是否通过；
- 是否有外部审计/认证。

### 4.3 平台结论

> **“有安全控制代码”可以确认；  
> “安全控制有效”只能部分确认；  
> “平台安全”不能确认。**

---

## 5. 修正后的成果物评估

| 成果物 | 已确认 | 未确认 | 结论 |
|---|---|---|---|
| Generated App | builder/conformance/autoreview 文档 | authz/IDOR/SSRF/DAST | 安全契约未验证 |
| Generated Agent | 契约/平台门禁文档 | 导出后防护 | 平台内依赖平台，平台外降级 |
| Generated Skill | 签名/SkillsGuard 文档 | handler 代码审计 | 注册期有门，运行期未证 |
| Generated Code | CodeAuditor 5 规则 | SAST/DAST/污点分析 | 辅助审查，不是保证 |
| Pi | 企业门禁/审批文档 | 无 PolicyGate | 导出即降级 |
| 文档/报告 | PII/审计文档 | 内容扫描 | 中低 |

**成果物结论：**

> **没有证据表明“所有生成物都经过安全验收”；只能确认“生成链路有安全检查和模板”。**

---

## 6. 与 v1 的差异

| 项 | v1 | v2 |
|---|---|---|
| 自动渗透 | 作为安全证据 | **判定不可信** |
| 评分 | 给出 3.2/5 等 | 不作为认证依据 |
| 平台结论 | 较强纵深防御 | 控制存在，有效性部分未证 |
| 成果物 | 中低 | 多为 D/U，缺逐应用证据 |
| 认证 | 无 | 仍无 |
| 证据等级 | 未逐条标 | V/T/D/U/A |

---

## 7. 要得到“完全真实”的完整报告，还缺什么

### 7.1 代码审计

- 逐模块审 PolicyGate/ApprovalGate/Sandbox/Secrets/PII/Audit/Skill signature/Builder/Pi；
- 每个控制点：入口、默认值、绕过路径、失败模式、测试；
- 建立 `claim -> code path -> test -> evidence` 映射。

### 7.2 动态验证

- 跨租户/越权/IDOR；
- Prompt injection 直接/间接/多轮；
- 工具/记忆投毒；
- microVM 逃逸/出网/宿主读写；
- 生成 App DAST；
- 真实红队。

### 7.3 外部验证

- 第三方渗透；
- 独立红队；
- 认证审计（可选）。

### 7.4 修复测试脚本

- 连接失败必须 FAIL，不是 PASS；
- S2 必须检查 guard 是否命中；
- S4 必须检查 429/限流；
- S7 必须做真实逃逸探针；
- S9 必须检查泄漏；
- S10 必须做真实 replay。

---

## 8. 修正后的总体结论

### 可以说

- aiPlat 有多项安全控制代码；
- 有审批 hard floor、AES-GCM、PII、审计链、S1/A7 测试资产；
- 平台内设计上有纵深防御；
- 生成链路有安全检查和模板。

### 不能说

- 已通过安全认证；
- 自动渗透已通过；
- 平台安全有效已被验证；
- 生成物自动安全；
- Pi 导出后仍有平台防护；
- microVM 已覆盖；
- Prompt injection 已防住。

### 一句话

> **v2 能确认“有控制、有代码、有测试资产”；不能确认“控制有效、系统安全、成果物安全”。  
> 要得到完全真实的完整报告，必须补代码审计 + 动态验证 + 外部审计；当前只能给出“证据分级”的诚实结论。**

---

## 附录 A：本次检查的文件

| 文件 | 用途 |
|---|---|
| `scripts/security-attack-sim.py` | 发现 false-pass |
| `aiPlat-core/core/harness/infrastructure/gates/policy_gate.py` | fail mode 默认 open |
| `aiPlat-core/core/harness/infrastructure/gates/approval_gate.py` | hard floor |
| `aiPlat-core/core/harness/infrastructure/secrets_manager.py` | AES-GCM |
| `aiPlat-core/core/services/pii_detector.py` | PII mask |
| `aiPlat-platform/governance/audit/logger.py` | SHA-256 链 |
| `packages/aiplat-evaluation/docs/a3/s1_live_attacks.v0.json` | S1 25 条 |
| `aiPlat-core/workspace_seeds/eval/agent_capability/cases/safety.json` | A7 8 条 |
| `docs/security/security-pen-test-report.md` | 自动报告，Actual 空 |
| `docs/security/security-architecture.md` | 自评 L1–L6 |

## 附录 B：本次未做

- 未启动服务做动态渗透；
- 未做跨租户实测；
- 未做 microVM 逃逸；
- 未做生成 App DAST；
- 未做外部审计；
- 未逐行审所有安全模块。

## 附录 C：使用限制

- 本报告是证据审计，不是认证；
- 不能用于对外“安全通过”声明；
- 任何评分/结论需随代码/配置更新复核。
