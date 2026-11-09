# aiPlat 平台与成果物安全质量报告 v3（复审更新）

> **版本**：v3.2 · 2026-11-09（附录 D：改进方案工程收口进度；仍非认证）  
> **定位**：**当前最可信的工程安全质量基线**；**不是**完整代码审计、动态渗透或安全认证  
> **替代优先**：本报告优先于 [v2 证据审计版](./aiplat-security-quality-report-2026-11-09-v2-evidence.md) 与 [v1 桌面评估](./aiplat-security-quality-report-2026-11-09.md)  
> **性质**：工程证据复审 / 非认证  
> **方法**：在 v2 关键发现上复核仍成立项；交叉验证 SEC/CERT-PREP/OOS + **改进方案 P0–P2 工程落地**；跑相关**单元/接口单测**；**未做**新的动态渗透、跨租户实测、外部审计  
> **诚实锁**：`security_certification=false`；`accuracy_claim=false`；工程可测 ≠ 生产有效 ≠ 认证通过  
> **执行方案**：[改进方案 v2.2](./aiplat-security-improvement-plan-2026-11-09.md) · [Ops 收口清单](./ops-closeout-checklist-2026-11-09.md)
---

## 0. 执行摘要

### 0.1 一句话结论

> **相对 v2：安全「评测与披露工程」明显增强；相对生产「控制有效性」与「成果物 secure-by-construction」结论基本不变。**  
> 平台仍是「有控制代码 + 部分自测 + 评测仪器已齐」；成果物仍是「生成链路有检查模板，缺逐应用威胁模型/验收」；对外仍不可称安全认证。  
> **v3 是诚实基线，不是安全证书。**

### 0.1b 误读禁令（管理层/市场）

| 禁止误读 | 正确读法 |
|---|---|
| 「84 项安全攻击全部通过」 | **84 个单元/接口单测**通过（`test_security_*.py` + `test_isolation_t12_p0b.py`）；≠ live 攻击 / 跨租户 / microVM 逃逸 / 外部渗透 |
| 「方案已签 = 安全结论已签」 | 签的是 **SEC-P0 工程实施基线**；≠ 四方独立审计 / 生产配置验证 / security_certification |
| 「17 族全覆盖」 | 目录有 **17** 个威胁族条目；另有 **9** OOS；达标须分族 live，默认未 covered |

### 0.2 相对 v2 的变化（本轮已验证）

| 变化 | 证据 | 是否改变「可宣称安全」 |
|---|---|---|
| Agent 安全评测方案**文档签认**为工程基线 | `status: signed_sec_p0_engineering_baseline`（签的是工程基线，**不是**安全结论） | **否** |
| SEC-P0a…P5 + P4b 工程切片落地 | `core/apps/eval/service/security_*.py` + seeds | **否**（诚实锁恒 false） |
| CERT-PREP / OOS-DEEP 跟进轨 | `security_cert_prep.py` / `security_oos_deep.py` | **否**（演练/fixture ≠ covered） |
| 安全相关**单元/接口单测** | 本次 **84 passed**（仅单测套件；≠ 渗透） | **是工程自测**；≠ 独立验证 / 动态证据 |
| `security-attack-sim.py` false-pass | **P0-1 已修**（不可达 FAIL+exit1；单测锁定） | 修好后可作 **HTTP 黑盒**证据；仍 ≠ 渗透认证 |
| PolicyGate 默认 fail-open | **P0-2 已改**：unset 时按 profile→closed/ask；函数形参 default 仍为解析兜底 | **生产切流/审计仍待 Ops** |
| `sandbox_real_isolation` | 代码路径仍强制 false | **仍不可宣称隔离 covered** |

### 0.3 三层结论（复审）

| 对象 | 结论 | 等级 |
|---|---|---|
| **aiPlat 平台控制** | 身份/权限/审批/PII/密钥/审计机制仍在；默认 fail-open、注入正则薄、隔离未实测 | **L1–L2**（实现+自测）；**非 L3** |
| **安全评测仪器** | 分族门禁、T12 三级、judge 校准协议、L5 模板、OOS 披露、CERT-PREP 已工程化 | **L2 工程仪器**；**非认证** |
| **平台生成成果物** | conformance/autoreview/CodeAuditor(5 规则) 仍在；无逐应用威胁模型/authz/DAST 强制门 | **L1–L2**；导出/Pi 仍降级 |
| **对外声明** | claims_gate / CERT-PREP 演练强制 cert=false | **不可称认证/生产安全** |

### 0.4 可以说 / 不能说（复审）

| 可以说 | 不能说 |
|---|---|
| 有纵深防御代码与多项横切控制 | 已通过安全认证 |
| 有已**文档签认**的 Agent 安全评测**工程基线**与可跑切片 | 已完成安全认证终稿 / 独立审计通过 |
| 有分族报告/OOS 自动清单/L5 声明**模板** | 已对生产发布「安全通过」 |
| guest_sim 可达 `isolation_probed`（工程） | microVM / Darwin 已 isolation_covered |
| CERT-PREP 可排练 claims_gate | explicit_authorize 自动翻 certification |
| 生成链路有 conformance / CodeAuditor | 成果物 secure-by-construction |
| 本次**单元/接口单测** 84 通过 | 84 项安全攻击/渗透全部通过 |

---

## 1. 评估范围与方法

### 1.1 范围内

- 平台身份、权限、审批、执行、数据、审计、供应链、CI；
- 生成 App / Agent / Skill / Code / Pi / 文档；
- Agent 安全评测工程资产（2026-11-09 合入）；
- v1/v2 关键发现的复核。

### 1.2 范围外（与 v2 相同）

- 新的动态渗透、漏洞利用、红队执行；
- 生产真实配置与流量；
- 多租户硬隔离实测；
- SOC2 / ISO 42001 / 等保正式审计。

### 1.3 证据等级（沿用 v2）

| 等级 | 含义 |
|---|---|
| **V** | 代码/配置直接验证 |
| **T** | 有可运行测试且本次执行 |
| **D** | 仅文档/能力表 |
| **U** | 未验证 |
| **A** | 自动脚本（须先审可信度） |

---

## 2. 关键发现复核（v2 → v3）

### 2.1 `scripts/security-attack-sim.py` false-pass — **P0-1 已修复（V+T）**

| 项 | 现状 |
|---|---|
| 不可达 | `probe_reachability` 失败 → 整次 run FAIL + exit 1（禁止 PASS） |
| S2/S4/S9/S10 | 查 guard 标记 / 必须见 429 / 禁密钥回显 / replay 拒绝 |
| S7 | **仅**未授权 HTTP 401；真逃逸属 P1-4；不宣称 isolation_covered |
| 文案 | 禁止「渗透测试通过」；标明 HTTP black-box ≠ 认证 |
| 回归 | `scripts/tests/test_security_attack_sim.py`（含不可达不得 PASS） |

**结论**：脚本可作为 **HTTP 黑盒自检**证据；仍**不是**渗透认证或隔离 covered。旧「不可达仍 PASS」假绿已关闭。

### 2.2 PolicyGate 失败模式默认 open — **仍成立（V）**

`policy_gate.py`：`resolve_policy_fail_mode` / `_parse_policy_fail_mode(..., default="open")`；文档注释写明 default open for compat/dev。

**结论**：生产必须显式 `AIPLAT_POLICY_FAIL_MODE=ask|closed`；本轮**未验证**生产 env。

### 2.3 ApprovalGate hard floor — **仍成立（V）**

`approval_gate.py`：`check_hard_floor`；逃生开关 `AIPLAT_HARD_FLOOR_DISABLED`。

**结论**：机制存在；生产是否禁用逃生开关 = **U**。

### 2.4 Secrets / PII / Audit — **仍成立（V）**

- SecretsManager AES-GCM（v2）；
- `PIIDetector.mask` + 手机/身份证/邮箱/银行卡等正则；
- AuditLogger SHA-256 链（v2）。

**结论**：实现存在；KMS 轮换 / 全链路 PII / 外部锚 = **U**。

### 2.5 Prompt injection 仍为薄正则 — **仍成立（V）**

`llm.py` `_INJECTION_PATTERNS`：**6 条**英文向正则 + 特殊 token 过滤；可 env 关闭 `AIPLAT_PROMPT_INJECTION_GUARD`。

**结论**：有基线；对抗评测 / 多语言 / 间接注入通道 = **U**。不可说「已防住注入」。

### 2.6 隔离诚实锁 — **仍成立且工程化加强（V+T）**

- 多处 `sandbox_real_isolation: False`（microVM track / T12 P4）；
- T12 三级：`isolation_admitted` / `probed` / `covered`（covered 需人审）；
- `guest_sim` 可工程达 probed；`guest_live` deny 无 escape_executor 则不进 probed。

**结论**：假绿防线在评测层加强；**仍无** Linux/KVM 生产级 covered 证据。

---

## 3. 本轮新增：Agent 安全评测工程基线（V+T）

### 3.1 方案与切片状态

| 项 | 状态 | 说明 |
|---|---|---|
| 方案 | `signed_sec_p0_engineering_baseline` | **文档签认 = SEC-P0 工程实施基线**；**≠** 安全结论 / 独立审计 / 生产验证 / certification |
| SEC-P0a…P5 / P4b | Done | 分族、T12、judge、severity、T13、S1/UI、L5 模板、L3 packs、guest_live hooks |
| CERT-PREP | Done | 分族候选 + judge/G2b 工作流 + L5 演练；cert 恒 false |
| OOS-DEEP | Done | OOS-07/04/06/05 fixture；01–03 研究拒测；08/09 出轨 |

### 3.1b 威胁族计数口径（防评审对不上）

| 口径 | 数量 | 权威来源 |
|---|---:|---|
| **威胁族目录 keys（工程权威）** | **17** | `threat_family_catalog.v1.yaml` → `families`（含 `T05-text-refusal` / `T05-exec` / `T13-escape`） |
| **方案 §2.3 taxonomy 表行** | **17** | 与目录一一对应（T05 已拆、含 T13-escape） |
| **名义编号 T01–T15** | 15 | 未计拆分前的口头简称；**勿**与 17 直接相加 |
| **OOS 披露项** | **9** | OOS-01…09（另列，不算进 17 族 covered） |
| **方案他处「T…」引用行** | 可变 | 缺口/进度表会再次出现 T05-exec、T12、T13 等；**勿与威胁族数累加成 19** |

> **统一说法**：工程上写「**17 个威胁族 + 9 个 OOS**」；若看到「19」，先核是否误把非 taxonomy 引用行计入。

### 3.2 资产规模（相对 v2）

| 资产 | v2 | v3（本轮） |
|---|---:|---|
| S1 攻击包 | 25 | 25（仍 facilitation） |
| A7 safety.json | 8 | 8（已补 threat_ids 等标注能力） |
| 威胁族目录 | — | **17** 族 + **9** OOS（见 §3.1b） |
| T12 逃逸探针目录 | — | 4（含负向对照） |
| T13 allowlist 探针 | — | 有种子包 |
| L3 S-Tool/S-RAG | — | 有种子包 |
| OOS 工程探针 | — | 07:5 / 04:4 / 06:3 / 05:5 |
| **单元/接口单测**（本次） | 未系统跑 | **84 passed**（仅 `test_security_*.py` + `test_isolation_t12_p0b.py`；**≠** live/渗透） |

### 3.3 评测层能证明 / 不能证明

| 能证明 | 不能证明 |
|---|---|
| 分族 `min_n` / CI / report_only 门可机算 | 生产 ASR 已达标 |
| L1 文本与 T05-exec 命名分层 | L1 通过 = 防删库 |
| admit ≠ probed ≠ covered | Darwin/microVM covered |
| OOS 自动列入披露 | OOS-01…06 已 covered |
| L5 模板拒假绿句式 | 已签发范围限定认证声明 |
| CERT-PREP 演练 claims_gate | accuracy_claim 可自动 true |

---

## 4. 证据矩阵（20 维复审）

| # | 维度 | 状态 | 相对 v2 | 说明 |
|---|---|---|---|---|
| 1 | 治理/威胁模型 | D→**D/V** | ↑ 有签字评测方案 | 仍缺平台逐系统正式 threat model |
| 2 | 安全需求 | D | ≈ | CAPABILITIES/registry 有安全评测条目 |
| 3 | 独立验证/红队 | U | ≈ | G2b/CERT-PREP 仅工作流；无外部报告 |
| 4 | 认证/合规 | U | ≈ | cert 锁死 false |
| 5 | 身份认证 | D/T | ≈ | admin MFA 创建 API key 有测试锚点 |
| 6 | 授权/最小权限 | V | ≈ | PolicyGate/ApprovalGate；默认 fail-open 风险仍在 |
| 7 | 租户/数据隔离 | U | ≈ | OOS-04 仅 fixture 目录；无实测 |
| 8 | 隐私/生命周期 | D/V | ≈ | PII mask 在；retention/删除 U |
| 9 | 密钥/凭据 | V | ≈ | AES-GCM；KMS U |
| 10 | 审计 | V | ≈ | SHA-256 链；外部锚 U |
| 11 | 输入/注入 | V | ≈ | 6 正则；对抗 U |
| 12 | 输出处理 | D/V | ≈ | CodeAuditor 5 规则 |
| 13 | 模型/系统提示 | D | ↑ 微 | OOS-07 fixture 目录；无 live 专项证明 |
| 14 | 工具/Agent | V/D | ↑ | L3 packs / T13 浅测种子；沙箱弱 |
| 15 | 记忆/RAG | D | ≈ | 投毒/间接注入 live U |
| 16 | 多 Agent | U→**D/V** | ↑ | T11 deferred 门 + OOS-05 fixture；未毕业 |
| 17 | 运行时隔离 | U→**V/T** | ↑ | T12/P4 状态机+单测；covered/生产仍 U |
| 18 | 供应链 | D | ↑ 微 | T13 浅测 + OOS-06 披露；无 SBOM/证明链 |
| 19 | 成果物安全 | D | ≈ | conformance/promotion_gate；无 authz/DAST 强制 |
| 20 | IR/合规运营 | D/U | ≈ | 无演练/外部审计 |

> **平台控制有效性**：仍约 **工程 3.2/5 量级**（判断分，非认证）。  
> **保证/认证**：仍约 **1.6–2.0/5**。  
> **评测仪器成熟度**：相对 v2 **明显上升**（约 +1 档工程分），但**不计入**认证分。  
> **成果物自身**：仍约 **2.3/5**。

---

## 5. 平台评估（复审）

### 5.1 已确认（V/T）

- PolicyGate / ApprovalGate hard floor 代码存在；
- Secrets AES-GCM、PII mask、审计链存在；
- Prompt injection 基线 6 正则存在；
- Agent 安全评测工程基线已**文档签认**并实现切片（签的是工程基线，不是安全结论）；
- 安全评测相关**单元/接口单测**本轮 84 通过（≠ 动态渗透）；
- admin MFA 强制创建 API key 有测试表述。

### 5.2 仍不能确认（U）

- 生产 `AIPLAT_POLICY_FAIL_MODE` 是否 closed；
- hard floor 逃生开关是否关闭；
- 跨租户硬隔离全链路；
- 注入对抗有效性；
- Linux/KVM isolation_covered；
- 外部渗透/认证。

### 5.3 平台结论

> **「有控制 + 有评测仪器」可以确认；  
> 「控制在生产有效」仍只能部分确认；  
> 「平台已安全认证」不能确认。**

---

## 6. 成果物评估（复审）

| 成果物 | 已确认 | 未确认 | 结论 |
|---|---|---|---|
| Generated App | conformance / promotion_gate / hop_metrics | 逐应用威胁模型、authz/IDOR/SSRF、DAST | 契约门 ≠ 安全验收 |
| Generated Agent | 平台门禁/契约 | 导出后护栏、mode-faithful 安全 live | 平台内依赖平台 |
| Generated Skill | SkillsGuard/签名/CodeAuditor | handler 深度审计、供应链证明 | 注册期有门 |
| Generated Code | CodeAuditor **5** 规则 | 强制 SAST/污点/密钥门 | 辅助审查 |
| Pi | 企业门禁文档 | 导出后无 PolicyGate 继承 | **导出即降级** |
| 文档/报告 | PII/审计 | 内容安全扫描 | 中低 |

**成果物结论（不变）：**

> **没有证据表明「所有生成物都经过安全验收」；只能确认「生成链路有安全检查和模板」。**  
> 评测侧新增的 OOS/L3/T13 包是**评测资产**，不自动变成生成物发布门。

---

## 7. 优先缺口（更新后排序）

> 完整验收见改进方案 **v2.2（批准执行）**。此处仅列标题。

### P0（HTTP/门禁/IR；**不含**真逃逸）

1. 修 attack-sim false-pass（S7=未授权 401 等 HTTP 语义；**真逃逸不在此**）；  
2. fail-closed 灰度（故障真拒绝+审计）；  
3a. manifest + **canonical hash/验签** + SAST/密钥/依赖；  
3b. authz pilot（2 类×≥3 样本+负向+Owner 退出）；  
4. Pi 导出器自动披露；P0-IR 止损。

### P1（Subject=Agent 组合；真逃逸在此）

5. 文本族 live（禁止裸 LLM）；工具族后期；  
6. judge 校准；跨租户/注入；  
7. **P1-4 Linux/KVM 真逃逸**（最多 probed；covered 不自动）；  
8. 证据卡统一。

### P2

9–11. SBOM；外部 RFP/红队；正式 IR/认证可选。

---

## 8. 与改进计划的关系

[`aiplat-security-improvement-plan-2026-11-09.md`](./aiplat-security-improvement-plan-2026-11-09.md)（**v2.2 · 批准执行**）。  
相对 v2.1 四条技术修订：S7 真逃逸→P1-4；pilot 退出写死；P1-1 Subject 锁定；canonical hash+验签方写死。  
评测仪器已齐；**P0–P2 尚未关闭** — 可开变更单。

---

## 9. 总体结论

### 一句话

> **v3：评测工程从「弱连接」升级到「已文档签认、可跑的 SEC 工程基线」；生产控制与成果物安全验收相对 v2 无质变。  
> 有控制代码、有评测仪器、有 84 个安全单测、有分族/OOS 披露、有 CERT-PREP 演练；仍无生产有效性、动态渗透、外部审计和认证。  
> v3 是诚实基线，不是安全证书。下一步应先修 attack-sim、强制 fail-closed、补动态/外部验证，再谈 v4。**

### 使用限制

- 本报告不是认证、不是渗透通过证明、不是完整代码审计；  
- 禁止把「84 passed」写成「84 项攻击通过」；  
- 禁止把「signed_sec_p0_engineering_baseline」写成「安全结论已签」；  
- 禁止用于对外「安全通过 / 可上生产」营销；  
- 结论随代码与配置变更须复核。

---

## 附录 A — 本轮核查锚点

| 锚点 | 用途 |
|---|---|
| `scripts/security-attack-sim.py` | **P0-1 已修**（不可达 FAIL；HTTP only） |
| `core/harness/infrastructure/gates/policy_gate.py` | **P0-2**：profile 默认 closed/ask；open 须 UNTIL（生产切流仍待 Ops） |
| `core/harness/infrastructure/gates/approval_gate.py` | hard floor |
| `core/harness/syscalls/llm.py` | 6 条注入正则 |
| `core/harness/security/code_auditor.py` | 5 规则 |
| `core/services/pii_detector.py` | PII mask |
| `docs/architecture/plans/eval-agent-security-exam-scheme.md` | 文档签认工程基线（≠ 安全结论） |
| `threat_family_catalog.v1.yaml` `families` | **17** keys（权威族计数） |
| `core/apps/eval/service/security_*.py` | SEC / CERT-PREP / OOS-DEEP |
| `workspace_seeds/eval/agent_capability/security/*` | 威胁族/探针种子 |
| `pytest …/test_security_*.py` + `test_isolation_t12_p0b.py` | **84 passed（单元/接口单测）** |

## 附录 B — 本轮未做（相对认证/生产有效性）

- 未启动服务做完整动态渗透；  
- 未跨租户**生产**实测（P1-3 工程探针已有，黑盒仍待）；  
- 未 Linux/KVM **真** guest escape live（P1-4 工程通道已有）；  
- 未生成 App 全量 DAST；  
- 未外部审计 / 未发标；  
- ~~未修复 attack-sim 脚本~~ → **P0-1 已修**。

## 附录 C — 版本关系

| 版本 | 角色 |
|---|---|
| v1 | 桌面评估（含不可信自动渗透引用）— 仅对比 |
| v2 | 首次证据审计，撤回自动渗透证据 |
| v3 / v3.1 | 复审 v2 + SEC/CERT-PREP/OOS 工程进展 |
| **v3.2** | **现行**：+ 改进方案 P0–P2 工程收口进度（仍非认证） |

## 附录 D — 改进方案工程收口（v3.2）

| 档 | 工程状态 | 生产/认证状态 |
|---|---|---|
| P0（HTTP/门禁/manifest/IR 卡） | **已落地** | Ops 切流/联系人/pilot 退出仍待 |
| P1（Subject live / judge / 动态 / KVM 架） | **已落地** | 真 live / 真人审 / 真 KVM 仍待 |
| P2（SBOM 门 / RFP / IR 草案） | **工程+草案** | 发标/邮箱/认证立项仍待 |
| Ops 审计脚本 | **已落地** | `security_ops_audit.py` 报告缺联系人等；`--strict` 仅齐备后启用 |

验证：
- `python3 scripts/security_plan_closeout_check.py` → 工程 exit 0 ≠ `security_certification`
- `python3 scripts/security_ops_audit.py` → 默认 exit 0（advisory）；联系人未填时 `ok=false` 但仍非认证失败
