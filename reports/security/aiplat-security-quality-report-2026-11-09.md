# aiPlat 平台与成果物安全质量分析报告

> **更正（2026-11-09）**：本报告是桌面评估；后续代码证据审计发现 `scripts/security-attack-sim.py` 存在 false-pass（服务器不可达仍计 PASS）。因此本报告中的“自动渗透/测试通过”不能作为安全证据。请以现行 [`v3 复审版`](./aiplat-security-quality-report-2026-11-09-v3.md) 为准（[`v2`](./aiplat-security-quality-report-2026-11-09-v2-evidence.md) 为中间证据审计）；本报告仅保留作对比。

> **版本**：v1.0 · 2026-11-09  
> **类型**：安全质量评估 / 工程审计  
> **范围**：aiPlat 平台、平台生成成果物（App / Agent / Skill / Code / Pi / 文档）  
> **方法**：仓库文档、代码、证据与公开框架对照；**未执行新的动态渗透或外部审计**  
> **诚实锁**：本报告不是安全认证；`security_certification=false`；评分是工程判断，不是合规结论。

---

## 0. 执行摘要

### 0.1 一句话结论

> **aiPlat 已经有一套较强的“工程级纵深防御”；但整体仍处于“已实现 + 已自测”阶段，缺少独立验证与认证。成果物是“安全感知生成”（security-aware generation），不是“secure-by-construction”；在平台内可继承护栏，离开平台后明显降级。**

### 0.2 三层结论

| 对象 | 结论 | 当前等级 |
|---|---|---|
| **aiPlat 平台** | 身份、权限、审批、审计、PII、密钥、签名、CI 扫描较完整 | **L1–L2（实现+自测）**，少量 L3 自动扫描 |
| **平台生成成果物** | 生成时有安全约束/模板/沙箱/autoreview/CodeAuditor/SkillsGuard | **L1–L2**，无逐成果物安全验收 |
| **对外安全声明** | 无独立渗透/认证；S1 是评测包不是认证 | **不可称“安全认证/生产安全”** |

### 0.3 最重要的 8 个风险

1. 无独立第三方渗透测试/认证；
2. microVM/强隔离未实测，`sandbox_real_isolation=false`；
3. Prompt injection 仍是 6 条正则，易绕过；
4. PolicyGate 失败模式默认 `open`；
5. Pi 导出不搬 PolicyGate/ApprovalGate/Memory；
6. 生成 App 无逐应用威胁模型与 authz/IDOR/SSRF 验收；
7. 生成代码缺强制 SAST/DAST/authz 测试门；
8. 供应链缺统一 SBOM/证明链，MCP/插件覆盖弱。

### 0.4 可以说 / 不能说

| 可以说 | 不能说 |
|---|---|
| 有纵深防御架构和多项安全控制 | 已通过安全认证 |
| 平台内标准执行路径有基线防护 | 成果物自动安全 |
| 有 S1 安全评测与自动扫描 | S1 = 生产安全 / 红队认证 |
| 生成物有安全检查和签名 | 生成物 secure-by-construction |
| Pi 有企业工具门禁/审批桥 | Pi 导出后仍有平台级防护 |

---

## 1. 评估范围与方法

### 1.1 范围内

- 平台身份、权限、审批、执行、数据、审计、供应链、CI；
- 生成 App / Agent / Skill / Code / Pi / 文档；
- 安全评测与红队资产；
- 安全治理文档与证据等级。

### 1.2 范围外

- 新的动态渗透、漏洞利用、红队执行；
- 生产环境真实流量与配置；
- 客户数据/多租户生产隔离实测；
- 正式合规审计（SOC2/ISO 42001/等保）。

### 1.3 证据等级

| 等级 | 含义 |
|---|---|
| **L1 已实现** | 代码/机制存在 |
| **L2 已自测** | 本地脚本/CI 有覆盖 |
| **L3 已独立验证** | 第三方/外部审计 |
| **L4 已认证** | SOC2/ISO 42001/等保等 |

> 本报告所有“✅”只表示 L1/L2 证据存在，不表示 L3/L4。

---

## 2. 评估框架：5 类 20 维

安全质量由以下维度共同决定，不能只看“身份+权限”。

| 类别 | 维度 |
|---|---|
| A. 治理与保证 | 安全治理/威胁建模、安全需求、独立验证/红队、认证与合规 |
| B. 身份与数据 | 身份认证、授权/最小权限、租户/数据隔离、隐私生命周期、密钥、审计 |
| C. AI/Agent 特有 | 输入信任/注入、输出处理、模型/系统提示、工具/过度代理、记忆/RAG、多 Agent、安全评测 |
| D. 运行时/供应链 | 沙箱/隔离/出口、供应链/制品完整性、安全编码/成果物 |
| E. 运营/人因/合规 | 可用性/资源滥用、人因/审批 UX、IR/回滚、配置安全、数据驻留/法务 |

### 2.1 维度评分（工程判断，1–5）

| 维度 | 分数 | 说明 |
|---|---:|---|
| 治理/威胁建模 | 3.0 | 有架构/合规矩阵，缺正式威胁模型 |
| 身份认证 | 4.0 | JWT/OIDC/MFA 较完整 |
| 授权/最小权限 | 4.0 | PolicyGate + 对象/字段权限 |
| 租户/数据隔离 | 3.0 | 设计有，生产验证不足 |
| 隐私/生命周期 | 3.0 | PII 脱敏强，retention/删除弱 |
| 密钥/凭据 | 4.0 | SecretsManager + 扫描 |
| 输入信任/注入 | 2.5 | 6 条正则，缺对抗评测 |
| 输出处理 | 2.5 | CodeAuditor/编码检查，非全链路 |
| 模型/系统提示 | 2.5 | PromptAudit，缺泄漏专项 |
| 工具/过度代理 | 3.0 | 审批/RiskClass，沙箱弱 |
| 记忆/RAG | 2.0 | provenance 有，评测弱 |
| 多 Agent | 1.5 | 基本 deferred |
| 运行时隔离 | 2.5 | Docker/子进程，无 microVM 实测 |
| 供应链/制品 | 2.5 | 签名/扫描，缺 SBOM/证明 |
| 安全编码/成果物 | 2.5 | CodeAuditor 5 规则 |
| 审计/可观测 | 3.5 | SHA-256 链，本地 |
| 可用性/资源 | 3.0 | 限额/超时，DoS 未系统测 |
| 人因/审批 UX | 2.5 | HITL/Inbox，缺用户测试 |
| IR/回滚 | 2.0 | 有回滚指引，缺演练 |
| 合规/认证 | 2.0 | 自评/映射，无认证 |

> **平台工程分约 3.2/5；保证/认证分约 1.6/5；成果物自身约 2.3/5。**

---

## 3. aiPlat 平台安全质量

### 3.1 治理与保证

**已做：**

- `docs/security/security-architecture.md` 定义 L1–L6 纵深防御；
- `docs/audit/compliance-matrix.md` 维护架构合规矩阵；
- `docs/architecture/eu-ai-act-compliance.md` 有 EU AI Act 自评；
- SOC2/ISO27001 有控制映射与自动检查；
- CAPABILITIES 登记安全能力。

**未做/不足：**

- 自评清单不等于独立审计；
- 无正式威胁模型库（STRIDE/MAESTRO/ATLAS 映射）；
- 无 ISO/IEC 42001 认证；
- 无外部法律/合规评估。

**评级：3.0/5（L1–L2）。**

### 3.2 身份、权限、租户

**已做：**

- JWT/OIDC/SSO（Keycloak/Azure AD/Okta）；
- admin MFA 强制；
- PolicyGate 在 `sys_tool_call` / `sys_skill_call` 入口检查；
- RBAC/PBAC、对象级/字段级权限、ManagedPolicy；
- ApprovalGate/HITL、Unattended Inbox、hard floor；
- 审计来源与审批 provenance。

**未做/不足：**

- `resolve_policy_fail_mode` 默认 `open`，生产需 `ask/closed`；
- 租户隔离在能力表中仍标“待核实”；
- 审批覆盖依赖 syscall，旁路执行可绕过；
- 无统一权限矩阵回归测试。

**评级：身份 4.0；授权 4.0；租户 3.0。**

### 3.3 数据、隐私、密钥、审计

**已做：**

- SecretsManager：AES-256-GCM；
- PII Detector：Presidio + 正则（手机/身份证/邮箱/银行卡/地址/IP）；
- PII 全量入库路径覆盖；
- 审计链：SHA-256 chain + verify_integrity；
- memory provenance/trust_weight；
- 日志脱敏/密钥不落日志。

**未做/不足：**

- retention/删除/导出/DLP 策略不完整；
- 审计链本地，无 WORM/外部锚；
- 跨租户数据流/备份传播未验证；
- 无统一数据分类分级。

**评级：密钥 4.0；隐私 3.0；审计 3.5。**

### 3.4 AI / Prompt / 模型安全

**已做：**

- Prompt injection guard：6 条正则 + 特殊 token 过滤；
- PromptAuditRules / prompt_auditor；
- CrisisDetector / CrisisGate / EmotionTracker；
- CodeAuditor：注入/XSS/CSRF/认证/授权；
- security_view：静态安全视图；
- S1 live_llm 攻击包：25 条，ASR/leak/false refusal；
- `llm_ok_n=0` 不算 PASS。

**未做/不足：**

- 正则注入防护易绕过；
- 无系统提示泄漏专项防护/评测；
- 无模型投毒/后门/抽取评测；
- S1 样本小，未按威胁族给 n/CI；
- prompt injection 与 RAG/工具间接注入未形成完整评测。

**评级：2.5/5。**

### 3.5 工具、Agent、运行时隔离

**已做：**

- Tool RiskClass：READ/EGRESS/WRITE_LOCAL/EXEC/EXTERNAL；
- Shell command risk：危险命令 hard floor；
- ApprovalGate：25 规则，CRITICAL/HIGH/MEDIUM/LOW；
- Session Write Provenance：防写完自跑；
- Auto-Approve Reviewer：仅非 hard-floor，fail-closed；
- SandboxGate：Docker/子进程；
- microVM guest_boot authorize/探针。

**未做/不足：**

- `sandbox_real_isolation=false`；无 Linux/KVM 实测；
- 无真实工具逃逸/出网/宿主读写测试；
- 旁路 subprocess/HTTP/DB 不走 SandboxGate；
- 多 Agent handoff 安全 deferred；
- 无工具投毒/供应链完整评测。

**评级：工具 3.0；运行时 2.5；多 Agent 1.5。**

### 3.6 供应链与成果物

**已做：**

- SkillsGuard：78 威胁模式；
- Skill 签名：Ed25519；
- Dependabot/pip-audit；
- Ruff bandit；
- 密钥扫描、架构守卫、许可证检查；
- CodeAuditor、security_view、autoreview；
- builder conformance / coding closed loop。

**未做/不足：**

- 无统一 SBOM/证明链/发布门禁；
- MCP/插件供应链覆盖弱；
- 生成物无逐应用威胁模型；
- 生成代码无强制 SAST/DAST/authz 测试；
- Pi 导出不搬核心门禁。

**评级：供应链 2.5；成果物 2.5。**

### 3.7 审计、运营、人因、合规

**已做：**

- SHA-256 审计链；
- trace/span/审批 provenance；
- 漏洞 SLA、自动渗透、ZAP baseline；
- 回滚指引/checkpoint；
- EU AI Act 自评、SOC2/ISO 映射。

**未做/不足：**

- 无外部不可篡改锚；
- 无 IR 演练/漏洞披露；
- 审批疲劳/透明度未做用户研究；
- 无正式认证/数据驻留证明。

**评级：审计 3.5；运营 3.0；人因 2.5；合规 2.0。**

---

## 4. 成果物自身安全质量

### 4.1 Generated App

**已做：**

- Builder 模板 + conformance；
- `apply_architecture_profile`；
- coding closed loop：sandbox + done_verify + testability + autoreview；
- 生成物运行走 daemon_jobs；
- 平台侧 PolicyGate 横切。

**未做：**

- 无逐应用威胁模型；
- 无 authz/IDOR/SSRF/XSS 专项验收；
- 无生成 App 的 DAST；
- 生成 App 自建 DB/API 可绕平台租户隔离；
- 无安全发布门。

**评价：中低。平台内可用，不能称“应用安全”。**

### 4.2 Generated Agent

**已做：**

- AGENT.md/契约、required tools/skills；
- 平台内 PolicyGate/ApprovalGate/SandboxGate；
- trace/audit；
- mode-aware 安全评测（在研）。

**未做：**

- 导出 Pi 后无平台门禁；
- 无 Agent 级威胁模型；
- 无多 Agent 信任模型；
- 工具/记忆投毒未系统测。

**评价：中。平台内中，平台外低。**

### 4.3 Generated Skill

**已做：**

- Ed25519 签名；
- SkillsGuard 78 模式；
- 权限声明；
- SkillSimulator/AutoLearner 的 CodeAuditor。

**未做：**

- handler 代码未必被完整安全审查；
- 第三方依赖/网络出口未系统限制；
- 无 Skill 级 authz/tenant 测试。

**评价：中。注册期有门，运行期依赖平台。**

### 4.4 Generated Code

**已做：**

- CodeAuditor 5 规则；
- security_view（heuristic）；
- autoreview security preset/panel；
- 单测/testability；
- 密钥/依赖扫描。

**未做：**

- 不是 SAST/DAST；
- 无污点分析/数据流；
- 无 authz/tenant 测试；
- 无生成代码 SBOM；
- LLM 审查会漏。

**评价：中低。辅助审查，不是安全保证。**

### 4.5 Pi 导出包

**已做：**

- 企业工具门禁（opt-in）；
- 审批桥（opt-in）；
- 工具代理 allowlist；
- 原生工具默认 block。

**未做：**

- 不搬 PolicyGate；
- 不搬 ApprovalGate；
- 不搬 MemoryManager；
- 安全能力依赖企业配置；
- 无 Pi 侧安全验收。

**评价：低。导出即降级。**

### 4.6 文档 / 报告

**已做：**

- PII 脱敏；
- 审计；
- 安全声明边界。

**未做：**

- 生成内容可能含注入/敏感信息；
- 无自动敏感信息扫描门；
- 无对外发布审批。

**评价：中低。**

---

## 5. 共享责任矩阵

| 维度 | 平台 | 成果物 | 平台外 |
|---|---|---|---|
| 身份/租户 | ✅ | ❌ | 自建 |
| PolicyGate/审批 | ✅ | 声明权限 | ❌ |
| 沙箱 | ✅（Docker） | 工具选择 | ❌ |
| 审计 | ✅ | 自己的日志 | 自建 |
| PII/密钥 | ✅ | 正确使用 | 自建 |
| Prompt 注入 | 部分 | 输入/输出处理 | 自建 |
| 工具/记忆投毒 | 部分 | 设计/测试 | 自建 |
| 供应链 | 扫描/签名 | 依赖/制品 | 自建 |
| 安全测试 | 平台基线 | 逐成果物 | 自建 |
| 威胁模型 | 平台级 | 应用级 | 自建 |

---

## 6. 对照 2025–2026 公开框架

| 框架 | 核心要求 | aiPlat 现状 |
|---|---|---|
| [OWASP Top 10 for LLM 2025](https://genai.owasp.org/2024/11/17/owasp-reveals-2025-top-10-risks-for-llms-new-sponsorship-program/) | 注入、敏感信息、供应链、投毒、输出处理、过度代理、系统提示泄漏、向量弱点、错误信息、无界消耗 | 覆盖一部分；系统提示泄漏、向量弱点、投毒弱 |
| [OWASP Agentic AI Top 10](https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/) | 目标劫持、工具滥用、身份/权限、记忆投毒、多 Agent、人因、供应链 | 工具/审批有基础；记忆/多 Agent 弱 |
| [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) | 治理、测度、风险管理、生命周期 | 有意识；无正式映射/审计 |
| [MITRE ATLAS](https://atlas.mitre.org/) | 对抗 ML 战术 | 有攻击包；缺 ATLAS 映射 |
| [ISO/IEC 42001](https://www.iso.org/standard/42001) | AI 管理体系 | 有自评；未认证 |
| [Google SAIF](https://safety.google/cybersecurity-advancements/saif/) | 安全默认、威胁建模、供应链、检测响应 | 部分；secure-by-default 不足 |
| [Microsoft Agent Failure Modes](https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents/) | 工具污染、记忆、身份、人机边界 | 工具/审批有；记忆/工具污染弱 |
| [CSA MAESTRO](https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro) | Agentic 威胁建模 | 未系统采用 |

---

## 7. 风险登记

### P0（安全基线，必须先做）

| ID | 风险 | 影响 | 建议 |
|---|---|---|---|
| P0-1 | PolicyGate fail-open 默认 | 故障时越权 | 生产默认 `ask/closed` |
| P0-2 | 无独立渗透/认证 | 不能对外称安全 | 外部渗透立项 |
| P0-3 | microVM 未实测 | 工具逃逸风险 | Linux/KVM 探针+负向对照 |
| P0-4 | 生成 App 无 authz/tenant 验收 | IDOR/越权 | 模板 + 测试门 |
| P0-5 | 生成代码无强制 SAST/DAST | 漏洞入产物 | 发布门 |

### P1（能力补齐）

- SBOM/签名/证明链；
- 记忆/工具/多 Agent 投毒评测；
- Prompt injection 对抗集；
- 生成物安全 manifest；
- Pi 安全基线；
- 审计外部锚。

### P2（认证与治理）

- ISO 42001/NIST AI RMF 映射；
- 外部红队；
- IR/漏洞披露；
- 认证范围声明。

---

## 8. 建议路线

| 阶段 | 内容 | 周期 |
|---|---|---:|
| 0–1 月 | PolicyGate fail-closed、生成物安全 manifest、SAST/密钥/依赖门、外部渗透立项 | 4 周 |
| 1–3 月 | microVM 探针、authz/tenant 测试模板、Prompt 对抗集、SBOM | 8–12 周 |
| 3–6 月 | 记忆/工具/多 Agent 安全评测、Pi 基线、外部红队 | 12–24 周 |
| 6–12 月 | ISO 42001/NIST 映射、认证、IR/披露 | 24–48 周 |

---

## 9. 最终判断

### 可以说

- aiPlat 有工程级纵深防御；
- 平台内标准执行路径有基线防护；
- 生成物有安全约束/检查/签名；
- 有 S1 评测和自动扫描。

### 不能说

- 已通过安全认证；
- 成果物自动安全；
- Pi 导出后仍有平台级防护；
- S1 = 生产安全；
- microVM 已覆盖；
- Prompt injection 已完全防住。

### 一句话

> **aiPlat 已经“有安全工程”，但还没有“被证明的安全”；成果物已经“考虑安全”，但还没有“自身安全验收”。**

---

## 附录 A：证据索引

| 证据 | 路径 |
|---|---|
| 安全架构 | `docs/security/security-architecture.md` |
| 安全测试 | `docs/security/security-testing.md` |
| 自动渗透 | `docs/security/security-pen-test-report.md` |
| EU AI Act | `docs/architecture/eu-ai-act-compliance.md` |
| 合规矩阵 | `docs/audit/compliance-matrix.md` |
| 安全能力 | `AIPLAT_CAPABILITIES.md` 第七节 |
| S1 说明 | `packages/aiplat-evaluation/docs/a3/S1_LIVE.md` |
| S1 攻击包 | `packages/aiplat-evaluation/docs/a3/s1_live_attacks.v0.json` |
| 安全评测方案 | `docs/architecture/plans/eval-agent-security-exam-scheme.md` |
| 信任边界 | `docs/architecture/plans/eval-trust-boundary-lab-vs-cert.md` |

## 附录 B：缩略语

| 缩写 | 含义 |
|---|---|
| ASR | Attack Success Rate |
| DAST | 动态应用安全测试 |
| IR | 事件响应 |
| PII | 个人可识别信息 |
| SAST | 静态应用安全测试 |
| SBOM | 软件物料清单 |
| WORM | 一次写入多次读取 |

## 附录 C：报告限制

- 未执行新的动态渗透；
- 未验证生产配置；
- 未做客户数据/多租户生产测试；
- 评分是工程判断，不是认证；
- 报告随代码/配置变化需复核。
