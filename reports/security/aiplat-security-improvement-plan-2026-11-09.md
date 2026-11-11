---
doc_type: Report
---

# aiPlat 安全质量改进方案

> **版本**：v2.2 · 2026-11-09（可执行修订：S7 分层 / pilot 退出 / Subject / canonical 签名）  
> **类型**：安全改进计划 / 执行方案  
> **依据**：现行 [`v3.1 安全质量报告`](./aiplat-security-quality-report-2026-11-09-v3.md)  
> **核心命题**：v3 已有**评测仪器**；下一步是把仪器变成**可验证证据**——**不是再堆安全功能**  
> **状态**：**批准执行**（附 §0.5 条件 + §0.6 四条技术修订）  
> **评审**：9.5/10 — 结构已可执行；本版修层级/硬定义矛盾  
> **诚实锁**：`security_certification=false`；`accuracy_claim=false`；本方案不承诺认证通过

---

## 0. 执行摘要

### 0.1 一句话

> **这版已经可执行；把「P0 做真逃逸」这个层级错误修掉，并给 pilot / Subject / 签名补上硬定义后，即可开变更单。**

### 0.2 目标状态（相对 v3）

| 从（v3） | 到（本方案验收后） |
|---|---|
| 有控制代码 + 84 单测 + SEC 仪器 | attack-sim **HTTP 语义**可信；生产 fail-closed **可证明拒绝** |
| fixture / guest_sim / admit | 有环境才 live；无环境标 `unknown`；Subject=Agent 组合 |
| 生成链路有检查模板 | manifest **canonical hash + 可验证签名**；authz pilot 有退出条件 |
| Pi 默认可被误解为平台级安全 | **导出器自动生成**丢失控制披露 |
| 无基本 IR | P0 联系人/止损/回滚；P1 演练；P2 正式披露/认证 |

### 0.3 优先级总览

| 档 | 项 | 不做的后果 |
|---|---|---|
| **P0** | P0-1（HTTP only）…4 + P0-IR + P0-3a | 后续皆假绿 |
| **30–60** | P0-3b pilot + P1 文本族（Subject 锁定）等 | 仪器停在 fixture |
| **60–90** | 工具族 live、**P1-4 真逃逸**、SBOM、RFP | 无隔离与外部入口 |
| **90+** | 红队、认证、多 Agent 深度 | 无外部保证 |

### 0.4 进度快照（相对 v3.1）

| 工作项 | 状态 |
|---|---|
| SEC / CERT-PREP / OOS 评测仪器 | **已落地（工程）** — **不再**以加 fixture 当成绩 |
| P0-1 attack-sim（HTTP 语义） | **已修** — 不可达 FAIL+exit1；S7=HTTP 401 only；`scripts/tests/test_security_attack_sim.py` |
| P0-2 fail-closed 灰度 | **已落地（代码）** — profile 默认 closed/ask；open 须 UNTIL；hard-floor 到期恢复；健康漂移检查。**生产 env 审计/灰度切流仍待 Ops** |
| P0-3a manifest + 扫描门 | **已落地** — `artifact_security_manifest.py`；deploy 接线；prod/staging 强制 |
| P0-3b authz pilot | **已落地（工程）** — 模板+账本+退出条件+API；**真人样本跑分与 Owner 批准仍待执行** |
| P0-4 Pi 自动披露 | **已落地** — `write_pi_security_disclosure` |
| P0-IR 基本止损 | **已落地（文档+SoT）** — runbook + `security/ir/contacts*.yaml`；**真人联系人仍待填入 local** |
| P1-1 文本族 live | **已落地（工程）** — Subject 锁定 + 环境矩阵 + 证据卡；scripted CI；**真 live 模型跑分仍待** |
| P1-1 工具/检索族 | **已落地（工程）** — `security_tool_retrieval_live_p1`：T05-exec/T06/T07；契约强制；无 `AIPLAT_EVAL_P1_1_TOOLS/RETRIEVAL`→unknown；**真工具面 live 仍待** |
| P1-2 judge 校准起步 | **已落地（工程）** — `security_p1_judge_session` 会话持久化 + 双盲 A/B + 仲裁；失败全量人审门；**真人标定样本仍待** |
| P1-3 跨租户/注入动态 | **已落地（工程）** — `security_dynamic_p13`：跨租户 100% 拒绝门 + 注入基线 ASR + 输出编码；transport 可注入；**对真实 staging/prod 黑盒跑分仍待** |
| P1-IR 桌面演练 | **已落地（剧本）** — `reports/security/P1-IR-tabletop-drill.md`；**真人推演与记分仍待**（联系人 TBD 时禁标 pass） |
| P1-4 真逃逸（原误放 P0-1 S7） | **已落地（工程）** — `security_p1_4_kvm_escape`：guest_boot 门 + 五类探针 + GuestChannel；HTTP≠escape；最多 probed；**真 KVM guest 通道与人审 covered 仍待** |
| P2-1 SBOM + 签名证明链 | **已落地（工程）** — `artifact_sbom_attest`：CycloneDX-lite + digest 入 manifest；MCP/插件 allowlist；HMAC 默认 / Ed25519 可选；prodish 缺 SBOM 拒发；**syft/cosign 生产加固与公钥入库仪式仍待** |
| P2-2 外部渗透 RFP | **已落地（草案）** — `reports/security/P2-2-external-pentest-rfp.md`；**发标/选商仍待** |
| P2-3 正式 IR/披露/认证 | **已落地（草案）** — `reports/security/P2-3-formal-ir-disclosure-draft.md`；**邮箱/立项仍待** |
| 工程收口门 | **已落地** — `scripts/security_plan_closeout_check.py` + CI job `security-plan-closeout` + Ops 清单；**≠认证** |
| Ops 审计脚本 | **已落地** — `scripts/security_ops_audit.py`（联系人/fail-closed/hard-floor/P2-1 密钥/工程收口）；CI advisory；`--strict` 可选；单测 `scripts/tests/test_security_ops_audit.py`；**≠认证** |

### 0.5 批准附带的 5 个条件（强制 · 承自 v2.1）

| # | 条件 |
|---|---|
| 1 | P0-3 拆 a/b；30 天只收 3a |
| 2 | fail-closed 灰度；验收=故障真拒绝+审计 |
| 3 | P1-1 环境矩阵；无环境 → `unknown` |
| 4 | IR 前移：P0 基本 / P1 演练 / P2 正式 |
| 5 | 证据卡 + manifest 哈希/签名（细节见 §4） |

### 0.6 四条技术修订（本版强制 · 相对 v2.1）

| # | 修订 | 若不修 |
|---|---|---|
| T1 | **S7 真逃逸 → P1-4**；P0-1 的 S7 只做「未授权 MCP/工具调用应 401」等 HTTP 语义 | P0-1 因无 sandbox 无法收口 |
| T2 | **P0-3b pilot 范围/样本/退出**写死 | 无限期「试点中」 |
| T3 | **P1-1 Subject = Agent×ImplMode×Config×Model×RuntimeTier**；禁止裸 `/chat/completions` | 「Agent 安全」沦为「模型安全」 |
| T4 | **canonical hash + 签名验证方**写死 | `signature` 只是装饰字段 |

另：**30–60 容量**见 §6.1；人手不足时强制降级排期。

---

## 1. P0：必须先修（不做，后面都是假绿）

| # | 改进 | 验收标准 | 排期 |
|---|---|---|---|
| **P0-1** | 修 `scripts/security-attack-sim.py` false-pass（**仅 HTTP 黑盒语义**） | 见 §1.0 | 0–30 |
| **P0-2** | PolicyGate fail-closed **灰度** | 见 §1.1；验收=故障真拒绝+审计 | 0–30 起 |
| **P0-3a** | 生成物门骨架 | schema + **canonical hash + 可验证签名** + SAST/密钥/依赖；缺项阻断；`authz_smoke` 可 `na` | 0–30 |
| **P0-3b** | App authz/IDOR/SSRF **pilot** | 见 §1.2 硬退出条件 | **30–60** |
| **P0-4** | Pi 导出披露 | **导出器自动**生成；手写 README 不得作唯一证据 | 0–30 |
| **P0-IR** | 基本事件响应 | 联系人 / 止损 / 回滚 / 24h 可达；演练在 P1 | 0–30 |

**硬约束：** P0-1/2/3a/4/IR 未完成前，禁止把「84 单测 / SEC 仪器」写成对外安全声明依据。  
**层级约束：** P0 **不**验收 sandbox escape / `isolation_covered`；真逃逸只在 **P1-4**。

### 1.0 P0-1 attack-sim 范围（T1）

`security-attack-sim.py` 是 **HTTP 黑盒**，无 sandbox 执行面。

| 场景 | 归属 | 验收 |
|---|---|---|
| 服务器不可达 | **P0-1** | **FAIL + 非零退出**（禁假 PASS） |
| S2 查 guard 语义 | **P0-1** | 断言响应体现拒绝/守卫，非仅 HTTP 码宽松通过 |
| S4 查 429 | **P0-1** | 限流语义 |
| **S7 未授权 MCP/工具调用应 401** | **P0-1** | HTTP 401/权限拒绝（当前脚本意图） |
| **S7 真实 sandbox escape**（宿主文件/网络/设备/提权） | **P1-4** | 不在 P0；缺 KVM/工具面不得宣称完成 |
| S7 → `isolation_covered` | **永不自动** | 仅人审协议后可标 covered |
| S9 查泄漏 | **P0-1** | 响应体泄漏检测 |
| S10 真实 replay | **P0-1** | replay 拒绝语义 |
| 回归测试 | **P0-1** | 锁定「不可达不得 PASS」 |
| 修好前作证据 | **禁止** | — |

### 1.1 P0-2 fail-closed 灰度

| 阶段 | 配置 | 要求 |
|---|---|---|
| dev | 默认 `ask` | 禁止把隐式 `open` 当正确 |
| staging | `closed` | 观察误杀；豁免有记录 |
| prod | 灰度 `closed` + 白名单 | owner、到期日、审计 |
| 全程 | `AIPLAT_HARD_FLOOR_DISABLED` 默认关 | 开启审计；**到期自动恢复** |
| 全程 | 配置漂移检测 | 与声明不符 → 告警 |

> 人为制造故障时敏感调用被**拒绝**且可审计；仅「写了 closed」不算通过。

### 1.2 P0-3b pilot 硬定义（T2）

```text
pilot 范围：至少 2 类 App（默认：CRUD、报表；可由 Security Owner 书面替换同类）
每类 ≥ 3 个独立生成样本
authz / IDOR / SSRF 冒烟：每样本必须 pass|fail，禁止长期 na
负向：每类至少 1 个负向用例必须被门禁阻断
pilot 通过 =
  (2 类 × ≥3 样本全部 pass)
  AND (每类 ≥1 负向被阻断)
  AND (Security Owner 书面批准退出试点)
退出后：该类 App 发布强制 authz 门；未批准退出不得宣称「生成 App 已安全验收」
超时：启动后 60 个自然日内未退出 → 状态标 blocked，不得无限「试点中」
```

---

## 2. P1：把仪器变成动态证据

> 禁止 fixture 当成绩。无环境 → `unknown`。真逃逸只在 P1-4。

### 2.0 环境矩阵

| 威胁族 | 所需环境 | 无环境时 |
|---|---|---|
| T01/T02/T03/T04/T09/T10/T15 | 文本 live（§2.0b Subject） | —（优先） |
| T05-exec / T06 | tools | `unknown` |
| T07 | retrieval + tools | `unknown` |
| T08 | sandbox / egress | `unknown` |
| T11 | multi-agent | `unknown` |
| T12 | microVM / KVM | `unknown` → **P1-4** |
| T13 | plugin / MCP | `unknown` |
| T13-escape | process_split | `unknown` |
| T14 | budget / timeout | `unknown` |

### 2.0b P1-1 Subject 定义（T3 · 强制）

```text
Subject = Agent × ImplMode × Config × Model × RuntimeTier
（可选扩展：ToolContract × RetrievalContract；无则显式 none）
```

**必须同时满足：**

| 要求 | 禁止 |
|---|---|
| 经 `create_agent` / `run_workspace_agent`（或同等正式 Agent 入口） | 仅调 `/chat/completions` / 裸 LLM SDK |
| 有可检索 **trace**（run_id / session） | 无 trace 的一次性补丁脚本 |
| 有 **system prompt / Agent 配置** 生效 | 空壳 prompt 冒充 Agent |
| 工具/检索契约显式声明（可为 `none`） | 隐式「有工具」却未接线 |
| 证据卡 `subject` 字段写全组合键 | 只写模型名 |

否则结果只能标 `model_only` / `unknown`，**不得**写入「Agent 安全 live 通过集」。

### 2.1 P1 项

| # | 改进 | 验收 | 排期 |
|---|---|---|---|
| **P1-1** | 分族 live | 环境矩阵 + Subject 锁定；文本族优先；不足 `report_only`；无环境 `unknown` | 30–60 文本；60–90 工具/检索 |
| **P1-2** | judge 校准 + G2b-S | 一致率达标；双盲/仲裁；失败全量人审 | 30–60 起步（人手不足可顺延，见 §6.1） |
| **P1-3** | 跨租户/越权/注入动态 | 跨租户可重复 100% 拒绝；注入基线 ASR | 30–60（可顺延） |
| **P1-4** | **Linux/KVM 真逃逸**（承接原 S7 逃逸） | guest_boot + 宿主文件/网络/设备/提权探针 + 负向对照 → 最多 `isolation_probed`；**永不自动** `covered` | **60–90** |
| **P1-IR** | IR 桌面演练 | 按 P0-IR 剧本推演 | 30–60 |

---

## 3. P2：保证与认证

| # | 改进 | 验收 | 排期 |
|---|---|---|---|
| **P2-1** | SBOM + 签名证明链 | 每发布物 SBOM；未签名不可发布；MCP/插件 allowlist | 60–90 |
| **P2-2** | 外部渗透 + 独立红队 | 60–90 RFP；90+ 第三方报告+高危闭环 | 60–90 → 90+ |
| **P2-3** | 正式 IR / 披露 / 认证路径 | 正式流程；标准映射；认证可选 | 90+（基本 IR 已在 P0） |

---

## 4. 证据卡与 Manifest 签名（T4 · 写死）

### 4.1 证据卡最小字段

```json
{
  "claim": "string",
  "subject": "Agent×ImplMode×Config×Model×RuntimeTier",
  "pack": "string",
  "manifest_hash": "string",
  "runtime": "string",
  "environment": "text|tools|retrieval|sandbox|kvm|multi-agent|none",
  "n": 0,
  "ci": [0.0, 1.0],
  "result": "pass|fail|unknown|report_only|fixture|model_only",
  "evidence_path": "string",
  "owner": "string",
  "date": "YYYY-MM-DD"
}
```

- `fixture` / `model_only` / `unknown` **不得**进入对外 pass 声明集。

### 4.2 `manifest_hash` canonical 规则

| 规则 | 规定 |
|---|---|
| 编码 | UTF-8 |
| 序列化 | JSON Canonical：对象键**字典序**；`separators=(',', ':')`（无多余空白）；数组保序 |
| **纳入哈希的字段** | 除下方排除项外的全部业务字段（含 `artifact_id`、扫描结果、`claim_boundary`、`platform_controls_*`、`authz_smoke` 等） |
| **排除字段**（写入前剥离再算） | `manifest_hash`、`signature`、`signed_at`、`reviewer_notes`、`generated_at`（若仅作墙上时钟）、任意 `_*_local` |
| 算法 | SHA-256，输出小写 hex |
| 签名覆盖 | 签名覆盖的是 **`manifest_hash` 字节串**（或等价 `sha256:<hex>`），**不是**含签名字段的整文件随意串 |

复算：剥离排除字段 → canonical dumps → sha256 → 与文件内 `manifest_hash` 比对。

### 4.3 签名 / CI attest 验证方

| 项 | 规定 |
|---|---|
| **谁签** | CI job（推荐）或 Platform Security 发布密钥；开发者笔记本自签**默认不进生产门** |
| **公钥位置** | 仓库或密钥目录固定路径（如 `security/keys/artifact-manifest-ci.pub` / 平台 KMS key id）；变更走 PR |
| **算法** | Ed25519 或与平台现有 attest 对齐；方案实施时在变更单写死一种 |
| **发布门如何验** | ① 复算 hash；② 用公钥验 `signature`；③ 二者任一失败 → **拒绝发布** |
| **本地手改如何失效** | 改 `sast.status` 等纳入字段 → hash 变 → 旧签名失效 → 门禁拒绝 |
| **无公钥环境** | 不得跳过；只允许 `result=unsigned_dev` 且**禁止**生产通道 |

---

## 5. 应该停止做的事

1. 84 单测 ≠「安全测试通过」；  
2. 未修前的 attack-sim 输出不作证据；  
3. S1 25 ≠ 生产安全；  
4. guest_sim / admit ≠ isolation covered；  
5. Pi 不继承平台安全声明；  
6. 无动态证据不签认证；  
7. fixture 不冒充 live；  
8. **P0 不做真逃逸 / 不标 isolation_covered**；  
9. 裸 LLM API 不冒充 Agent live；  
10. 无 canonical/验签的 manifest「pass」不放行；  
11. P0-3b 不得无限「试点中」。

---

## 6. 30 / 60 / 90 / 90+（修订版）

| 周期 | 只做 |
|---|---|
| **0–30** | P0-1（**不含** S7 真逃逸）、P0-2 灰度、P0-3a、P0-4、P0-IR |
| **30–60** | P0-3b pilot（硬退出）、P1-1 **文本族**（Subject 锁定）、P1-2 校准起步、P1-3 跨租户/注入、P1-IR；prod fail-closed 加深 |
| **60–90** | P1-1 工具/检索族、**P1-4 KVM 真逃逸**、P2-1 SBOM、P2-2 RFP、IR 草案 |
| **90+** | 外部红队、认证可选、多 Agent/供应链深度 |

### 6.1 容量与降级（强制）

| 配置 | 30–60 可承诺 |
|---|---|
| **最低满配**：1 Security Owner + 2 Eng + 0.5 QA | P0-3b + P1-1 文本 + P1-2 起步 + P1-3 + P1-IR |
| **仅 1 人** | **只做** P0-3b + P1-1 文本族；**P1-2 / P1-3 / P1-IR 顺延到 60–90** |
| 开窗前 | Security Owner 书面确认人员配置；不符满配则自动启用降级表 |

---

## 7. 验收门

| 门 | 阻断 |
|---|---|
| **G-P0** | 不可达仍 PASS；P0 宣称真逃逸/covered；无哈希验签仍发布；Pi 仅手写披露；无 IR 联系人 |
| **G-P0b** | pilot 未达 §1.2 退出条件却宣称 App 安全验收 |
| **G-P1** | fixture/model_only 进 live 通过集；裸 LLM 冒充 Agent；guest_sim 冒充 covered |
| **G-P2** | 无 SBOM/签名；自评代替第三方；无证据卡 |

---

## 8. 成果物契约（摘要）

见 §4 + `artifact.security.json`：含 `manifest_hash` / `signature`；Pi 的 `platform_controls_lost_on_export` 由导出器写入；P0-3a 允许 `authz_smoke=na`；P0-3b 试点类型禁止长期 `na`。

---

## 9. 原则

evidence over claims · fail-closed（可证灰度）· shared responsibility · instruments ≠ evidence · no environment → unknown · **HTTP ≠ escape** · **Agent Subject ≠ model-only** · no security theater。

---

## 10. RACI / 风险（摘）

| 事项 | A | R |
|---|---|---|
| P0-1 HTTP | Security Owner | Platform Eng |
| P0-2 灰度 | Platform Security | Eng + Ops |
| P0-3a/b、P0-4 | Product Security | Builder/Platform |
| P0-IR / P1-IR | IR Lead | Ops + Security |
| P1-1 Subject/live | Security Owner | Eval + QA |
| **P1-4 真逃逸** | Platform Security | Infra |
| P2 | Exec Sponsor | Security Owner |

| 风险 | 缓解 |
|---|---|
| P0 塞进逃逸 | **T1** 分层 |
| pilot 无限期 | **T2** 退出条件 |
| 测模型当测 Agent | **T3** Subject |
| 签名不可验 | **T4** canonical + 公钥 |
| 30–60 过载 | **§6.1** 降级 |

---

## 11. 结论

**批准执行（v2.2）。** 结构条件（§0.5）与技术修订（§0.6）均已写入正文。

> **评测仪器 →（正确层级的）HTTP/Agent/KVM 证据 → 可复算门禁 → 范围限定声明。**

**一句话：开变更单；P0 只收假绿与门禁骨架，真逃逸留给 P1-4；pilot / Subject / 签名按硬定义验收。**

---

## 12. 工程收口（2026-11-09 实施后）

| 检查 | 命令 / 路径 |
|---|---|
| 工程清单 | `python3 scripts/security_plan_closeout_check.py`（exit 0 ≠ 认证） |
| Ops 人审清单 | [`ops-closeout-checklist-2026-11-09.md`](./ops-closeout-checklist-2026-11-09.md) |
| CI | `.github/workflows/ci.yml` job `security-plan-closeout` |

**工程结论：** P0–P2 **可编码项已落地**（见 §0.4）。  
**未结论：** Ops/真人/真 KVM/外部渗透/认证 — 见 ops 清单；`security_certification` 仍为 false。