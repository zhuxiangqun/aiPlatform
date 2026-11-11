---
doc_type: Report
---

# aiPlat Evaluation 产品评审基线

> **评审日期**：2026-11-04  
> **仓库基线**：`df303eff`（工作区源码与构建产物存在差异，见 §7）  
> **用途**：供后续版本复评、发布门禁和产品范围讨论时逐项对照  
> **总体判断**：工程基础和证据治理较强；评测效度、跨对象可比性、高级能力评测及发布一致性仍需收口。  
> **强制边界**：`accuracy_claim=false`；`process_split_authorized=false`；评测报告不替代安全认证、FDE 客户签收或生产拆分授权。  
> **文档入口**：[`../modules/evaluation/README.md`](../../../docs/products/five-products/modules/evaluation/README.md) · 生命周期 [`EVAL_DOCS_LIFECYCLE.md`](./EVAL_DOCS_LIFECYCLE.md)（CLOSEOUT 等已迁 `_archive/eval-receipts/`）。

---

## 1. 执行摘要

aiPlat Evaluation 已搭建首版评测工程骨架：管理端评测中心、评测 API 与协议、任务和报告存储、runner/worker、复核、门禁、证据归档，以及本地运行和运维演练材料。首版对象包括 Agent、Skill、Prompt、KB/RAG、Arena、Code Review；另有 Session、Preference、G2b 人工标注、S1 安全和 Compliance/PII 检查。

仓库记分卡在 **SCORE_SCOPE_V1 限定范围**内记录功能覆盖、工程架构和“不含 microVM 的本地独立”均为 5/5。该分数表示项目定义范围内的工程与证据条件满足，**不表示**通用评测能力完整、模型准确率认证通过或已经具备生产独立部署。

本次评审确认的首要事项是管理端发布一致性：源码定义 15 个 tab，当前仓库 `dist` bundle 仍只有旧 10 个 tab，并保留旧横幅与 `/diagnostics/eval` route/chunk。**这是发布阻断项**：发布前必须重建构建产物，并在实际部署环境确认 `/eval` 的 tab、文案和入口行为。

其他关键判断：

- G2b 当前有 n=30 的双标和 adjudicated gold 聚合：23/30 通过，pass rate 约 76.7%，Wilson 95% CI 约 [0.59, 0.88]，inter-annotator κ≈0.627；31–100 尚待双标，准确率声明仍关闭。
- `evidence_manifest.v1.json` 已入仓；双人真实性 attestation 为 confirmed。`scorecard_v1_check.sh` 校验聚合哈希、说明文件哈希和 attestation，避免无证据地把功能覆盖报为 5/5；但哈希并不能证明样本代表性或测量效度。
- 有些评分是工程启发式：Arena 按回答长度决定 winner；`text_quality` 看长度、可打印字符和精确匹配；部分 groundedness 使用 token overlap。它们适合 smoke 或局部回归，不宜按名称解读为充分的质量测量。
- 上下文、记忆和自学习在系统其他模块有实现或设计，但 Eval Center 尚无完整的高级能力基准；评估器自校准仍是设计存档、未实现。
- API 路由有鉴权和 tenant 过滤实现；UI 将 tenant 固定为 `eval-v1`；保留策略仍 TBD。D2/D3 本地工程收口不等于生产 SLO、灾备或独立部署授权。

## 2. 产品定位与范围

### 2.1 产品定位

Evaluation 面向 aiPlat 产物提供评测、比较、复核、门禁和证据组织。它回答“当前版本在已定义任务和评测集上是否回归、是否满足本地门禁”，不拥有源系统运行事实，不代替 Diagnosis 根因分析，也不代替 FDE 客户验收。

### 2.2 架构归属

| 层 | 位置 | 职责 |
|---|---|---|
| 产品根 | `packages/aiplat-evaluation/` | contracts、store、runner/worker、scoring、sandbox、tests、部署材料 |
| 平台 API 适配 | `aiPlat-platform/apps/eval/api/` | 平台鉴权边界、路由与 CoreFacade/服务适配 |
| 通用/历史评测逻辑 | `aiPlat-core/core/harness/evaluation/` 与 `core/apps/eval/service/` | 通用评测、RAG、G2a/G2c、judge 和既有业务操作 |
| 管理端 | `aiPlat-management/frontend/src/pages/Eval/` | `/eval` 评测中心 |

产品文档将 package 定义为产品根，平台 HTTP 层应保持薄适配。当前默认交付仍为 Central 共宿 D1c/cohost；A3 独立进程/数据库拆分尚未获授权。

### 2.3 首版声明范围

首版包括 Agent/Skill/Prompt/KB/Arena/Code Review、有限多轮 Session、人类 Preference/G2b、最小 PII/合规检查、S1 安全指标、延迟/成本等。首版明确排除或未承诺：任意第三方 HTTP/CLI 程序端到端、完整红队、live skill tools/microVM 执行、企业级全量数据驻留策略、RLHF 生产训练闭环、多区域生产拓扑。

参考：[首版范围](../../../packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md) · [产品根](../../../packages/aiplat-evaluation/docs/a3/PRODUCT_ROOT_V1.md) · [Evaluation 模块说明](../../../docs/products/five-products/modules/evaluation/MODULE.md)

## 3. 评分轴与当前成熟度

| 评分轴 | 当前仓库记录 | 评审解释 |
|---|---:|---|
| 功能覆盖 | 5/5 | 相对首版 in-scope；不等于结果准确或全对象齐备 |
| 工程架构 | 5/5 | 相对首版产品根、薄路由、契约等要求；不等于生产拆分 |
| 本地独立（不含 microVM） | 5/5 | 本地范围已收口；不等于 staging/生产授权 |
| 本地独立（含 microVM） | N/A | 仍需 Linux/KVM 主机证据 |
| 生产独立 | 未计入首版 / null | 仍需要 staging、B4-S/B5/B6 和完整 split checklist |

顶层状态仍为 `accuracy_claim=false`、`process_split_authorized=false`。本地 Docker `network=none` 不等于隔离认证；本地演练不等于 staging。

## 4. 评测对象与维度基线

| 对象 | 当前维度/观测项 | 当前方式与局限 |
|---|---|---|
| **Agent** | 默认任务完成、产出实质性、错误恢复；可使用 Agent 自定义 scoring dimensions | 默认启发式维度权重约 0.4/0.3/0.3；也可由 LLM 生成或读取自定义项。不同 Agent 的维度、阈值可能不一致，跨 Agent 总分不天然可比。 |
| **Skill** | 正向/负向 queries、目标 Skill 触发、selected skill/score、run 间变化、quality cases | 主要覆盖 trigger/路由和受控质量用例；尚未统一定义通用 precision、recall、误触发/漏触发率及执行质量基线。 |
| **Prompt** | `pass`、`exact_match`、`text_quality`、有 gold 时的 groundedness、安全、拒答、PII、延迟/成本 | package runner 与 core 旧 Prompt Eval 存在不同判分逻辑。旧路径按 expected keys 命中情况给分；报告需指明 runner/judge/version。 |
| **KB/RAG** | core RAG：faithfulness、answer relevancy、context precision/recall；package fixture：hit_count、expected IDs、token-overlap groundedness、文本质量/安全 | 前者侧重回答与上下文质量，后者主要是受控检索 fixture 检查；不能统称为一种“RAG 准确率”。 |
| **Arena/A-B** | winner、回答长度、平均 text quality、安全分 | package runner 依文本长度选 winner，是弱代理，不可作为真实质量胜负或用户偏好结论。 |
| **Code Review** | precision、recall、F1、P0 recall、TP/FP/FN、coverage、exact match、groundedness/安全 | Gold finding 匹配便于回归分析；fixture/match-only 结果不代表真实代码库端到端审查能力。 |
| **Session** | turn success rate、session pass、turn 数；每轮可附 Prompt 维度 | v0 为 2–3 轮、v1 为 5–8 轮；先前轮次作为纯文本上下文，没有工具循环；不代表长程 Agent/生产对话。 |
| **Preference** | A/B/Tie、标注覆盖率、agreement、preference κ | 衡量标注偏好和一致性，不等于事实正确或生产 RLHF 质量。 |
| **G2b** | 双标 agreement/inter-annotator κ；模型对 adjudicated gold 的 pass rate 与 CI | n=30，23/30；pass≈0.7667；Wilson 95% CI≈[0.5907, 0.8821]；κ≈0.6269。31–100 双标待完成，`accuracy_claim=false`。 |
| **PII/合规** | PII clean/leak、规则通过率 | email/phone/SSN/身份证/银行卡等启发式规则；report-only，`certified=false`，不是生产 DLP/合规认证。 |
| **S1 安全** | ASR、leak rate、false refusal rate | 有限本地攻击包；不是生产红队、安全认证或 SOC 结论。 |
| **效率** | latency p50/p95、cost per success、token、失败/超时 | 可用于固定条件下比较；本地 Ollama 数值不代表远程生产 API SLO。 |

### 4.1 指标效度与比较边界

当前 P1 composite 对质量、安全、效率按存在项重新归一化（族权重质量 0.55、安全 0.25、效率 0.20）；ASR、accuracy、PII 等部分字段为 report-only。不同 runner 的计分集合不同，因此 composite 不天然可跨对象排名。

需要在 UI/报告中降格或明确标识的弱代理包括：

- `text_quality`：主要基于空值、精确匹配、可打印字符和长度，不是充分的语义质量评测。
- Arena winner：当前由回答长度决定，不能当作有效 judge。
- token-overlap groundedness：是词项重合线索，不证明回答事实受来源支持。
- 不同 runner 的 `pass` 含义不同，可能来自 exact match、预期 ID 命中或 fixture 规则。

建议把报告方法分层为：**工程 smoke/规则、gold 对照、人工评测、经校准 judge、生产运行指标**，并明确哪些指标进入 composite。

## 5. 高级能力评测

aiPlat 其他模块有上下文管理、记忆和自学习机制，但不能由此推定 Evaluation 已经覆盖。现有 Session v0/v1 是有限轮次 fixture；另有 evaluator self-calibration 决策文档，状态为设计存档、未实现。

| 能力 | 应纳入评测的内容 | 本基线判断 |
|---|---|---|
| **上下文管理** | 关键信息保留、长上下文召回、摘要保真、冲突处理、截断降级、无关信息干扰 | 有限多轮测试不足以验证上下文压缩/长程管理。 |
| **持久记忆** | 写入精确率、Recall@k、更新/过期、删除后不再召回、用户隔离、污染抵抗 | 有记忆实现；未见 Eval Center 的完整产品级记忆 benchmark。 |
| **自学习** | 反馈前后提升、跨任务迁移、旧任务回归/遗忘、恶意/错误反馈、改动可追溯 | 有自学习路径；依赖评估器的自校准方案未实现，存在错误评估强化错误经验的风险。 |
| **模型训练/微调** | 独立留出集、分布外泛化、灾难性遗忘、安全回归、复现和回滚 | 若产品提供训练/持续学习，应建立独立训练评测及发布门禁；现有材料不足以证明闭环完整。 |

高级能力测试需包括负向用例：不得记住的内容不写入；删除后不得再检索；跨用户不得泄漏；错误反馈不得持续把策略带偏。不能只以“记得住”或“分数上升”判定成功。

参考：[Session v1](../../../packages/aiplat-evaluation/docs/a3/SESSION_V1.md) · [Evaluator calibration 决策](../../../docs/architecture/decisions/evaluator_calibration.md)

## 6. 证据链与 G2b

仓库已跟踪 `evidence_manifest.v1.json`，其中记录方法、聚合文件 SHA256、适用边界和 dual-human attestation。manifest 当前 `dual_human_attestation.status=confirmed`，记录两名不同真人、独立盲标、非脚本/AI、非同一人填写两份；`scorecard_v1_check.sh` 会校验 manifest、聚合与说明文件哈希，并在缺少证据或 attestation 时拒绝功能覆盖 5/5。

这比只填写 scorecard 数值有更强可追溯性，但哈希证明的是文件一致，不证明任务代表性或测量效度。κ/agreement 也不等于模型准确率。

**统一状态口径：**

> G2b prep 和 n=30 双标 closeout 已完成；n=100 目标的 31–100 双标尚未完成；`accuracy_claim=false`，准确率认证和外部 gate 未开放。

早期 freeze、G2c、B4S 或 Settings 中仍有“G2b defer”旧文案，需据此统一。Scorecard 已记录 n=30 指标，不应误写成 scorecard 仍显示 defer。

参考：[Evidence manifest](../../../packages/aiplat-evaluation/docs/a3/evidence/evidence_manifest.v1.json) · [证据审计](../../../packages/aiplat-evaluation/docs/a3/EVIDENCE_AUDIT_V1.md) · [门禁脚本](../../../packages/aiplat-evaluation/scripts/scorecard_v1_check.sh) · [G2b closeout](../../../packages/aiplat-evaluation/docs/a3/G2B_ACCURACY_CLOSEOUT.md)

## 7. 发布一致性与统一入口

### 7.1 发布阻断：源码与 `dist` 不一致

源码 `EvalCenter.tsx` 定义 15 个 tab；仓库当前 `dist/assets/EvalCenter-6dk0Kefu.js` 只有旧 10 个 tab，并保留 κ=null/D5 单人复核横幅。bundle 的记录时间早于源码。源码中 `/diagnostics/eval` 已移除，但 `dist` 主 bundle 仍保留旧 route 和 `DiagnosticsEvalEntry` chunk。

**发布门禁（必须满足）：**

1. 重新构建前端 `dist`，确认 15 个预期 tab 均进入产物。
2. 确认新产物不再含旧横幅和无效 `DiagnosticsEvalEntry` route/chunk。
3. 菜单只保留 `/eval`「评测中心」主入口。
4. 若兼容旧 URL，由服务端 302 或 SPA replace 到 `/eval?tab=...`，不呈现第二套 Eval 页面。
5. 在实际部署环境打开 `/eval`，核实用户实际看到的 tab、文案与跳转行为。

在第 5 项完成前，不能把源码状态当成实际用户体验，也不应把新版 UI 标记为已发布。应通过正常构建流程重生成和清理 chunk，不要只手工删除单个 bundle。

### 7.2 入口现状

源码主菜单有 `/eval`「评测中心」；Diagnostics 页面还有跳转到 `/eval` 的快捷卡片。我在当前源码中未找到独立 `/diagnostics/eval` 菜单项/路由，但旧构建产物仍包含 route/chunk。因此“两个菜单”的判断应精确表述为：**源码侧一个主菜单 + Diagnostics 快捷入口；dist 仍带旧兼容页面产物。**

### 7.3 #592 合入后的状态对照（后续执行补记）

以下状态依据 2026-11-04 提供的当前 `main` 对照补记；它更新后续执行口径，不改写本报告前述静态检查时的历史观察：

- #592 已在源码侧只保留 `/eval` 菜单入口并删除旧页面；`accuracy_claim=false` 与 `process_split_authorized=false` 未改变。
- G2b 仍为 n=30 已完成、31–100 待双标，属于人工评测工作。
- 本报告原先建议旧 URL 采用 302/SPA 兼容跳转；#592 当前选择硬切，旧路径 404。这是实现决策与原建议不同，不应描述为已经满足 90 天兼容计划。
- 后续执行计划现以硬切为准：A1 要核对正式构建产物无旧 route/chunk，并在实际部署确认旧 URL 返回 404。若后续要恢复兼容，须按执行计划变更控制重新批准。
- **本地 `dist` 重建（2026-11-04，开发机）**：`npm run build` → `EvalCenter-D4XzUbiG.js`；15 个 tab label 全进产物；无 `DiagnosticsEvalEntry` chunk；无旧「G2b 前不计算 / 仍 defer」文案；Settings 为 n=30 closeout / 31–100 待双标。**≠ 实际部署验收**——A1 仍须在目标部署确认 URL、构建 ID、CDN/缓存与旧 URL 404。
- 源码文案已收口：`EvalCenter` / `EvalSettingsPanel`；ops：`EVAL_V1_G2C_CLOSEOUT`、`B4S_PREP`。
- A2 草稿已落盘：七张对象现状卡 [`eval-object-cards/`](./eval-object-cards/)；[`G2B_100_PROTOCOL.md`](../../../packages/aiplat-evaluation/docs/a3/G2B_100_PROTOCOL.md) 待三方签认。卡片为现状盘点，**待各对象 owner 核实**后方可记 A2 pass。

## 8. API、租户与运维边界

### API/鉴权

- 平台 Eval router 挂载 `require_auth`。
- standalone store routes 使用 Bearer token，从 claims 取 `tenant_id`，列表按 tenant 过滤；跨租户读取实现为 404。
- 这些实现说明有基础鉴权/租户边界，但本报告不是全端点安全审计，不能据此宣称完成生产租户隔离认证。
- `EvalCenter.tsx` 当前将 tenant 固定为 `eval-v1`；如果页面面向多租户，需要确认 UI tenant 选择与服务端授权上下文一致。

### 数据生命周期/运维

- Evaluation 模块说明中的任务、轨迹、分数和报告 retention policy 仍为 TBD。
- D2 包含本地安全基线、协议、性能基线、升级/回滚；D3 UAT 记录为 `environment=local`。
- 默认交付仍为 D1c/cohost；生产独立服务、staging、生产 SLO/灾备均不能由本地 closeout 推定。
- 评测报告不是 FDE 客户签收；FDE 仍是签收真源。

参考：[平台 router](../../../aiPlat-platform/apps/eval/api/router.py) · [standalone store routes](../../../packages/aiplat-evaluation/app/api/store_routes.py) · [模块说明](../../../docs/products/five-products/modules/evaluation/MODULE.md) · [D2 cohost](../../../packages/aiplat-evaluation/docs/D2_COHOST.md) · [拆分清单](../../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md)

## 9. 风险排序

| 级别 | 风险 | 评审意见 |
|---|---|---|
| **发布阻断** | `dist` 落后于源码 | 新 tab/文案可能未进入实际发布；rebuild + 实际部署验收必须成为 release gate。 |
| **高** | 弱代理与评分口径分裂 | Arena、text_quality、groundedness 等可能让用户过度解读分数。 |
| **高** | 高级能力缺少评测闭环 | 上下文/记忆/自学习不能由短 Session fixture 替代；评估器自校准未实现。 |
| **高** | 准确性证据有限 | n=30 区间较宽，31–100 未双标；不能用于广泛准确率承诺。 |
| **中高** | tenant 与 retention 产品化不足 | UI 固定 tenant；数据保留策略 TBD。 |
| **中** | 状态文案漂移 | 早期 defer 状态与当前聚合并存，需统一状态源。 |
| **中** | 生产独立未完成 | cohost 仍是当前交付，staging/生产拆分未授权。 |

## 10. 建议的收口顺序

1. **先处理发布阻断**：重建前端、清旧 route/chunk，并在实际部署验证 `/eval` 15 tab 与新横幅。
2. **统一状态文案**：写清 G2b n=30 完成、31–100 待双标、accuracy claim 关闭；同步 Settings、G2c、B4S 和历史状态入口。
3. **定义对象级指标卡**：每项标注定义、判分器/version、gold 需求、执行模式、样本数、composite 角色及外推限制。
4. **修正或降级弱评分器**：Arena 改为盲评/校准 judge；启发式指标显式标为 smoke，不包装成正式质量分。
5. **收敛重复路径**：Prompt、KB 等统一 canonical runner，或在报告上强制展示评分路径和版本。
6. **补齐高级能力基准**：上下文、记忆、自学习、反馈污染、遗忘、跨用户隔离与模型更新回归。
7. **补齐产品运维契约**：动态 tenant 上下文、retention/删除策略、生产 SLO/灾备和 staging 证据。
8. **最后推进生产拆分**：满足 A3 split checklist 的现场演练与审批前，不翻 `process_split_authorized`。

## 11. 后续复评对照表

每次复评时更新“本次值/证据链接/变化说明”，不要覆盖本次基线值。

| 对照项 | 2026-11-04 基线 | 下次复评需记录 |
|---|---|---|
| 源码 Eval tab 数 | 15 | 数量及具体 tab |
| 构建产物 Eval tab 数 | 基线 10（旧）；**2026-11-04 本地重建** → 15（`EvalCenter-D4XzUbiG.js`） | 部署环境 bundle 名/hash |
| 实际部署 `/eval` | 仍未签认 | URL/build ID、tab 数、横幅、截图或验收记录 |
| `/diagnostics/eval` | 源码已删；本地新 dist 无旧 chunk | 部署侧旧 URL **404** 证据 |
| Feature/Architecture/Local score | 5/5、5/5、5/5（限定首版范围） | scope 版本、score、证据审计结果 |
| G2b | n=30、23/30、76.67%、95% CI [0.5907,0.8821]、κ=0.6269 | n、pass/fail、CI、争议仲裁、双人证明、数据切片 |
| G2b target | n=100；31–100 待双标 | 完成样本与未完成样本数 |
| Preference | n=32、agreement=0.75、κ≈0.47 | 方法版本、双人样本和聚合 |
| Evidence manifest | tracked；dual-human confirmed | manifest hash、聚合 hash、attestation 状态 |
| Accuracy claim | false | 是否仍 false；若变更，引用审批及完整证据 |
| Process split | false；默认 cohost | checklist、staging drill、审批记录 |
| 高级能力评测 | 无完整 Eval benchmark | context/memory/self-learning/training 的独立结果 |
| Tenant/retention | UI tenant 固定 `eval-v1`；retention TBD | 动态 tenant 验收、删除/保留策略和审计 |

## 12. 参考材料

- [Evaluation README](../../../packages/aiplat-evaluation/README.md)
- [SCORE_SCOPE_V1](../../../packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md)
- [SCORECARD_V1](../../../packages/aiplat-evaluation/docs/a3/SCORECARD_V1.md)
- [G2b accuracy closeout](../../../packages/aiplat-evaluation/docs/a3/G2B_ACCURACY_CLOSEOUT.md)
- [Evidence audit](../../../packages/aiplat-evaluation/docs/a3/EVIDENCE_AUDIT_V1.md)
- [A3 split checklist](../../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md)
- [E6 UI closeout](./EVAL_V1_E6_CLOSEOUT.md)
- [E7 D2/D3 closeout](./EVAL_V1_E7_CLOSEOUT.md)
- [Evaluator self-calibration decision](../../../docs/architecture/decisions/evaluator_calibration.md)

