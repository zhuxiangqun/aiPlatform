# aiPlat 安全质量改进方案

> **版本**：v1.0 · 2026-11-09  
> **类型**：安全改进计划 / 执行方案  
> **依据**：[aiPlat 平台与成果物安全质量分析报告](./aiplat-security-quality-report-2026-11-09.md)  
> **状态**：提案，不实施；落地须另开变更单  
> **诚实锁**：`security_certification=false`；`accuracy_claim=false`；本方案不承诺“认证通过”，只承诺“可验证的安全质量提升”。

---

## 0. 执行摘要

### 0.1 目标

把 aiPlat 从：

> **“有安全工程控制、以自测为主”**

推进到：

> **“平台核心控制可独立验证；成果物有逐应用安全证据；对外声明范围可审计。”**

### 0.2 四个结果

1. **平台**：核心控制从 L1–L2 提升到 L3（独立验证）候选；
2. **成果物**：从“安全感知生成”提升到“有安全契约、有测试、有证据”；
3. **运行时**：从 Docker/子进程提升到可验证的强隔离路径；
4. **治理**：从自评清单提升到控制矩阵 + 证据 + 声明边界。

### 0.3 五个最优先动作

1. 生产 PolicyGate 默认 `ask/closed`，禁止 fail-open；
2. 生成物安全 manifest + 发布门；
3. 生成代码强制 SAST/密钥/依赖/authz 测试；
4. Linux/KVM microVM 逃逸探针；
5. 外部渗透测试 + 独立红队立项。

### 0.4 不做

- 不把“S1 25 条”当安全认证；
- 不用“自动扫描通过”代替人工红队；
- 不在无 microVM 证据时宣称隔离；
- 不让 Pi 导出物默认继承平台安全声明；
- 不用单一“安全分”对外认证。

---

## 1. 现状与根因

### 1.1 现状摘要

| 对象 | 当前 | 主要问题 |
|---|---|---|
| 平台 | L1–L2，少量自动扫描 | 无独立验证/认证；部分默认 open |
| 身份/权限 | 较强 | 租户隔离待核实；旁路可绕过 |
| 数据/密钥 | 较强 | retention/删除/DLP 弱 |
| Prompt/模型 | 基础 | 正则注入；系统提示/投毒弱 |
| 工具/Agent | 有审批/风险类 | 沙箱弱；记忆/多 Agent 弱 |
| 运行时 | Docker/子进程 | microVM 未实测 |
| 供应链 | 扫描/签名 | 无 SBOM/证明链 |
| 成果物 | 有 conformance/autoreview | 无逐应用威胁模型/验收 |

### 1.2 根因

1. **平台中心化**：安全能力主要在平台横切，成果物自身安全契约弱；
2. **缺少威胁模型**：平台级有，应用级没有；
3. **缺少证据门**：实现 ≠ 验证 ≠ 认证；
4. **fail-open 遗留**：生产配置未强制 closed；
5. **隔离未证明**：admit ≠ escape test；
6. **供应链未闭环**：签名有，SBOM/证明/撤销弱；
7. **红队/认证不足**：自动扫描多，独立验证少。

---

## 2. 目标状态与原则

### 2.1 12 个月目标状态

| 维度 | 目标 |
|---|---|
| 治理 | 每个核心系统有 threat model + 控制矩阵 + owner |
| 身份/权限 | 生产 fail-closed；租户/权限回归测试 |
| 数据 | 数据分类、retention、删除、导出可审计 |
| Prompt/模型 | 注入对抗集 + 系统提示保护 + judge 校准 |
| 工具/Agent | 工具 allowlist、审批、记忆/多 Agent 测试 |
| 运行时 | Linux/KVM microVM + 逃逸探针 |
| 供应链 | SBOM + 签名 + 证明 + MCP allowlist |
| 成果物 | 安全 manifest + SAST/DAST/authz 门 |
| 保证 | 外部渗透 + 独立红队；认证可选 |
| 声明 | 范围限定、证据绑定、可撤回 |

### 2.2 原则

1. **shared responsibility**：平台护栏 ≠ 成果物安全；
2. **secure by default**：默认拒绝、默认最小权限；
3. **fail closed**：安全基础设施故障时不放行；
4. **evidence over claims**：每个结论有证据；
5. **threat-model driven**：先建模，再测试；
6. **verify, don't trust**：不信任生成物/工具/模型输出；
7. **no security theater**：不做无法验证的“认证按钮”。

---

## 3. 目标运营模型

```text
Security Review Board
  ├─ Platform Security（平台控制）
  ├─ Product Security（成果物安全）
  ├─ QA / Red Team（独立验证）
  ├─ Compliance / Legal（合规）
  └─ Incident Response（响应）
```

### 3.1 角色

| 角色 | 职责 |
|---|---|
| Executive Sponsor | 资源、风险接受、对外声明 |
| Security Owner | 安全质量总负责 |
| Platform Security Lead | 身份/权限/运行时/审计 |
| Product Security Lead | 生成物安全契约/测试 |
| QA / Red Team | 独立验证/对抗测试 |
| Compliance | 标准映射/审计 |
| IR Lead | 事件响应/复盘 |

### 3.2 每个成果物必须有

- 安全 owner；
- threat model；
- security manifest；
- 测试证据；
- 声明边界；
- 回滚/IR 路径。

---

## 4. 工作流（Workstreams）

### WS1 治理、威胁模型与保证

**目标**：从“自评清单”到“控制矩阵 + 证据 + 独立验证”。

** actions**

1. 建立安全控制矩阵：维度 × 控制 × 证据 × owner × 状态；
2. 每类成果物 threat model 模板（STRIDE/MAESTRO/ATLAS 映射）；
3. 安全需求模板（security AC）；
4. 安全声明模板（范围/证据/限制）；
5. 外部渗透/红队 RFP；
6. 认证路线（ISO 42001/NIST AI RMF）。

**交付**

- `SECURITY_CONTROL_MATRIX.md`
- `THREAT_MODEL_TEMPLATE.md`
- `SECURITY_CLAIM_TEMPLATE.md`
- 外部评估计划。

**验收**

- 核心系统 100% 有 threat model；
- 每个 P0 控制有证据；
- 声明模板可审计。

---

### WS2 身份、权限、租户

**目标**：生产 fail-closed；权限/租户可验证。

** actions**

1. PolicyGate 生产默认 `ask/closed`；
2. 关闭/限制 `AIPLAT_APPROVALS_DISABLED` 等逃生开关；
3. 建立权限矩阵：角色 × 资源 × 动作；
4. 租户隔离负向测试：列表/详情/导出/取消/删除；
5. admin MFA 强制验证；
6. 旁路检测：直接 HTTP/CLI/子进程。

**验收**

- 跨租户访问 100% 拒绝；
- 未授权工具调用 100% 拒绝；
- 生产 fail mode 不是 open；
- 旁路有检测/阻断。

---

### WS3 数据、隐私、密钥、审计

**目标**：数据可分类、可删除、可审计。

** actions**

1. 数据分类分级；
2. retention/删除/导出策略；
3. PII 全链路扫描（输入/输出/日志/报告）；
4. SecretsManager 强制使用；
5. 审计链外部锚/WORM；
6. 备份删除传播。

**验收**

- PII 泄漏用例 0 通过；
- 删除后不可检索；
- 审计可验证；
- 密钥不落日志。

---

### WS4 Prompt、模型、输出安全

**目标**：从正则到结构化防护 + 对抗评测。

** actions**

1. 指令层级/消息来源标记；
2. 工具/RAG 内容视为不可信；
3. 系统提示泄漏防护；
4. 输出编码/下游注入测试；
5. Prompt injection 对抗集（直接/间接/多轮）；
6. judge 校准与人工复核。

**验收**

- 直接/间接注入有基线 ASR；
- 输出进入 HTML/SQL/Shell 有编码测试；
- 系统提示泄漏有专项用例；
- judge 与人工一致率达标。

---

### WS5 工具、Agent、记忆、多 Agent

**目标**：防过度代理、工具投毒、记忆投毒、多 Agent 越权。

** actions**

1. 工具 allowlist + 参数 schema；
2. 高危工具审批/hard floor；
3. 记忆写入 provenance/trust/删除；
4. RAG 来源可信度/引用校验；
5. 多 Agent handoff 身份/权限；
6. 工具/记忆投毒攻击集。

**验收**

- 越权工具调用 0 通过；
- 删除后记忆不可召回；
- 间接注入有测试；
- 多 Agent 越权有阻断。

---

### WS6 运行时隔离

**目标**：从 Docker 到可验证 microVM。

** actions**

1. Linux/KVM 主机；
2. Firecracker/microVM admit；
3. 逃逸探针：宿主文件、网络、设备、提权；
4. 负向对照；
5. 网络出口 allowlist；
6. 审计/监控。

**验收**

- `guest_boot` 成功；
- 逃逸探针全负；
- 出网被阻断；
- 仍不称“隔离认证”。

---

### WS7 供应链与制品

**目标**：SBOM + 签名 + 证明 + 撤销。

** actions**

1. SBOM（依赖/模型/插件）；
2. 制品签名/证明；
3. MCP/plugin allowlist；
4. 依赖 pin/漏洞 SLA；
5. 密钥/签名轮换/撤销；
6. 供应链攻击演练。

**验收**

- 每个发布物有 SBOM；
- 未签名制品不可发布；
- 高危依赖阻断；
- MCP 未登记拒绝。

---

### WS8 成果物安全（Builder）

**目标**：从“生成后检查”到“安全契约 + 发布门”。

** actions**

1. `artifact.security.json` manifest；
2. 安全模板：authn/authz/tenant/input/output/secrets；
3. 生成代码强制 SAST + 密钥 + 依赖；
4. authz/IDOR/SSRF/XSS 测试；
5. 生成 App DAST；
6. Pi 导出安全基线；
7. 发布前安全验收。

**验收**

- 每个成果物有 manifest；
- 每个成果物有 threat model；
- 每个成果物通过 SAST/authz 测试；
- Pi 导出明确列出丢失的控制。

---

### WS9 审计、IR、运营

**目标**：可检测、可响应、可回滚。

** actions**

1. 审计外部锚；
2. IR runbook；
3. 桌面演练；
4. 漏洞披露；
5. 回滚/恢复；
6. 安全指标看板。

**验收**

- MTTR 有基线；
- 演练有记录；
- 回滚可执行；
- 漏洞披露渠道存在。

---

### WS10 人因、审批 UX、透明度

**目标**：减少审批疲劳/误操作/过度依赖。

** actions**

1. 审批风险分级；
2. 高风险二次确认；
3. 用户可见安全边界；
4. 过度依赖提示；
5. 审批日志可解释。

**验收**

- 高风险审批有明确理由；
- 误批率下降；
- 用户能理解“能/不能”。

---

### WS11 可用性、资源滥用

**目标**：防 DoS/成本炸弹/无限循环。

** actions**

1. 预算/超时/步数；
2. 队列背压；
3. 速率限制；
4. 成本告警；
5. 资源滥用测试。

**验收**

- 无限循环被阻断；
- 成本上限生效；
- 队列积压有告警。

---

### WS12 合规与认证

**目标**：从自评到可审计；认证可选。

** actions**

1. ISO 42001/NIST AI RMF 映射；
2. SOC2/ISO27001 控制证据；
3. 数据驻留；
4. 外部审计；
5. 认证范围声明。

**验收**

- 控制矩阵可审计；
- 外部审计完成；
- 声明范围明确。

---

## 5. 阶段路线图

### Phase 0：0–30 天（止血）

| 工作 | 交付 | 验收 |
|---|---|---|
| PolicyGate fail-closed | 配置 + 测试 | 生产非 open |
| 生成物安全 manifest schema | schema + 模板 | 可校验 |
| SAST/密钥/依赖门 | CI gate | 新代码阻断 |
| 租户/权限负向测试 | 测试集 | 跨租户拒绝 |
| Prompt 注入对抗集 v1 | 30–50 用例 | 有基线 ASR |
| 外部渗透 RFP | 计划 | 供应商确定 |
| Pi 安全声明 | 文档 | 明确丢失控制 |
| IR 桌面演练 | 记录 | 发现缺口 |

**出口：** 平台基线可复现；成果物有 manifest；不称认证。

### Phase 1：1–3 个月（平台硬化）

- microVM/Linux KVM 探针；
- SBOM 原型；
- 记忆/工具投毒测试；
- 输出编码/下游注入；
- 审计外部锚；
- 生成 App authz 测试模板；
- 外部渗透执行。

**出口：** 平台核心控制 L3 候选；成果物 L2+。

### Phase 2：3–6 个月（成果物安全）

- secure-by-construction 模板；
- 生成 App DAST；
- Pi 安全基线；
- 多 Agent 安全；
- 供应链证明；
- 红队复测。

**出口：** 成果物有逐应用证据；无“平台内自动安全”表述。

### Phase 3：6–12 个月（保证/认证）

- ISO 42001/NIST 映射；
- 外部审计；
- 认证范围；
- 持续监控；
- 公开透明度报告（可选）。

**出口：** 可对外发范围限定安全声明；认证可选。

---

## 6. 安全质量门

### G0 — PR 门（每次提交）

- SAST/Ruff bandit；
- 密钥扫描；
- 依赖扫描；
- 架构守卫；
- 单元测试。

**阻断：** 高危/密钥/越界。

### G1 — 平台基线门

- 身份/权限/租户测试；
- PolicyGate fail-closed；
- 审计/PII/密钥；
- Prompt 注入基线。

**阻断：** 跨租户/越权/fail-open。

### G2 — 成果物门

- security manifest；
- threat model；
- SAST/DAST/authz/tenant；
- SBOM/签名；
- 回滚/IR。

**阻断：** 缺 manifest/threat model/高危漏洞。

### G3 — 生产门

- staging 渗透；
- 红队；
- SLO/IR；
- 外部评估。

**阻断：** 未验证/未审计。

### G4 — 认证门（可选）

- 外部审计；
- ISO/NIST 映射；
- 范围声明；
- 签字。

**阻断：** 任何声明超出证据。

---

## 7. 成果物安全契约

每个成果物必须有：

```json
{
  "artifact_id": "app-x@1.0.0",
  "type": "app|agent|skill|pi",
  "owner": "...",
  "data_classes": ["internal"],
  "authn": "platform|oidc|none",
  "authz": {"model": "rbac", "tenant": true},
  "tools": ["search"],
  "egress": ["api.example.com"],
  "secrets": ["vault:..."],
  "dependencies": ["..."],
  "threat_model": "docs/security/threat-models/app-x.md",
  "tests": {
    "sast": true,
    "dast": true,
    "authz": true,
    "tenant": true,
    "secrets": true
  },
  "sbom": "sbom/app-x.json",
  "claim": {"security": "scoped", "certified": false}
}
```

**发布门：**

- manifest 缺失 → 拒绝；
- threat model 缺失 → 拒绝；
- SAST/DAST/authz 未过 → 拒绝；
- 高危依赖/密钥 → 拒绝；
- Pi 导出未声明丢失控制 → 拒绝。

---

## 8. 指标与 KPI

| 指标 | 目标 |
|---|---|
| 核心系统 threat model 覆盖 | 100% |
| P0 控制证据覆盖 | 100% |
| 跨租户负向测试 | 100% 拒绝 |
| 生成物 security manifest | 100% |
| 生成代码 SAST 覆盖 | 100% |
| 生成 App authz 测试 | 100% |
| SBOM 覆盖 | 100% 发布物 |
| 未签名制品 | 0 |
| microVM 逃逸探针 | 全负 |
| 外部渗透高危 | 0 未修复 |
| MTTR | 有基线并下降 |
| 误报率 | 有基线并下降 |

> 不设“单一安全分”；按维度报告。

---

## 9. RACI

| 工作 | 负责 | 批准 | 咨询 | 知会 |
|---|---|---|---|---|
| 安全治理 | Security Owner | Exec Sponsor | Compliance | Eng |
| 平台控制 | Platform Security | Security Owner | QA | Eng |
| 成果物安全 | Product Security | Security Owner | Builder | Product |
| 外部渗透 | QA/Red Team | Security Owner | Vendor | Exec |
| 认证 | Compliance | Exec Sponsor | External | All |

---

## 10. 资源与预算（量级）

| 阶段 | 人力 | 外部 |
|---|---|---|
| Phase 0 | 1 安全负责人 + 1 平台 + 1 产品 + 0.5 QA | 渗透 RFP |
| Phase 1 | +1 平台 +0.5 合规 | 渗透执行 |
| Phase 2 | +1 产品 +0.5 红队 | 红队/工具 |
| Phase 3 | +0.5 合规 | 认证审计 |

> 具体人日/费用需按组织预算另算；不要用“安全是免费”误导。

---

## 11. 风险与依赖

| 风险 | 缓解 |
|---|---|
| 外部审计排期长 | 提前 RFP |
| microVM 无 Linux 主机 | 采购/云主机 |
| 安全门拖慢发布 | 分级门 + baseline |
| 误报导致绕过 | 校准/豁免流程 |
| Pi 边界争议 | 明确“导出降级” |
| 供应链数据缺失 | SBOM 先行 |
| 生成物 owner 不清 | 强制 manifest owner |

---

## 12. 未来 30 天行动清单

1. 冻结当前安全基线（commit/build）；
2. PolicyGate 生产 fail-closed；
3. 发布 artifact security manifest schema；
4. CI 加 SAST/密钥/依赖门；
5. 租户/权限负向测试；
6. Prompt 注入对抗集 v1；
7. SBOM 原型；
8. 外部渗透 RFP；
9. Pi 安全声明；
10. IR 桌面演练。

---

## 13. 验收与声明边界

### 13.1 阶段声明

| 阶段 | 可以说 | 不能说 |
|---|---|---|
| Phase 0 | 工程基线改进 | 已安全 |
| Phase 1 | 平台核心控制有证据 | 已认证 |
| Phase 2 | 成果物有安全证据 | 所有成果物安全 |
| Phase 3 | 范围限定、外部验证 | 通用安全认证 |

### 13.2 Definition of Done

- 有 threat model；
- 有 control matrix；
- 有测试证据；
- 有 owner；
- 有声明边界；
- 有回滚/IR；
- 无未修复高危。

---

## 14. 附录 A：20 维映射

| 维度 | 工作流 |
|---|---|
| 治理/威胁建模 | WS1 |
| 身份/权限/租户 | WS2 |
| 数据/隐私/密钥/审计 | WS3 |
| Prompt/模型/输出 | WS4 |
| 工具/Agent/记忆/多 Agent | WS5 |
| 运行时隔离 | WS6 |
| 供应链 | WS7 |
| 成果物 | WS8 |
| 审计/IR | WS9 |
| 人因 | WS10 |
| 可用性 | WS11 |
| 合规 | WS12 |

## 附录 B：框架映射

- OWASP LLM Top 10 2025；
- OWASP Agentic AI Top 10；
- NIST AI 600-1；
- MITRE ATLAS；
- ISO/IEC 42001；
- Google SAIF；
- CSA MAESTRO。

## 附录 C：不做什么

- 不做“安全认证按钮”；
- 不把自动扫描当红队；
- 不把 S1 当认证；
- 不在无证据时宣称隔离；
- 不让 Pi 默认继承平台声明；
- 不用单一安全分掩盖维度缺口。

---

## 15. 结论

**本方案的核心不是“再加几个安全功能”，而是建立一条可验证的安全质量链：**

> **威胁模型 → 控制 → 测试 → 证据 → 门禁 → 声明 → 复评。**

**一句话：先把平台基线做实，再把成果物安全契约做实，最后才谈外部验证与认证；在此之前，只能说“有安全工程”，不能说“已安全”。**
