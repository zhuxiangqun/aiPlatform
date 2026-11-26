---
title: "aiPlat 产品能力白皮书"
volume_id: product-capability
type: whitepaper-volume
doc_type: Report
status: generated
generated_at: "2026-11-26T15:17:07Z"
audience: "产品负责人、技术评估者、客户技术链"
core_question: "能解决什么问题？能力边界在哪？"
priority: P1
source_status: ready
suite: docs/reference/explanatory/whitepaper-suite.yaml
suite_sha256: "1641cccf71efaa130f3b0370ae0c988e50303e56d5e830b273e9915cd8613a2e"
caps_sha256: "12f38247020c41794e637bb7c8fcd06600cdbafb2ae9b81620836ba2b5049794"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=product-capability suite_sha256=1641cccf71efaa130f3b0370ae0c988e50303e56d5e830b273e9915cd8613a2e caps_sha256=12f38247020c41794e637bb7c8fcd06600cdbafb2ae9b81620836ba2b5049794 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 产品能力白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI
> 体系：[`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md) · 清单：[`../../../docs/reference/explanatory/whitepaper-suite.yaml`](../../../docs/reference/explanatory/whitepaper-suite.yaml)
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `product-capability` |
| 受众 | 产品负责人、技术评估者、客户技术链 |
| 核心问题 | 能解决什么问题？能力边界在哪？ |
| 优先级 | P1 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-11-26T15:17:07Z` |
| CAPABILITIES sha256 | `12f38247020c…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

## 1. 本卷论证目标

本卷面向 **产品负责人、技术评估者、客户技术链**，围绕「**能解决什么问题？能力边界在哪？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) | 唯一能力清单 | ✅ |
| [`reports/whitepapers/aiplat-platform-status-whitepaper.md`](../../../reports/whitepapers/aiplat-platform-status-whitepaper.md) | 可读包装（含完整能力表） | ✅ |
| [`docs/reference/matrix/capability-impact-matrix.md`](../../../docs/reference/matrix/capability-impact-matrix.md) | 变更影响 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/guides/getting-started.md`](../../../docs/guides/getting-started.md) | 上手路径 | ✅ |
| [`docs/guides/fde/README.md`](../../../docs/guides/fde/README.md) | FDE 交付场景入口 | ✅ |
| [`docs/guides/fde/templates/template-signoff.md`](../../../docs/guides/fde/templates/template-signoff.md) | ORG / 现场签收模板 | ✅ |
| [`docs/guides/management.md`](../../../docs/guides/management.md) | Workbench / 管理端操作 | ✅ |
| [`docs/guides/knowledge/knowledge-system.md`](../../../docs/guides/knowledge/knowledge-system.md) | 知识 / 本体 / RAG 手册 | ✅ |
| [`packages/aiplat-evaluation/README.md`](../../../packages/aiplat-evaluation/README.md) | 评测治理入口 | ✅ |
| [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md) | 执行选型（产品/技术评估共用） | ✅ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | 厂外薄交付边界（Pi） | ✅ |
| [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | Pi Package 用户侧说明 | ✅ |
| [`docs/reference/security/security-architecture.md`](../../../docs/reference/security/security-architecture.md) | 治理下执行（产品嵌入视图） | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 典型产品场景（索引 + 正文）

本卷用**场景切片**回答「能解决什么问题」：索引表指路 + 权威源节选。节选随权威源再生；**禁止**在卷内手写第二份能力清单或编造客户 ROI。接线以 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) 为准。

#### 3.0.0 场景索引

| 场景 | 客户要解决的问题 | 权威源（优先） | 正文节 |
|------|------------------|----------------|--------|
| **FDE 交付** | 把业务问题做成可签收的 AI 交付 | [`docs/guides/fde/README.md`](../../../docs/guides/fde/README.md) · CAPABILITIES「平台治理 / FDE」 | §3.0.1 |
| **App 工厂 / Builder** | 从需求到 Agent/应用产物 | 管理端 Builder · [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | §3.0.2 |
| **Workbench** | 开发与调试工作台 | [`docs/guides/management.md`](../../../docs/guides/management.md) · CAPABILITIES「Workbench」 | §3.0.3 |
| **评测治理** | 评测流程与治理规则 | [`packages/aiplat-evaluation/README.md`](../../../packages/aiplat-evaluation/README.md) · CAPABILITIES「评测 / Governance」 | §3.0.4 |
| **ORG 签收** | 组织级签收与现场闭环 | [`docs/guides/fde/templates/template-signoff.md`](../../../docs/guides/fde/templates/template-signoff.md) · CAPABILITIES「apps/org」 | §3.0.5 |
| **渠道接入** | 多渠道消息与集成 | CAPABILITIES「Channel」· 分卷 04 | §3.0.6 |
| **知识 / 本体 / RAG** | 企业知识可检索、可治理 | [`docs/guides/knowledge/knowledge-system.md`](../../../docs/guides/knowledge/knowledge-system.md) · CAPABILITIES「知识引擎 / RAG」 | §3.0.7 |
| **Agent / Skill 运行** | 多步工具调用与技能执行 | [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md) · CAPABILITIES「Agent / Skill」 | §3.0.8 |
| **治理下执行** | 权限、审批、审计可证明 | [`docs/reference/security/security-architecture.md`](../../../docs/reference/security/security-architecture.md) · 分卷 05 · CAPABILITIES「Gate」 | §3.0.9 |
| **薄交付（Pi）** | 用户侧轻量跑快照、不装全栈 | [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) · [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | §3.0.10 |

> 索引指路；各 §3.0.x 为权威源节选（可再生）。[`docs/guides/README.md`](../../../docs/guides/README.md) 仅提供操作说明，不作为行为契约。

#### 3.0.1 FDE 交付

**尽调问题**：现场如何把业务问题做成可签收的 AI 交付？

操作细节见 `docs/guides/fde/` 分册；接线以 CAPABILITIES「FDE」为准。

**权威源**： [`docs/guides/fde/README.md`](../../../docs/guides/fde/README.md)

**节选自** [`docs/guides/fde/README.md`](../../../docs/guides/fde/README.md)：

### FDE 现场交付体系 — 文档导航

**FDE**（Field Deployment Engineer）是 aiPlat 的核心用户角色——负责到客户现场完成 AI 系统交付。

#### 文档角色（Batch C2）

| 文档 | 角色 | 不是 |
|---|---|---|
| `01`、`02`、`03`、`04` | 任务指南 / 操作手册 | 方法论全文 |
| `05` | 交付方法论 | 日常操作步骤 |
| `06` | 标准交付 SOP | 架构设计 |
| `templates/fde-delivery-manual.md` | 交付手册模板 | 方法论正文 |
| `docs/contracts/FDE_WORKBENCH_CONTRACT.md` | 工作台规范契约 | 操作教程 |

##### 你是谁？选文档

| 我是… | 看这篇 | 5分钟能上手 |
|------|------|:---:|
| **第一天加入，完全不知道怎么用** | [01 - 快速入门](../../../docs/guides/fde/01-fde-quickstart.md) | ✅ |
| **我要从零交付一个全新客户域** | [06 - 标准交付 SOP](../../../docs/guides/fde/06-sop-domain-delivery.md) | ✅ |
| **日常交付客户项目** | [02 - 交付操作手册](../../../docs/guides/fde/02-fde-delivery.md) | ✅ |
| **需要理解完整交付方法论** | [05 - 实施流程](../../../docs/guides/fde/05-fde-implementation-process.md) | — |
| **已交付项目需要维护监控** | [03 - 运维与自演进](../../../docs/guides/fde/03-fde-operations.md) | ✅ |
| **我要扩展系统（创建Agent/Workflow）** | [04 - 管理与扩展](../../../docs/guides/fde/04-fde-admin.md) | — |
| **建域 / 工厂 apply / 应用库 Agent** | [创建本体+Agent 合册](../../../docs/contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) | ✅ |
| **it-ops 组织试点与签收准备（八闸门）** | [ORG_L5_RUNBOOK](../../../docs/contracts/ORG_L5_RUNBOOK.md) · [ORG_M4_SIGNOFF_PACK](../../../docs/contracts/ORG_M4_SIGNOFF_PACK.md) · 管理端 `/org/pilot` | ✅ |

> **勿混淆**：本目录「⑦ 验收移交 / 客户签收」指 **FDE 项目交付签收单**；it-ops **Org M4 签收准备**（材料齐可送审，程序不打开 `m4_claim`）在仪表盘 **组织试点**，不在 FDE 工作台九步主流程里完成。

##### FDE 工作台工具箱（v28.0 新增）

工具栏包含 10+ 跨阶段工具，按用途分三组：

| 组 | 工具 | 用途 |
|:--|------|------|
| **治理层** | 沙盒推演 / 决策血缘 / 本体分支 / 蜂群推演 | Agent推演 / 决策追溯 / 本体分支管理 / 原子拆分执行 |
| **协作层** | Agent网络 | 蜂群自组织网络可视化 + 伙伴选择 |
| **执行层** | 模板 / 录制 / 编译 | 文档模板渲染 / 操作录制→Skill生成 / OKF导出+ROI |

> 工具栏收纳策略：沙盒推演/决策血缘/蜂群推演始终可见，其余通过「更多▼」展开。

##### FDE 九步交付流程

```
① 业务认知  →  ② 评估域  →  ③ 问题重构  →  ④ 验证价值  →  ⑤ 快速构建
    选客户         选域           诊断           POC演示        打包部署

⑥ 评测护栏  →  ⑦ 验收移交  →  ⑧ 运营监控  →  ⑨ 快速认知
   灰度测试        客户签收        持续运维        48h行业认知
```

##### 阅读路线图

```
新人入职          日常交付           交付后            系统扩展
    │                │                 │                  │
    ▼                ▼                 ▼                  ▼
┌──────────┐   ┌──────────┐    ┌──────────┐       ┌──────────┐
│ 快速入门  │→  │ 交付操作  │ →  │ 运维自演进 │       │ 管理与扩展 │
│ (5分钟)  │   │ (核心手册) │    │ (持续维护) │       │ (Agent等) │
└──────────┘   └──────────┘    └──────────┘       └──────────┘
```

以上 4 篇是**操作流程**，按角色从入门到日常交付到运维到扩展。

[05 - 实施流程](../../../docs/guides/fde/05-fde-implementation-process.md) 是**方法论参考**——角色定义、输入输出契约、验收标准、质量门。适合 PM 和 FDE 负责人制定交付计划时查阅，不是操作手册。
```

##### 系统访问

| 服务 | 地址 |
|------|------|
| FDE 工作台（前端） | `http://localhost:5173/diagnostics/fde` → FDE Dashboard |
| 平台 API | `http://localhost:8003/api/platform/apps/fde/` |
| Core API | `http://localhost:8002/api/core/` |

##### 相关文档

- [交付手册模板](../../../docs/guides/fde/templates/fde-delivery-manual.md) — 交付后自动生成的客户验收文档
- [输入输出文档模板](../../../docs/guides/fde/templates) — 10 个标准文档模板（客户档案/诊断报告/签收单等）
- [标书审查实例](../../../docs/guides/fde/examples/bid-review/delivery-manual.md) — 投标场景实操参考
- [知识系统完整指南](../../../docs/guides/knowledge/knowledge-system.md) — 知识库反馈闭环
- [知识系统完整指南](../../../docs/guides/knowledge/knowledge-system.md) — 域本体与 FDE 集成


#### 3.0.2 App 工厂 / Builder

**尽调问题**：工厂产物与厂外交付边界如何划清？

Builder UI 以管理端为准；本卷只节选厂外薄交付边界，避免与 §3.0.10 重复粘贴 Package README。

**权威源**： [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) · 管理端 Builder（运行时入口）

**节选自** [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md)：

### Plan: aiPlat × Pi 薄 Runtime（1C + 2C）

> Living 摘要 · 2026-10-12 · 包：`packages/aiplat-pi-runtime/`
> **状态**：Phase 0–2 + 工厂/FE/ZIP **已合并 main**（PR [#251](https://github.com/zhuxiangqun/aiPlatform/pull/251)）
> **Live 门**：✅ `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh`（Ollama `ollama/qwen2.5:3b` — CLI print + SOP + `/aiplat-status` + HTTP `createAgentSession`）

#### 术语：「Hybrid」消歧

| 语境 | 含义 | 权威入口 |
|------|------|----------|
| **Pi ↔ aiPlat 企业回连** | `AIPLAT_ENTERPRISE=1` 等可选厚能力（KB/工具/Memory/审批） | `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md` |
| **Skill 执行类型** | `execution_type` 等技能实现模式（与企业回连无关） | 各 `SKILL.md` / 引擎 Skill 规约 |
| **Builder / 工厂模式** | 应用工厂产物或流水线形态中的 “hybrid” 措辞 | Builder / 工厂相关 docs（勿与上表第一行混用） |

本文其余「混合 / Hybrid」若未特别说明，均指 **第一行：Pi↔aiPlat 企业回连**。

#### 战略：两条轴，勿合成一条

Pi 是极简 Agent Harness（非治理平台）。与 aiPlat 的关系拆成**两条产品轴**，禁止写成「一个 Pi 集成路径解决所有问题」。

| 轴 | 定位 | 状态 | 解决什么 | 不解决什么 |
|----|------|------|----------|------------|
| **（B）厂外** | 用户侧薄交付宿主：导出包 → `pi -e` / 薄 HTTP | **既定主路径**（已落地） | 不装全栈也能跑快照（SOP + skills + handler） | 平台级厚度（Memory / SECI / PolicyGate / 知识 syscall） |
| **（A）厂内** | 可选编码执行核：CLI/RPC 包在 PolicyGate 外 | **⓪ 合并关闭**（2026-10-14 `blank_not_proven`）：Workspace Execute Pi 旁路已拆；离线 CLI/探针归档；CAPABILITIES **不**标「厂内已接线」 | （历史宣称）编码闭环副作用 | 替代编排治理；默认换掉 ReActLoop |

##### 分层，而非两套平行产品（2026-10-13 锁定）

> **能力重叠 ≠ 交付重复。** aiPlat 白皮书里已有 Agent 循环、工具、多模型——那是**平台能力清单**。
> Pi 默认交付解决的是另一件事：**工厂产出物如何在用户侧轻量跑起来**（不装 core/platform/infra 全栈）。

| 说法 | 是否采纳 |
|------|:--------:|
| 执行面（Pi）与治理面（aiPlat）**分层** | ✅ |
| 用户对外装「两个平权平台」、两套权限/审计 | ❌ |
| 企业场景入口仍是 aiPlat（或 Pi 壳回连 aiPlat）；Pi 对用户透明为「更轻的跑法」 | ✅ |
| 用 Pi 替代 aiPlat 编排/门禁/多租户 | ❌ |

```text
aiPlat（控制面 / 工厂 / 治理）
    │ 导出快照（AGENT.md / skills / handler）
    ▼
Pi（执行面 / 厂外薄宿主）── 默认 Pi-only 可闭环
    │ 可选 AIPLAT_ENTERPRISE=1
    └── 回连 aiPlat API（KB / 工具 / 原生门禁 / Memory / 审批等待；PolicyGate 留在服务端）
```

**产品决策（已锁定 · 2026-10-12；措辞澄清 · 2026-10-13）**

> **默认：只靠 Pi 就能跑产出物。**
> **企业级：Pi + aiPlat（混合）——Pi 仍是用户侧宿主，厚能力经 aiPlat 托管 API / 门禁回连。**
> **不以「用户侧单独部署厚 aiPlat 运行时」为默认交付形态。**
> **不以「Pi 与 aiPlat 两套平行产品」对外叙事。**

| 模式 | 用户侧 | 能力 | 状态 |
|------|--------|------|------|
| **Pi-only** | 导出包 + `pi` / 薄 HTTP + 自备模型 | SOP + skills + handler（确定性桥） | **默认交付 · 已落地** |
| **Pi + aiPlat** | 同上 Pi 壳 + `AIPLAT_ENTERPRISE=1` 回连 | + 只读 KB + 允许列表工具代理 + **原生工具门禁** + **Memory capture** + **审批等待**（`AIPLAT_ENTERPRISE_APPROVAL=1` → status/pending/wait；裁决在平台 UI） | **混合阶梯 1–5 · 已接线** |
| ~~厚运行时~~ | 用户侧直接跑裁剪 aiPlat | 接近平台 Agent | **非默认**；仅特殊驻场/私有化例外 |

**Pi-only 必须能完成的闭环（验收）**

- 加载导出包（manifest / AGENT.md / skills）
- 对话 + SOP 注入
- `/skill-*` 与 `handler.py` 确定性执行
- 自备 LLM（Ollama / 云厂商均可）
- **不依赖** 8002/8003 进程

**Pi + aiPlat 才提供的企业能力（混合回连，不搬进 Pi 进程）**

- PolicyGate / RBAC / 审批
- Memory / SECI / 经验回写
- 平台知识检索（`sys_kb_retrieve` 等）
- 运行时审计 / 可观测回写
- 租户配额与成本治理

混合形态示意（KB + 工具 + 原生门禁 + Memory + 审批等待已落地）：

```text
用户 ──► Pi（对话壳 + 本地 skills/handler）
              │
              ├── 本地可完成 → 不回连（默认 Pi-only）
              └── AIPLAT_ENTERPRISE=1
                    ├── enterprise_tool_gate：block bash/write/edit（默认）
                    ├── POST /platform/kb/query          （只读 KB）
                    ├── AIPLAT_ENTERPRISE_TOOLS=… → POST …/tools/{name}/execute
                    ├── AIPLAT_ENTERPRISE_MEMORY=1 → POST /platform/memory/capture
                    └── AIPLAT_ENTERPRISE_APPROVAL=1 → GET /platform/approvals…
                          （wait/status only；approve/reject 在平台 UI）
```

接线入口：`enterprise_kb.ts` / `enterprise_tools.ts` / `enterprise_tool_gate.ts` / `enterprise_memory.ts` / `enterprise_approval.ts`（由 `aiplat-app.ts` 条件注册）。详见 `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`。

##### 双模式内涵（精确化 · 2026-10-13）

> **合理方向 = 控制面 / 执行面分层**，不是「两套平权平台」。企业级 ≠ 单一功能，而是可观测、可治理、可审计的平台工程；Pi 不承担该体系。

| 模式 | 内涵 | 能力边界 | 不安全假设 |
|------|------|----------|------------|
| **模式一 · 仅 Pi** | 独立、可自托管的极简 Agent Harness | `read`/`write`/`edit`/`bash`、会话内循环、多模型抽象；适合个人 / 小团队 / 快速验证 | **无**内置权限、队列、成本、审计 → **禁止**默认无人值守生产 |
| **模式二 · Pi + aiPlat** | Pi = 执行内核；aiPlat = 平台层包裹 | 权限 / 策略 / 审计 / 成本 / 生命周期 / 多租户在 **aiPlat**；副作用经回连或外层 PolicyGate | 禁止叙事成「再装一套平行平台」；禁止把 Memory/SECI/ApprovalGate 搬进 Pi 进程 |

**厂内集成形态（轴 A，与厂外交付正交；已 ⓪ 合并关闭）**：

| 形态 | 原理 | 现状 |
|------|------|------|
| RPC 子进程 | aiPlat 启 Pi 为外部进程，JSONL 通信 | 离线 CLI / `pi_rpc_client` **归档**（不经 Workspace Execute） |
| SDK 嵌入 | 同进程调 Pi API | **非默认**（强 Node 绑定） |
| 可选执行后端 | 曾拟 `AIPLAT_PI_CODING_EXECUTOR` 旁路 | **已拆除**；flag 无生产效果 |

接 Pi **不是为了补上下文**：aiPlat 已有 Memory / CRAG / Cont

…

_(节选；全文见权威源)_


#### 3.0.3 Workbench

**尽调问题**：开发与调试工作台从哪里上手？

CAPABILITIES「Workbench」为接线真相；手册只描述操作路径。

**权威源**： [`docs/guides/management.md`](../../../docs/guides/management.md)

**节选自** [`docs/guides/management.md`](../../../docs/guides/management.md)：

### aiPlat 管理画面 操作手册

> 版本 **2.4** | 最后更新 **2026-09-20** | 适用于 aiPlat 管理端现状（以 `pageManifest` 为准）
> **v2.4 更新（2026-09-20）**: 侧边栏以 `pageManifest` 为准——仪表盘含**组织试点** `/org/pilot`；知识为**业务本体 | 知识库**双轨；应用工厂与 FDE 工作台边界写清（写活本体 / 签收准备不在应用工厂完成）。旧「知识工厂九入口」描述已废弃。
>
> **v2.3 更新**: 侧边栏 v2.3 重构 — 6 组 92 入口；AI应用工厂精简58%(33→14项)；引擎能力配置独立成组移入平台设置；价值看板→仪表盘；诊断与治理全 per-project | 2026-08-12

本文档详细说明 aiPlat 管理画面（Management Dashboard）的所有功能模块、操作方法和典型工作流。

---

#### 目录

- [1. 系统概述](#1-系统概述)
- [2. 五大角色与权限体系](#2-五大角色与权限体系)
- [3. 侧边栏导航](#3-侧边栏导航)
- [4. 系统入口页面](#4-系统入口页面)（含 [组织试点](#41b-组织试点orgpilot)）
- [5. 平台设置](#5-平台设置)
- [6. AI 应用工厂 — 能力组装](#6-ai-应用工厂--能力组装)
- [7. 能力市场](#7-能力市场)
- [8. 平台配置](#8-平台设置--平台配置)
- [9. AI 应用工厂 — 应用生命周期](#9-ai-应用工厂--应用生命周期)
- [10. 价值看板](#10-仪表盘--价值看板)
- [11. 诊断与治理](#11-诊断与治理)
- [12. 知识（双轨）](#12-知识双轨业务本体--知识库)
- [13. 审批管理](#13-诊断与治理--审批管理)
- [14. 典型操作流程](#14-典型操作流程)
- [附录 A：支持模型类型](#附录-a支持模型类型)
- [附录 B：常见问题](#附录-b常见问题)
---

#### 1. 系统概述

aiPlat 管理画面是一个四层架构的 AI 中台管理界面，覆盖基础设施、AI 引擎、平台服务和应用接入全栈管理。首页为**系统概览**仪表盘，左侧侧边栏按任务流分组（7 组）。右下角提供**角色切换器**用于不同身份视角切换。

**访问地址**：`http://localhost:5173`（开发模式）

---

#### 2. 角色与权限体系（8 类角色）

##### 2.1 角色定义

| # | 角色 Key | 中文名 | 职责范围 | 侧边栏可见组 |
|---|---------|-------|---------|------------|
| 1 | `admin` | 管理员 | 全局配置、安全审计、系统运维 | 全部菜单组 + 独立菜单项 |
| 2 | `developer` | 开发者 | 模型、Agent、Skill、诊断 | infra, core, workspace, app, value, user, diagnostics |
| 3 | `business` | 业务负责人 | KPI、目标、价值看板 | value, user |
| 4 | `user` | 终端用户 | 提交任务、查看结果 | user, app |
| 5 | `approver` | 审批人 | 审批待办事项 | user |
| 6 | `operator` | 运维 | 平台运维/监控 | 见 `AppLayout.tsx` |
| 7 | `fde` | FDE | FDE 交付/知识 | 见 `AppLayout.tsx` |
| 8 | `viewer` | 只读 | 查看 | 见 `AppLayout.tsx` |

> 上表为常用角色说明；完整角色与可见菜单以 `aiPlat-platform/auth/rbac.py` + `AppLayout.tsx` 为准。

##### 2.2 角色切换

侧边栏底部的角色切换器允许你切换身份以验证不同角色的界面效果：

1. 点击底部当前角色名称
2. 弹出下拉菜单显示角色切换项（实际角色集合见 `rbac.py`）
3. 选择目标角色 → 页面自动刷新

> 开发环境使用 `localStorage` 模拟。生产环境从 JWT Token 解析角色，不可手动切换。

##### 2.3 后端权限矩阵

以下路由级别权限在后端通过 `PolicyGate.check_route_access()` 强制校验：

| 路由前缀 | 允许角色 |
|---------|---------|
| `/system-overview` | admin |
| `/onboarding` | admin |
| `/platform` | admin |
| `/value-center/roles` | admin |
| `/value-center` | admin, business |
| `/value-center/kpis` | admin, business |
| `/value-center/goals` | admin, business |
| `/value-center/strategy` | admin, developer |
| `/value-center/training` | admin, developer |
| `/diagnostics` | admin, developer |
| `/infra` | admin, developer |
| `/core` | admin, developer |
| `/workspace` | admin, developer |
| `/workbench` | admin, developer, business, user |
| `/value-center/spec` | admin, developer, business, approver |
| `/app` | admin, user |
| `/approval-center` | admin, approver |

---

#### 3. 侧边栏导航

侧边栏按任务流分为 7 个分组，每组包含若干菜单项。分组内用子区域标题分段，左侧图标 + 文字标签，点击进入对应页面。支持展开/折叠 + URL 自动匹配展开。

##### 3.1 菜单分组总览

| 分组 | 标签 | 主要角色 | 菜单数 | 说明 |
|------|------|---------|:---:|------|
| dashboard | **📊 仪表盘** | 全部 | 含组织试点 | 系统概览、**组织试点**、告警、图谱、治理、价值看板 |
| knowledge | **🧠 知识** | admin, developer, fde | 2 | **业务本体**（权威轨）+ **知识库**（检索轨） |
| build | **🤖 AI 应用工厂** | admin, developer, fde | — | 应用工厂 / 已部署应用 / FDE 工作台 + 工作区能力 |
| diagnostics | **🩺 诊断与治理** | 全部 | 10 | 概览与监控(4项) + 排查与追踪(4项) + 项目维护(2项)；全 per-project 范围 |
| eval | **🧪 评测** | admin, developer, fde | — | 评测入口；菜单定义见 `pageManifest.ts` |
| platform | **⚙️ 平台设置** | admin, operator | 54 | 监控与运维(15项) + 能力配置(6项) + 接入配置(5项) + 系统维护(8项) + 安全与合规(8项) + 高级工具(12项) |
| help | **📖 帮助** | 全部 | 1 | 文档系统 |

##### 3.2 各分组详细菜单

###### 📊 仪表盘

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Activity | 系统概览 | `/system-overview` | 全局健康仪表盘 |
| Users | **组织试点** | `/org/pilot` | it-ops 开跑 / 八闸门签收准备 / 证据包（≠ 已签收） |
| Bell | 告警中心 | `/alerts` | 系统告警管理 |
| Share2 | 系统图谱 | `/system-graph` | 架构可视化 |
| Shield | 治理仪表盘 | `/governance` | 8 项治理机制健康状态 |
| BarChart3 | 价值看板 | `/value-center` | 业务价值量化分析 |

> 组织试点操作：[`../contracts/ORG_L5_RUNBOOK.md`](../../../docs/contracts/ORG_L5_RUNBOOK.md) · [`../contracts/ORG_M4_SIGNOFF_PACK.md`](../../../docs/contracts/ORG_M4_SIGNOFF_PACK.md)。

###### 🧠 知识（双轨）

| 图标 | 名称 | 路由 | 说明 |
|------|------|------|------|
| Box | **业务本体** | `/knowledge/business` | 域管理 / 编辑器 / **工厂流水线（提案 apply）** |
| Database | **知识库** | `/knowledge/library` | Vault / 向量 / Wiki（检索轨，不替代拍板） |

> 业务本体详细步骤：[`../knowledge-system.md`](../../../docs/guides/knowledge/knowledge-system.md) 附录 C · [`../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md`](../../../docs/contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md)。
> 旧菜单「本体编辑器 `/ontology-editor`」「本体模型 `/infra/ontology`」已收敛到业务本体，勿再当主入口写进 SOP。

###### 🤖 AI 应用工厂

**📦 应用生命周期**：
| 图

…

_(节选；全文见权威源)_


#### 3.0.4 评测治理

**尽调问题**：评测服务如何本地/共置运行，证据与准确率声明边界是什么？

准确率/authorize 声明以评测包文档与 CAPABILITIES「评测」为准，禁止卷内另编通过率。

**权威源**： [`packages/aiplat-evaluation/README.md`](../../../packages/aiplat-evaluation/README.md)

**节选自** [`packages/aiplat-evaluation/README.md`](../../../packages/aiplat-evaluation/README.md)：

### aiplat-evaluation

Evaluation Service **D1 Thin (D1c/cohost)** · **D2 ops pack** · A3 Accepted（有条件）· **A1–A5 local standalone (closeout)**.

#### Modes

| Mode | How | Notes |
|---|---|---|
| **cohost (default production)** | Central `GET /api/core/eval/healthz` | `deploy_unit=central` |
| **standalone (A1–A6 / B1–B3-L)** | `bash scripts/run_local.sh` → `:8010` | store OK; allowlist enqueue **202**; sandbox/forbidden **422**; **`process_split_authorized=false`**; `environment=local` |
| **B2-L worker** | `bash scripts/run_worker.sh` | poll `process_once` until idle/signal; same DB URL |
| **B3-L local_stub** | `AIPLAT_EVAL_SANDBOX_BACKEND=local_stub` | admits `http_probe` stub only; **no** network/container; see [`docs/a3/B3L_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/B3L_LOCAL.md) |
| **B3-L.3 docker cli** | `AIPLAT_EVAL_SANDBOX_BACKEND=docker` | admits `cli_probe` via allowlisted `docker run --network=none`; not microVM |
| **B3-L.2 dual-read** | `bash scripts/b3l_dual_read_drill.sh` | local fixture ETL + reconcile + pointer rollback; **not** production backfill |
| **Optional LLM** | `AIPLAT_EVAL_LLM=stub\|http` + BASE_URL | `prompt_eval` without Central; see [`docs/a3/LLM_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/LLM_LOCAL.md) |
| **LLM dynamic gate** | `bash scripts/b2l_llm_dynamic_gate.sh` | stub Worker e2e; optional live via `AIPLAT_EVAL_LLM_LIVE=1` |
| **Live LLM 10-task smoke** | `bash scripts/live_llm_smoke.sh` | stub baseline + optional live×3; see `docs/a3/LIVE_LLM_SMOKE.md` |
| **S1 security fixture** | `bash scripts/s1_local_gate.sh` | SECURITY_EVAL_V1 fixture ASR gate; **not** accuracy; see [`docs/a3/S1_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/S1_LOCAL.md) |
| **P1 scoring semantics** | `bash scripts/p1_local_gate.sh` | families + engineering composite (text/safety scored; asr report-only); `accuracy_claim=false`; see [`docs/a3/P1_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/P1_LOCAL.md) |
| **Local track closeout** | `bash scripts/local_track_closeout.sh` | P1+S1 gates + authorize locked; not B4/staging |
| **B4-S prep (blocked)** | [`docs/a3/B4S_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/B4S_PREP.md) | host prerequisites only; no authorize |
| **Scorecard evidence audit** | [`docs/a3/EVIDENCE_AUDIT_V1.md`](../../../packages/aiplat-evaluation/docs/a3/EVIDENCE_AUDIT_V1.md) + `scripts/scorecard_v1_check.sh` | manifest SHA256 + dual-human attestation; refuse silent feature 5 |
| **microVM prep (blocked)** | [`docs/a3/MICROVM_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/MICROVM_PREP.md) + `scripts/microvm_local_prep_gate.sh` | probe + refuse live tools; no real isolation |
| **microVM Linux track** | [`docs/a3/MICROVM_LINUX_TRACK.md`](../../../packages/aiplat-evaluation/docs/a3/MICROVM_LINUX_TRACK.md) + `scripts/microvm_linux_track_gate.sh` | KVM host admit + host allowlist CLI; Darwin ineligible |
| **microVM guest_boot authorize** | [`docs/a3/MICROVM_GUEST_BOOT.md`](../../../packages/aiplat-evaluation/docs/a3/MICROVM_GUEST_BOOT.md) + `scripts/microvm_guest_boot_gate.sh` | GUEST_BOOT+KERNEL/ROOTFS+InstanceStart; ≠ process_split; Darwin ineligible |
| **microVM Linux track v1** | [`docs/a3/MICROVM_LINUX_TRACK.md`](../../../packages/aiplat-evaluation/docs/a3/MICROVM_LINUX_TRACK.md) + `scripts/microvm_linux_track_gate.sh` | KVM host admit + host allowlist CLI; guest_boot deferred; Darwin ineligible |
| **Prod live 25×3** | [`docs/a3/PROD_LIVE.md`](../../../packages/aiplat-evaluation/docs/a3/PROD_LIVE.md) + `scripts/prod_live_baseline.sh` | candidate model latency/cost; accuracy_claim=false |
| **G2b accuracy closeout** | [`docs/a3/G2B_ACCURACY_CLOSEOUT.md`](../../../packages/aiplat-evaluation/docs/a3/G2B_ACCURACY_CLOSEOUT.md) + `scripts/g2b_accuracy_closeout_gate.sh` | adjudicated gold + pass-rate/CI; accuracy_claim=false until attestation |
| **Local chaos / backup-restore** | [`docs/a3/LOCAL_CHAOS.md`](../../../packages/aiplat-evaluation/docs/a3/LOCAL_CHAOS.md) + `scripts/local_chaos_drill.sh` | SQLite crash/wipe/partial + optional B4-S PG kill; ≠ staging/authorize |

| **B1/B2 contract converge** | `bash scripts/b12_contract_gate.sh` | error body + dual-point + temporary_proxy=0; see [`docs/a3/CONTRACT_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/CONTRACT_LOCAL.md) |
| **P1 canonical honesty** | `bash scripts/p1_canonical_gate.sh` | package scored vs Central legacy_7dim report-only; see [`docs/a3/P1_CANONICAL.md`](../../../packages/aiplat-evaluation/docs/a3/P1_CANONICAL.md) |
| **Job wall-clock** | `AIPLAT_EVAL_JOB_TIMEOUT_SEC` (default 300) | exceed → `timed_out` (never succeeded) |
| **Job cancel** | `POST /api/platform/apps/eval/jobs/{id}/cancel` | queued\|running → `cancelled` |
| **Job cost cap** | `AIPLAT_EVAL_JOB_COST_CAP` / payload `cost_cap` | exceed → `timed_out` (`cost_cap_exceeded`) |
| **B1-L Compose + PG store** | `compose/docker-compose.b1l.yml` + `AIPLAT_EVAL_DB_URL=postgresql://…` | PG16 + MinIO; EvalStore via asyncpg; SQLite still default if unset |
| **Central proxy (optional)** | `AIPLAT_EVAL_SERVICE_URL=http://127.0.0.1:8010` | Central authenticates then forwards store subset |

#### A5 closeout

```bash
bash packages/aiplat-evaluation/scripts/a5_local_closeout.sh
### backup / rollback / contracts / A4–A5 tests → docs/a3/drills/local-eval-a3-a5-closeout-*.json
```

See [`docs/a3/A_LOCAL_CLOSEOUT.md`](../../../packages/aiplat-evaluation/docs/a3/A_LOCAL_CLOSEOUT.md).

#### B2-L closeout

```bash
bash packages/aiplat-evaluation/scripts/b2

…

_(节选；全文见权威源)_


#### 3.0.5 ORG 签收

**尽调问题**：组织级签收与现场闭环用什么模板？

apps/org 运行时行为以 CAPABILITIES 为准；模板只示范签收字段。

**权威源**： [`docs/guides/fde/templates/template-signoff.md`](../../../docs/guides/fde/templates/template-signoff.md)

**节选自** [`docs/guides/fde/templates/template-signoff.md`](../../../docs/guides/fde/templates/template-signoff.md)：

### 签收单 — {{客户名称}}

> ← [返回实施流程](../../../docs/guides/fde/05-fde-implementation-process.md)

> **签收单编号**：`SIGNOFF-{{YYYYMMDD}}-{{CUSTOMER_CODE}}`
> **生成时间**：{{GENERATED_AT}} | **FDE**：{{FDE_NAME}}
> **步骤归属**：⑦ 验收移交 | **负责角色**：DM（交付经理） | **是否客户可见**：是（法律文件）
> **勿与 Org M4 混淆**：本单是 **FDE 项目交付签收**。it-ops 组织「签收准备包 / 八闸门」在 `/org/pilot`，材料齐不等于本单已签，亦不会由程序打开 `m4_claim_allowed`。

---

#### 一、项目信息

| 项 | 内容 |
|------|------|
| 项目名称 | `{{PROJECT_NAME}}` |
| 客户名称 | `{{CUSTOMER_NAME}}`（甲方） |
| 交付方 | `{{DELIVERY_COMPANY}}`（乙方） |
| 部署版本 | `{{DEPLOY_VERSION}}` |
| 部署环境 | `{{DEPLOY_ENV}}`（`{{DEPLOY_MODE}}`） |
| 交付日期 | `{{DELIVERY_DATE}}` |
| 验收日期 | `{{ACCEPTANCE_DATE}}` |
| 技术支持有效期 | `{{SUPPORT_START}}` ~ `{{SUPPORT_END}}` |

---

#### 二、验收 Checklist

##### 2.1 功能验收

| # | 验收项 | 验收标准 | 验收结果 | 备注 |
|:---:|------|------|:---:|------|
| 1.1 | `{{FUNC_ITEM_1}}` | `{{FUNC_STANDARD_1}}` | ✅ 合格 / ❌ 不合格 | `{{FUNC_NOTE_1}}` |
| 1.2 | `{{FUNC_ITEM_2}}` | `{{FUNC_STANDARD_2}}` | ✅ 合格 / ❌ 不合格 | `{{FUNC_NOTE_2}}` |
| 1.3 | `{{FUNC_ITEM_3}}` | `{{FUNC_STANDARD_3}}` | ✅ 合格 / ❌ 不合格 | `{{FUNC_NOTE_3}}` |
| 1.4 | `{{FUNC_ITEM_4}}` | `{{FUNC_STANDARD_4}}` | ✅ 合格 / ❌ 不合格 | `{{FUNC_NOTE_4}}` |
| 1.5 | `{{FUNC_ITEM_5}}` | `{{FUNC_STANDARD_5}}` | ✅ 合格 / ❌ 不合格 | `{{FUNC_NOTE_5}}` |

##### 2.2 数据验收

| # | 验收项 | 验收标准 | 验收结果 | 备注 |
|:---:|------|------|:---:|------|
| 2.1 | 数据导入完成 | 所有约定数据源已成功导入 | ✅ / ❌ | `{{DATA_NOTE_1}}` |
| 2.2 | 数据一致性 | 关键实体数量与预期一致（偏差 ≤ 5%） | ✅ / ❌ | `{{DATA_NOTE_2}}` |
| 2.3 | 数据质量 | 格式标准化、PII 脱敏已完成 | ✅ / ❌ | `{{DATA_NOTE_3}}` |

##### 2.3 SLA 验收

| # | 验收项 | 验收标准 | 验收结果 | 备注 |
|:---:|------|------|:---:|------|
| 3.1 | 系统可用性 | 验收期内可用性 ≥ 99.5% | ✅ / ❌ | `{{SLA_NOTE_1}}` |
| 3.2 | 响应时间 | P95 ≤ `{{SLA_LATENCY_MS}}`ms | ✅ / ❌ | `{{SLA_NOTE_2}}` |
| 3.3 | 金色问题通过率 | ≥ `{{GOLDEN_RATE}}`% | ✅ / ❌ | `{{SLA_NOTE_3}}` |
| 3.4 | 灰度回滚方案 | 回滚已测试，可在 `{{ROLLBACK_TIME}}` 分钟内完成 | ✅ / ❌ | `{{SLA_NOTE_4}}` |

##### 2.4 培训验收

| # | 验收项 | 验收标准 | 验收结果 | 备注 |
|:---:|------|------|:---:|------|
| 4.1 | 管理员培训 | 至少 1 名管理员完成操作培训（≥ 1 小时） | ✅ / ❌ | `{{TRAIN_NOTE_1}}` |
| 4.2 | 终端用户培训 | 至少 `{{MIN_USERS}}` 名用户完成培训（≥ 1 小时） | ✅ / ❌ | `{{TRAIN_NOTE_2}}` |
| 4.3 | 培训文档交付 | 操作手册 + 常见问题文档已交付 | ✅ / ❌ | `{{TRAIN_NOTE_3}}` |
| 4.4 | 培训沙盒可用 | 培训环境已创建，可独立使用 | ✅ / ❌ | `{{TRAIN_NOTE_4}}` |

---

#### 三、验收结论

##### 3.1 总体结果

| 维度 | 通过项 | 总项数 | 通过率 | 判定 |
|------|:---:|:---:|:---:|:---:|
| 功能验收 | `{{FUNC_PASS}}` | `{{FUNC_TOTAL}}` | `{{FUNC_RATE}}`% | ✅ / ❌ |
| 数据验收 | `{{DATA_PASS}}` | `{{DATA_TOTAL}}` | `{{DATA_RATE}}`% | ✅ / ❌ |
| SLA 验收 | `{{SLA_PASS}}` | `{{SLA_TOTAL}}` | `{{SLA_RATE}}`% | ✅ / ❌ |
| 培训验收 | `{{TRAIN_PASS}}` | `{{TRAIN_TOTAL}}` | `{{TRAIN_RATE}}`% | ✅ / ❌ |

##### 3.2 最终结论

```
{{ACCEPTANCE_CONCLUSION}}

□ 验收通过，同意签收
□ 验收不通过，需整改后重新验收
□ 验收有条件通过（条件见下方备注）
```

---

#### 四、签收确认

##### 甲方（客户方）确认

| 项 | 内容 |
|------|------|
| 甲方单位 | `{{CUSTOMER_NAME}}` |
| 验收人姓名 | `{{CUSTOMER_SIGNER}}` |
| 验收人职务 | `{{CUSTOMER_TITLE}}` |
| 验收人签名 | \\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_（手写签名） |
| 签收日期 | `____年____月____日` |
| 联系方式 | `{{CUSTOMER_CONTACT}}` |
| 备注 | `{{CUSTOMER_REMARK}}` |

##### 乙方（交付方）确认

| 项 | 内容 |
|------|------|
| 乙方单位 | `{{DELIVERY_COMPANY}}` |
| 交付经理 | `{{FDE_NAME}}` |
| 交付经理签名 | \\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_（手写签名） |
| 签收日期 | `____年____月____日` |
| 联系方式 | `{{FDE_CONTACT}}` |
| 备注 | `{{FDE_REMARK}}` |

---

#### 五、售后承诺

| 项 | 内容 |
|------|------|
| 质保期 | `{{WARRANTY_DAYS}}` 天（自验收签署之日起） |
| 首月护航 | ✅ 已激活：`{{ESCORT_START}}` ~ `{{ESCORT_END}}`（30 天自动健康检查） |
| 技术支持 | `{{SUPPORT_HOURS}}` 工作时间响应，紧急问题 `{{EMERGENCY_RESPONSE}}` 小时内响应 |
| 巡检频率 | `{{INSPECTION_FREQUENCY}}` |
| 升级渠道 | `{{ESCALATION_CONTACT}}` |

---

#### 填写指引

| 章节 | 填写时机 | 谁负责 |
|------|:---:|:---:|
| 一、项目信息 | 签收前 | DM（AI 自动填充） |
| 二、验收 Checklist | 逐项验收时 | DM（手工勾选，每项与客户确认） |
| 三、验收结论 | Checklist 完成后 | DM（AI 自动统计 + 客户确认） |
| 四、签收确认 | 签收仪式 | 客户负责人 + FDE 交付经理（手写签名） |
| 五、售后承诺 | 签收后 | DM（AI 自动生成） |

> **注意事项**：
> 1. 签收单为法律文件，所有不通过项必须有明确备注和整改计划
> 2. "部分通过"应在备注中说明具体偏差和可接受的原因
> 3. 双手写签名完成后扫描存档，原件给客户

---

> 模板文件：`docs/guides/fde/templates/template-signoff.md`
> 对应步骤：⑦ 验收移交

---

#### 完整

…

_(节选；全文见权威源)_


#### 3.0.6 渠道接入

**尽调问题**：多渠道消息与集成从哪里看？

**权威源**： CAPABILITIES「Channel」 · 分卷 04（MCP/API/生态）

渠道适配器随应用端演进；本卷不复制渠道清单。接入面与开放边界见生态卷，避免与分卷 04 双写。

#### 3.0.7 知识 / 本体 / RAG

**尽调问题**：企业知识如何组织、检索与治理？

知识引擎接线以 CAPABILITIES 为准；本节只节选知识体系手册。

**权威源**： [`docs/guides/knowledge/knowledge-system.md`](../../../docs/guides/knowledge/knowledge-system.md)

**节选自** [`docs/guides/knowledge/knowledge-system.md`](../../../docs/guides/knowledge/knowledge-system.md)：

### aiPlat 知识系统 — 完整指南

> 最后更新: 2026-08-11 · 原理优先，细节后置 · API/SQL/操作见附录
> **Agent 记忆寿命 / sticky / 任务选模锁**（与 RAG 三大存储并列的运行时记忆）：sticky/archive 租户边界见 [architecture/system-architecture-contract.md](../../../docs/architecture/system-architecture-contract.md)（契约表 Sticky 行）；`task_model_lock` 见根目录 `AIPLAT_CAPABILITIES.md` 与 Core `task_model_lock`。

---

#### 一、知识系统要解决什么问题

企业的知识散布在 PDF、Word、HTML、视频和数据库中。传统 RAG 面临三个核心挑战：

**1. 如何将异构资料转化为可检索的结构化知识？**
解决方案：一条 5 阶段管线。资料摄入→本体提取→向量索引→Wiki 合成→多路检索。
纯文本检索只能匹配关键词，无法理解「这篇 PDF 第 3 页的表格」和「那篇 Word 的第三章」讨论的是同一个概念。

**2. 如何让 RAG 检索到最相关的知识，而不是被无关内容淹没？**
解决方案：三大存储体系各司其职。向量 KB 存原始片段（搜原材料），GraphIndex 存实体/关系（搜结构化知识），LLM Wiki 存百科页面（搜人类可读知识）。检索时三路并行，路由到正确域过滤噪音。

**3. 如何发现知识缺口并自动补充？**
解决方案：质量闭环。HallucinationTracker 检测不忠实话→CandidatePool 积累候选缺口→ActiveSynthesis 自动生成补充页面→回写 Wiki。N≥3 次同一缺口才触发，避免误报。

##### 三大存储体系速览

```
┌─────────────────────────────────────────────────────────────────┐
│                         三大存储，各司其职                         │
├───────────────┬──────────────────┬──────────────────────────────┤
│ 向量 KB       │  GraphIndex      │  LLM Wiki                    │
│ 原始文档片段   │  知识结构图       │  人类可读百科页面              │
│ (SQLite)      │  (SQLite)        │  (Markdown 文件)              │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 存什么        │ 存什么            │ 存什么                        │
│ 解析后的文本   │ 实体节点+关系边    │ 实体页+合成页+矛盾页           │
│ 片段+向量      │ +超边            │ +知识原子                     │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 谁写          │ 谁写              │ 谁写                          │
│ 文档入库管线    │ 本体引擎 Step 10  │ KnowledgeSynthesizer         │
│ (不需要本体引擎) │ (提取实体+关系)    │ (从 GraphIndex 合成)          │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 谁读          │ 谁读              │ 谁读                          │
│ SqliteEmbedding│ BFS 图遍历       │ WikiPageRetriever             │
│ Retriever     │                  │                              │
├───────────────┼──────────────────┼──────────────────────────────┤
│ 核心原则       │                  │                              │
│ 本体引擎不修   │                  │                              │
│ 改向量 KB     │                  │                              │
└───────────────┴──────────────────┴──────────────────────────────┘
```

> 关于 TripleStore（将 5 个图连接为统一知识网络）请参见 §四·本体层。

---

#### 二、核心架构：三大存储 + 一条管线

```
用户查询
  │
  ├── [1] 资料摄入: DocumentParser→StructuredChunk→向量KB（零LLM，秒级可用）
  │
  ├── [2] 本体提取: OntologyEngine→实体/关系→GraphIndex（LLM异步，后台运行）
  │
  ├── [3] Wiki 合成: KnowledgeSynthesizer→Wiki 页面（从GraphIndex生成可读百科）
  │
  ├── [4] 知识检索: DomainRouter→三路并行→CRAG回退→RRF融合→答案
  │       Wiki(语义) + KB向量 + FTS5(关键词)
  │
  └── [5] 质量闭环: HallucinationTracker→ActiveSynthesis→回写Wiki
          不忠实话→候选缺口→自动补知识
```

##### 各阶段职责

| 阶段 | 组件 | 输入 | 输出 | LLM？ |
|:---:|------|------|------|:---:|
| ① 摄入 | DocumentParser | PDF/Word/HTML/MD | StructuredChunk | 否 |
| ② 提取 | OntologyEngine | StructuredChunk + 域YAML | 实体/关系→GraphIndex | 部分（PropertyExtractor） |
| ③ 合成 | KnowledgeSynthesizer | GraphIndex 实体/关系 | Wiki 页面 | ActiveSynthesis可选 |
| ④ 检索 | DomainRouter+CRAG+RRF | 用户查询 | 带来源的答案 | HyDE level 3 |
| ⑤ 闭环 | HallucinationTracker+ActiveSynthesis | ④的输出+用户信号 | 知识缺口→自动补充 | ActiveSynthesis |

##### 异步最终一致性

引擎采用异步最终一致性模型：
- ClassMapper（零 LLM）打粗粒度标签后，**先行落地基础向量索引**，保证检索立即可用
- PropertyExtractor（LLM）+ GraphBuild 作为**增强管线异步运行**
- 管线崩溃/超时时，**基础索引仍可服务**，RAG 不会完全不可用
- 增强完成后覆盖更新向量 + 更新 Wiki 页面

---

#### 三、资料层：如何将文档变成可检索的知识

##### 3.1 核心原则

**资料上传后立即创建基础索引（零 LLM，秒级可用）**。本体增强（LLM 提取实体/关系）在后台异步运行——二者独立，互不阻塞。

##### 3.2 摄入路径

| 方式 | 操作 | 适用场景 |
|------|------|------|
| 页面上传 | 知识 → **知识库** / Vault 上传 | 少量文件 |
| API 上传 | `POST /api/core/wiki/ingest` | 外部系统对接 |
| URL 导入 | 知识中心 → 粘贴 URL | 在线文档 |

##### 3.3 支持格式

| 格式 | 解析器 | 说明 |
|------|--------|------|
| PDF | DocumentParser (MinerU / Tesseract) | 表格保留为 StructuredTable |
| DOCX/PPTX | DocumentParser | 保留标题层级 |
| HTML | DocumentParser (BeautifulSoup) | 保留结构 |
| Markdown | DocumentParser (内置) | 保留 heading 路径 |
| TXT | DocumentParser (内置) | 纯文本 |
| 图片 | DocumentParser (OCR) | 图像提取文本 |
| 视频 | DocumentParser (Whisper) | 转写+帧提取 |

外部数据源通过 DataSource 抽象层连接（SQL/API/CSV/Excel），不移动数据。

##### 3.4 数据存储

存入 `kb_elements` 表（文本片段 + 向量），`kb_elements_fts` 表（全文索引）。DomainRouter 根据内容自动分类到对应域。

> 完整表结构和接入方式参见[附录 B](#附录-b存储表结构)。

---

#### 四、本体层：如何从文本中提取结构化知识

##### 4.1 本体与三大存储的关系

本体层是五阶段管线中**承上启下的核心连接组织**。它从向量KB读取文档片段，提取实体/关系写入 GraphIndex，再经由 KnowledgeSynthesizer 生成 LLM Wiki 页面——最终这些 Wiki 页面成为 RAG 检索的主要数据源。

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  向量KB                  GraphIndex           LLM Wiki    │
│  原始文档片段  ──提取──→  实体+关系  ──合成──→  百科页面   │
│  (不用本体引擎)          (本体引擎 Step10)    (Step11)     │
│        │                      ▲                  │        │
│        │                      │                  │        │
│        └── 引擎读取文档 ──────┘                  │        │
│                                                  │        │
│        ┌─────────────────────────────────────────┘        │
│        ▼                                                  │
│  RAG 检索（三路并行）                                      │
│  Wiki语义 + KB向量 + FTS5关键词                            │
│  ← DomainRouter 域路由 + CRAG回退 →                        │
└──────────────────────────────────────────────────────────┘
```

**四个核心关系**：

1. **向量KB→本体**：本体引擎从 `kb_elements` 表中读取文档片段，提取实体和关系写入 GraphIndex。向量KB 是「原材料仓库」，本体是「提炼后的知识模型」——二者独立运行，向量KB 不需

…

_(节选；全文见权威源)_


#### 3.0.8 Agent / Skill 运行

**尽调问题**：多步工具调用与技能执行如何选型？

矩阵同时服务产品评估与技术选型；实现细节见技术卷。

**权威源**： [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md)

**节选自** [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md)：

### 执行决策矩阵

> **一句话**：帮你选「这件事该用程序、LLM、技能、Agent，还是流水线」——先按场景判断，细节与代码证据在文末附录。
> **状态**：Living Spec（与实现同步；冲突时以代码为准）· **v1.12** · 2026-10-17
> **互补文档**：[产物怎么验收](../../../docs/architecture/execution-quality-gates.md) · [能力剖面细节](../../../docs/architecture/capability-profile.md) · [知识 / Memory / CRAG](../../../docs/guides/knowledge/knowledge-system.md) · [Agent 总览](../../../docs/reference/agents/agent-system.md)（后端规则以本文为准）

---

#### 1. 先记住五条

1. **能写死规则就别用模型**——权限、闸门、算术、已有 handler，都走程序。
2. **加能力从便宜到贵**——改现有代码 → Skill/CLI → Tool → 插件 → MCP → 新内核接口。
3. **行为靠配置字段，不靠「某个 Agent 名字」**——引擎里禁止按业务角色硬编码分支。
4. **想钉死怎么跑，写「执行混合」或显式后端**——二者都不会被能力剖面降级。
5. **工厂生成物尽量薄，但可声明期望跑法**——选 Agent 类型 + 技能/工具；推荐写 `architecture_profile`（E1）；团队 YAML 仍可覆盖。

---

#### 2. 我该选谁？（按需求）

| 你想做的事 | 首选 | 别这样做 |
|------------|------|----------|
| 「满足条件就拒绝 / 必须可审计」 | **程序规则 / PolicyGate** | 让模型当权限系统 |
| 原子能力：读文件、调 API、算数（无业务 SOP） | **Tool**（可配 `meta_tool` 强制 code） | 纯提示词假装已执行 |
| 固定业务步骤 + 确定性副作用 | **handler Skill**（`handler.py`） | 用 prompt 假装写盘/调 API 成功 |
| 固定业务步骤，中间要模型填语义 | **prompt / hybrid Skill** | 把长 SOP 塞进流水线 `config.prompt` |
| 多步探索、自己选工具、做错能改 | **Agent 环**（`react_tools` 等） | 单次调用假装完成多步 |
| 固定多角色流水线 | **Workflow 编排**多 stage（stage 内仍是 Agent 或 Skill） | Agent 无门控互调；把 Workflow 当成「不要 Agent」 |
| 外部多工具 / 第三方维护的工具集 | **MCP**（见下方准入） | 为核心高频路径新建内核 Syscall |
| 写代码并落到磁盘 | 编码闭环；优先 Agent 环 | 空回复直接落盘 |

##### 2.1 LLM vs 程序（硬规则）

| 条件 | 路径 |
|------|------|
| 结果必须可复现、可审计、可规则化 | **程序**（PolicyGate / handler / Tool） |
| 需理解自然语言、开放生成、语义填充 | **模型**（prompt / oneshot） |
| **单次**「模型出计划 → 程序执行」 | **`hybrid` Skill**（syscall `Skill.execute`） |
| **多轮**工具调用、观察结果、自我纠正 | **`agent` 循环**（`architecture_profile=react_tools` 等） |
| 算术 / 日期 / 结构化解析 / 转义规范化 | **禁止纯 LLM 心算** → Tool 或 `meta_tool` 强制走 code（见 §2.3） |

> 「两者都要」**不是**随便选 hybrid 或 Agent：单次计划+执行用 hybrid；需要多轮反馈用 Agent。

##### 2.2 Tool vs handler Skill vs 程序

| 形态 | 何时选 |
|------|--------|
| **程序 / PolicyGate** | 权限、闸门、配额、合规——全局横切，不进业务 SOP |
| **Tool** | 原子、无业务步骤、多 Agent 可复用（`sys_tool_call`） |
| **handler Skill** | 有业务步骤/SOP、可复用、副作用可声明（`effects`），且执行是确定性代码 |
| **prompt Skill** | 步骤在 SOP 里，但中间判断必须靠模型 |

> **一句话**：横切策略用**程序**（PolicyGate / 闸门）；业务原子能力用 **Tool**；带业务 SOP 的确定性步骤用 **handler Skill**。

##### 2.3 meta-tool（该算就算）

算术、日期差、JSON/CSV 解析、路径规范化等**确定性变换**不得交给模型「心算」。Stage/Agent 可声明：

- `meta_tool.enabled` / `auto_bind` — 优先绑定 code 类元工具
- `meta_tool.force` — 强制走 code（逃逸舱口）

**意图如何识别（不是模型自判）**：

1. **显式配置**：`meta_tool.force=true` / `enabled` → 直接偏好 code（不依赖文本匹配）。
2. **任务文本正则**：`meta_tool.detect_meta_tool_intent(task)` 用 `_INTENT_PATTERNS`（arithmetic / datetime / parse_transform / escape_hatch）匹配用户/stage 任务串。
3. **提示注入**：命中后在 tools 描述末追加 `[META TOOL]` hint，并把 `code` 置顶（`build_meta_tool_hint` / `ensure_code_meta_tool`）。

落点：`PipelineStageConfig.meta_tool` → `apply_meta_tool_config` → loop 上下文 `_prefer_code_meta_tool` / `_force_code_meta_tool`。

##### 2.4 Workflow 与 Agent（不是二选一）

**Workflow / Pipeline = 编排壳**：决定 stage 顺序、handoff、HITL。
**每个 stage 内部**仍按 §3/§4 选 `execution_backend` + Skill：可以是 Agent 环，也可以是 handler / oneshot。
禁止把「用了 Pipeline」理解成「不许用 Agent」。

##### 2.5 MCP 准入（硬标准）

| 选 MCP | 选薄 Tool |
|--------|-----------|
| 多工具包、外部维护、协议边界清晰 | 单原子操作 |
| **非**核心热路径（描述 token 贵） | 内部核心高频（宜进 ToolRegistry） |
| 已证明阶梯 1–4 做不到（见根 CLAUDE.md §20） | 扩展已有代码 / CLI / Skill 即可 |

新 MCP / 新 Syscall 合入须过 `scripts/check_cost_ladder.py`（E4）。

**最小「阶梯证明」模板**（PR / `# ladder-ok` / CAPABILITIES 任选其一写清）：

```text
why_not_1_extend: <为何不能扩已有代码/Skill>
why_not_2_cli:    <为何 CLI+SOP 不够>
why_not_3_tool:   <为何不能做薄 Tool>
why_not_4_plugin: <为何不能放 ~/.aiplat/plugins>
rung:             MCP | Syscall
blast_radius:     <失败/token/权限影响>
```

**证明质量最低标准（v1.9）**：

- `why_not_1_extend`、`why_not_2_cli`、`why_not_3_tool`、`why_not_4_plugin` 四项均非空，且每项不少于 20 字；
- `rung` 必须为 `MCP` 或 `Syscall`；
- `blast_radius` 必须说明失败/token/权限影响；
- 缺任一字段或明显占位符（如 `N/A`、`待补`）→ CI 硬失败。

内联 `# ladder-ok: <reason>` 理由需不少于 15 字；支持 `# ladder-ok: temporary until <date>`，到期后重新校验。仅写 CAPABILITIES 名字、无证明块且无合格 `# ladder-ok` → **不通过**。

##### 2.6 执行封存（完成语义 · 平台规范）

「完成」不是模型说 DONE。封存是平台横切：DONE 前校验、DONE 后回执与质量复核。
**权威在 aiPlat Core**：公共入口 `execution_seal`（`check_done_verify` / `coding_deliverable_veto` / `seal_answer_with_receipts` / `seal_before_finish`）+ `quality_review_blocks_success`。叶实现 `bind_completion_to_receipts` 仅由 seal 调用；完成路径禁止直调。CoreFacade 有同名 re-export。
**Pi 壳不执行封存门禁**（见 [`HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md) 非目标）。混合企业 ≠ 编码闭环已在 Pi 上跑完。

| 路径 | DONE 前 | 完成回执 | 质量复核可翻失败 | 现状 |
|------|---------|----------|------------------|------|
| **ReAct**（StageRunner 默认、`coding_closed_loop`） | `done_verify` + coding 交付否决 + `require_review` 跟进技能 | `seal_answer_with_receipts`（→ leaf `bind_completion_to_receipts`） | 有（finalize / orphan 编码路径） | **全套** |
| **PlanExecute** | 与 ReAct 相同的 coding 交付否决 + `run_done_verify`（异常对编码 fail-closed） | 步骤记 `_tool_receipts` + 完成前 `seal_before_finish` | finalize 会跑 | **封存对齐** — 不自动派发 autoreview，缺跟进则 ERROR，不标完成 |
| **Pipeline llm oneshot** | `gate_llm_file_output_stage`（落盘前，内走 `seal_answer_with_receipts`） | 无成功工具回执的「已修好 / 路径」**否决落盘**（不改写 `## FILE:` 正文） | stage QR 硬失败可置 FAILED | file + 硬 `require_review` **schema 强制**升 `react_tools`（`KEEP_LLM` 无效）；软审查仍可 oneshot + gate 否决 |
| **Workspace Execute** | 与 ReAct 相同（`inject_workspace_coding_defaults`） | 同 ReAct | 同 ReAct | `loop_type=plan_execute` 会建 PlanExecute；**file-output / `require_review` 仍强制 ReAct**（自动跟进审查只在 ReAct） |
| **Pi hybrid** | **无** | 仅 Memory 回写打 `[未核验]`/`[失败]` 与 `completion_*` 标签；**不改用户可见完成** | **无** | 桥只投递；PolicyGate / 编码宪法 / `task_model_lock` 仍在 Core `sys_llm_generate` |

…

_(节选；全文见权威源)_


#### 3.0.9 治理下执行

**尽调问题**：权限、审批、审计如何嵌进产品路径？

完整威胁模型与 L 级定级见分卷 05；此处只给产品路径嵌入视图。

**权威源**： [`docs/reference/security/security-architecture.md`](../../../docs/reference/security/security-architecture.md)

**节选自** [`docs/reference/security/security-architecture.md`](../../../docs/reference/security/security-architecture.md)：

### aiPlat 安全架构 — 纵深防御模型

> 基于零信任原则 (never trust, always verify) 的六层防御体系。

#### 防御层级

| 层 | 名称 | 机制 | 实现 |
|:--:|:---|:---|:---|
| **L1** | 网络边界 | API 网关, TLS, CORS | Management API Gateway (port 8000) |
| **L2** | 身份认证 | JWT Bearer Token | 单用户模式可选, 多租户强制 |
| **L3** | 权限控制 | RBAC + PBAC | PolicyGate (deny-by-default) + Permission Check |
| **L4** | 操作审批 | HITL Approval | ApprovalGate + 审批申请/批准/拒绝 |
| **L5** | 执行沙箱 | Isolated Subprocess | SandboxGate — 工具执行隔离 |
| **L6** | 审计追溯 | SHA-256 Chain | Audit Mixin — 回查每条操作 |

#### 零信任原则落地

| 原则 | aiPlat 实现 |
|:---|:---|
| 持续验证 | PolicyGate 每次 syscall 前检查权限 |
| 最小权限 | deny-by-default 策略, 必须显式授权 |
| 微分段 | Skill/Tool/Agent 权限独立, 互不继承 |
| 假定被破 | SandboxGate 隔离, 工具执行不在主进程 |
| 全程审计 | SHA-256 hash chain, 每次操作不可否认 |

#### 安全边界

```
Internet → Management Gateway (唯一入口)
              ↓ PolicyGate (RBAC 检查)
              ↓ API 路由
              ├── Core (Agent Engine + Pipeline)
              │     ↓ ApprovalGate (高危操作审批)
              │     ↓ SandboxGate (工具执行隔离)
              ├── Infra (Model Management + LLM)
              │     ↓ SecretsManager (AES-256-GCM 密钥)
              └── Platform (Knowledge Base + Builder)
                    ↓ Audit Log (SHA-256 chain)
```

#### GitHub Branch Protection Rules (Recommended)

```yaml
### Apply in GitHub → Settings → Branches → Add rule
branches: [main]
rules:
  - require_pull_request: true
    required_approvals: 1
    dismiss_stale_reviews: true
  - require_status_checks: true
    contexts: ["Lint & Type Check", "Test (pytest)", "L5 Depth Tests"]
  - require_conversation_resolution: true
  - require_code_owner_review: false  # no CODEOWNERS file
  - enforce_admins: true
```

#### 零信任验证清单

| # | 层级 | 验证方式 | 状态 |
|:--:|:---|:---|:--:|
| L1 | 网络边界 | `curl http://localhost:8000/health` — 只有 mgmt 端口暴露 | ✅ |
| L2 | 身份认证 | JWT 无效时返回 401 — `scripts/security-attack-sim.py` S1 验证 | ✅ |
| L3 | 权限控制 | PolicyGate deny-by-default — 未授权 tool 调用被拒绝 | ✅ |
| L4 | 操作审批 | ApprovalGate 高危操作需审批 — change_control.py 验证 | ✅ |
| L5 | 执行沙箱 | SandboxGate 隔离 — 工具执行不在主进程 | ✅ |
| L6 | 审计追溯 | SHA-256 chain 可验证 — `audit_mixin.py verify_integrity()` | ✅ |

#### FDE 部署验证报告

> 外部人员按 deploy-guide.md 从头部署并计时。

| 步骤 | 内容 | 耗时 | 状态 |
|:--:|------|:--:|:--:|
| 1 | git clone + pip install | ~3min | ✅ |
| 2 | 配置 API Key | ~1min | ✅ |
| 3 | `./start.sh` | ~2min | ✅ |
| 4 | `curl /health` 验证 | ~10s | ✅ |
| 5 | 运行第一个 Agent | ~1min | ✅ |
| 6 | `verify-l4-pyramid.sh` 全量验证 | ~10s | ✅ |
| 7 | `verify-deploy.sh` 部署验证 | ~30s | ✅ |
| **总计** | | **~8 分钟** | **从头部署到全量验证通过** |

##### FDE 差距

| 项 | 状态 | 说明 |
|:---|:--:|:---|
| 新手无障碍部署 | ✅ | 8分钟从零到验证 |
| 生产部署就绪 | ✅ | Helm + ArgoCD + 回滚 |
| 外部人验证 | 需要 | 邀请未接触过 aiPlat 的人做盲测 |
| 大规模部署 | 待验证 | 需要 K8s 集群 + 100 并发压力测试 |


#### 3.0.10 薄交付（Pi）

**尽调问题**：用户侧如何轻量跑快照、不装全栈？

厂外默认 **Pi-only**；可选 **Pi + aiPlat 回连** ≠ 完整 Enterprise Runtime，也不等于在用户机默认安装全栈。

**权威源**： [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) · [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) · [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md)

**节选自** [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md)：

### Plan: aiPlat × Pi 薄 Runtime（1C + 2C）

> Living 摘要 · 2026-10-12 · 包：`packages/aiplat-pi-runtime/`
> **状态**：Phase 0–2 + 工厂/FE/ZIP **已合并 main**（PR [#251](https://github.com/zhuxiangqun/aiPlatform/pull/251)）
> **Live 门**：✅ `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh`（Ollama `ollama/qwen2.5:3b` — CLI print + SOP + `/aiplat-status` + HTTP `createAgentSession`）

#### 术语：「Hybrid」消歧

| 语境 | 含义 | 权威入口 |
|------|------|----------|
| **Pi ↔ aiPlat 企业回连** | `AIPLAT_ENTERPRISE=1` 等可选厚能力（KB/工具/Memory/审批） | `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md` |
| **Skill 执行类型** | `execution_type` 等技能实现模式（与企业回连无关） | 各 `SKILL.md` / 引擎 Skill 规约 |
| **Builder / 工厂模式** | 应用工厂产物或流水线形态中的 “hybrid” 措辞 | Builder / 工厂相关 docs（勿与上表第一行混用） |

本文其余「混合 / Hybrid」若未特别说明，均指 **第一行：Pi↔aiPlat 企业回连**。

#### 战略：两条轴，勿合成一条

Pi 是极简 Agent Harness（非治理平台）。与 aiPlat 的关系拆成**两条产品轴**，禁止写成「一个 Pi 集成路径解决所有问题」。

| 轴 | 定位 | 状态 | 解决什么 | 不解决什么 |
|----|------|------|----------|------------|
| **（B）厂外** | 用户侧薄交付宿主：导出包 → `pi -e` / 薄 HTTP | **既定主路径**（已落地） | 不装全栈也能跑快照（SOP + skills + handler） | 平台级厚度（Memory / SECI / PolicyGate / 知识 syscall） |
| **（A）厂内** | 可选编码执行核：CLI/RPC 包在 PolicyGate 外 | **⓪ 合并关闭**（2026-10-14 `blank_not_proven`）：Workspace Execute Pi 旁路已拆；离线 CLI/探针归档；CAPABILITIES **不**标「厂内已接线」 | （历史宣称）编码闭环副作用 | 替代编排治理；默认换掉 ReActLoop |

##### 分层，而非两套平行产品（2026-10-13 锁定）

> **能力重叠 ≠ 交付重复。** aiPlat 白皮书里已有 Agent 循环、工具、多模型——那是**平台能力清单**。
> Pi 默认交付解决的是另一件事：**工厂产出物如何在用户侧轻量跑起来**（不装 core/platform/infra 全栈）。

| 说法 | 是否采纳 |
|------|:--------:|
| 执行面（Pi）与治理面（aiPlat）**分层** | ✅ |
| 用户对外装「两个平权平台」、两套权限/审计 | ❌ |
| 企业场景入口仍是 aiPlat（或 Pi 壳回连 aiPlat）；Pi 对用户透明为「更轻的跑法」 | ✅ |
| 用 Pi 替代 aiPlat 编排/门禁/多租户 | ❌ |

```text
aiPlat（控制面 / 工厂 / 治理）
    │ 导出快照（AGENT.md / skills / handler）
    ▼
Pi（执行面 / 厂外薄宿主）── 默认 Pi-only 可闭环
    │ 可选 AIPLAT_ENTERPRISE=1
    └── 回连 aiPlat API（KB / 工具 / 原生门禁 / Memory / 审批等待；PolicyGate 留在服务端）
```

**产品决策（已锁定 · 2026-10-12；措辞澄清 · 2026-10-13）**

> **默认：只靠 Pi 就能跑产出物。**
> **企业级：Pi + aiPlat（混合）——Pi 仍是用户侧宿主，厚能力经 aiPlat 托管 API / 门禁回连。**
> **不以「用户侧单独部署厚 aiPlat 运行时」为默认交付形态。**
> **不以「Pi 与 aiPlat 两套平行产品」对外叙事。**

| 模式 | 用户侧 | 能力 | 状态 |
|------|--------|------|------|
| **Pi-only** | 导出包 + `pi` / 薄 HTTP + 自备模型 | SOP + skills + handler（确定性桥） | **默认交付 · 已落地** |
| **Pi + aiPlat** | 同上 Pi 壳 + `AIPLAT_ENTERPRISE=1` 回连 | + 只读 KB + 允许列表工具代理 + **原生工具门禁** + **Memory capture** + **审批等待**（`AIPLAT_ENTERPRISE_APPROVAL=1` → status/pending/wait；裁决在平台 UI） | **混合阶梯 1–5 · 已接线** |
| ~~厚运行时~~ | 用户侧直接跑裁剪 aiPlat | 接近平台 Agent | **非默认**；仅特殊驻场/私有化例外 |

**Pi-only 必须能完成的闭环（验收）**

- 加载导出包（manifest / AGENT.md / skills）
- 对话 + SOP 注入
- `/skill-*` 与 `handler.py` 确定性执行
- 自备 LLM（Ollama / 云厂商均可）
- **不依赖** 8002/8003 进程

**Pi + aiPlat 才提供的企业能力（混合回连，不搬进 Pi 进程）**

- PolicyGate / RBAC / 审批
- Memory / SECI / 经验回写
- 平台知识检索（`sys_kb_retrieve` 等）
- 运行时审计 / 可观测回写
- 租户配额与成本治理

混合形态示意（KB + 工具 + 原生门禁 + Memory + 审批等待已落地）：

```text
用户 ──► Pi（对话壳 + 本地 skills/handler）
              │
              ├── 本地可完成 → 不回连（默认 Pi-only）
              └── AIPLAT_ENTERPRISE=1
                    ├── enterprise_tool_gate：block bash/write/edit（默认）
                    ├── POST /platform/kb/query          （只读 KB）
                    ├── AIPLAT_ENTERPRISE_TOOLS=… → POST …/tools/{name}/execute
                    ├── AIPLAT_ENTERPRISE_MEMORY=1 → POST /platform/memory/capture
                    └── AIPLAT_ENTERPRISE_APPROVAL=1 → GET /platform/approvals…
                          （wait/status only；approve/reject 在平台 UI）
```

接线入口：`enterprise_kb.ts` / `enterprise_tools.ts` / `enterprise_tool_gate.ts` / `enterprise_memory.ts` / `enterprise_approval.ts`（由 `aiplat-app.ts` 条件注册）。详见 `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`。

##### 双模式内涵（精确化 · 2026-10-13）

> **合理方向 = 控制面 / 执行面分层**，不是「两套平权平台」。企业级 ≠ 单一功能，而是可观测、可治理、可审计的平台工程；Pi 不承担该体系。

| 模式 | 内涵 | 能力边界 | 不安全假设 |
|------|------|----------|------------|
| **模式一 · 仅 Pi** | 独立、可自托管的极简 Agent Harness | `read`/`write`/`edit`/`bash`、会话内循环、多模型抽象；适合个人 / 小团队 / 快速验证 | **无**内置权限、队列、成本、审计 → **禁止**默认无人值守生产 |
| **模式二 · P

…

_(节选；全文见权威源)_


**节选自** [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md)：

### @aiplat/pi-runtime

Thin **Pi Package** Runtime for aiPlat factory **Agent-mode** artifacts.

- **aiPlat** = heavy factory (PRD → AGENT.md / SKILL.md / `agent_manifest.json`)
- **This package** = **厂外** user-side thin host (Pi extensions + package `skills/`)

#### Two axes (do not merge)

See [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md).

| Axis | Role of Pi | Status |
|------|------------|--------|
| **(B) Factory-out** | User-side host for artifacts | **Shipped** — this package |
| **(A) Factory-in** | Optional coding exec kernel behind PolicyGate | **Merge-closed** (`blank_not_proven`) — Execute bypass removed; offline probes only |

**Product decision (locked)**

| Mode | Meaning |
|------|---------|
| **Pi-only** (default) | Artifacts run with Pi alone: SOP + skills + handler + your LLM. No 8002/8003. |
| **Pi + aiPlat** (enterprise) | Same Pi shell; opt-in hybrid (`AIPLAT_ENTERPRISE=1`). **KB** + **allowlisted tools** + **native tool gate** + **Memory capture** + **Approval wait** (`AIPLAT_ENTERPRISE_APPROVAL=1` → status/pending/wait + Unattended Inbox via `AIPLAT_ENTERPRISE_ATTENDANCE`; humans approve in platform UI). |
| Thick aiPlat-only on user machine | **Not** the default delivery shape. |

**Layered, not two parallel products:** aiPlat already has agent loops / tools / multi-model in the **platform** sense. Pi exists so **factory artifacts can run without installing the full stack**. Overlap in capability lists ≠ redundant delivery. Do not market Pi and aiPlat as two peer platforms with separate auth/audit. Enterprise entry remains aiPlat (or Pi shell reconnecting to aiPlat).

Do not claim Pi-only equals full in-factory agent. Enterprise thickness is **Pi + aiPlat**, not “stuff the platform into the Pi process”.

#### Enterprise hybrid (opt-in)

Default remains Pi-only. See [`docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md) and delivery appendix [`docs/HYBRID_ENTERPRISE_DELIVERY.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md) (SKU + KB citation acceptance).

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=http://127.0.0.1:8003      # or :8000/api GW; NOT :8003/api
export AIPLAT_TENANT_TOKEN=<bearer>                # or AIPLAT_API_KEY
### optional KB: AIPLAT_KB_COLLECTION_ID=default
### optional tools (empty = tools off, KB only):
export AIPLAT_ENTERPRISE_TOOLS=calculator
### optional: AIPLAT_CORE_URL=http://127.0.0.1:8002
### native gate ON by default under ENTERPRISE=1 (bash/write/edit blocked)
### escape: AIPLAT_ENTERPRISE_ALLOW_NATIVE=1  or  AIPLAT_ENTERPRISE_TOOL_GATE=0
### optional memory writeback:
### export AIPLAT_ENTERPRISE_MEMORY=1
### optional approval wait (no approve from Pi):
### export AIPLAT_ENTERPRISE_APPROVAL=1
### export AIPLAT_ENTERPRISE_ATTENDANCE=inbox   # attended|inbox|auto
### export AIPLAT_ENTERPRISE_SESSION_ID=my-pi-session

pi -e .
### /aiplat-status          → enterprise_hybrid / tools / tool_gate / memory / approval
### /aiplat-enterprise      → KB reconnect status
### /aiplat-memory          → memory writeback status
### /aiplat-approval        → approval wait-bridge status
### tools: aiplat_kb_retrieve | aiplat_tool_execute | aiplat_memory_capture
### | aiplat_approval_status | aiplat_approval_pending | aiplat_approval_wait
### | aiplat_unattended_inbox | aiplat_unattended_wait
```

Offline gates (mock HTTP / pure policy, no platform process):

```bash
node packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
node --experimental-strip-types packages/aiplat-pi-runtime/scripts/enterprise_kb_citation_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_delivery_scan_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_kb_health_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_memory_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_approval_smoke.mjs
```

Policy

…

_(节选；全文见权威源)_


### 3.1 能力统计（摘自 CAPABILITIES）

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|
| Harness 执行引擎 | 955 | 1 | 956 |
| 记忆子系统 | 93 | 0 | 93 |
| 知识引擎（本体） | 911 | 9 | 920 |
| RAG 检索 | 60 | 0 | 60 |
| 知识基础设施 | 30 | 0 | 30 |
| Agent 系统 | 319 | 0 | 319 |
| Skill 系统 | 215 | 0 | 215 |
| 安全与治理 | 126 | 0 | 126 |
| 可观测性 | 43 | 0 | 43 |
| 模型基础设施 | 46 | 0 | 46 |
| 部署与运维 | 23 | 0 | 23 |
| 扩展与学习 | 177 | 1 | 178 |
| Gate 系统 | 177 | 0 | 177 |
| 评估系统 | 614 | 0 | 614 |
| MCP 协议 | 11 | 0 | 11 |
| A2A 协议 | 9 | 0 | 9 |
| 文档智能 | 27 | 0 | 27 |
| 工具生态 | 74 | 0 | 74 |
| 微调系统 | 14 | 0 | 14 |
| 部署与灰度 | 7 | 0 | 7 |
| 运行时干预 | 44 | 0 | 44 |
| Arena & 调度 | 7 | 0 | 7 |
| 平台治理 | 152 | 0 | 152 |
| Infra 基础设施 | 20 | 0 | 20 |
| 核心API统一入口 | 7 | 0 | 7 |
| 编排系统 | 10 | 0 | 10 |
| 管理 & 质量 | 116 | 0 | 116 |
| 编排层 | 22 | 0 | 22 |
| L6 自主能力 | 8 | 0 | 8 |
| 记忆系统白盒化 | 7 | 0 | 7 |
| 记忆运行时过滤 | 2 | 0 | 2 |
| MoA多模型推理 | 5 | 0 | 5 |
| AI知识层增强 | 3 | 0 | 3 |
| Hermes压缩对标 | 3 | 0 | 3 |
| Scenario Simulation | 5 | 0 | 5 |
| Decision Lineage | 6 | 0 | 6 |
| Security 3D 增强 | 4 | 0 | 4 |
| Global Branching | 3 | 0 | 3 |
| EvoX 蜂群协作 | 9 | 0 | 9 |
| 闭环执行层 | 7 | 0 | 7 |
| 知识编译与OKF | 0 | 0 | 0 |
| 对话→Wiki 自动管线 | 6 | 0 | 6 |
| Skill 目录标准化 | 9 | 0 | 9 |
| Web 工具归并 | 4 | 0 | 4 |
| E2E 端到端验证 | 18 | 0 | 18 |
| **总计** | **4408** | **11** | **4419** |

### 3.2 上手路径（节选）

### aiPlat 快速入门指南

> 15 分钟从零启动到运行第一个 Agent。

#### 前置条件

- Python 3.11+
- pip
- 至少一个 LLM API Key (DeepSeek/OpenAI/Qwen 等)

#### Step 1: 克隆与安装 (2 分钟)

```bash
git clone https://github.com/zhuxiangqun/aiPlatform.git
cd aiPlatform
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
pip install -e aiPlat-core/ aiPlat-infra/ aiPlat-platform/ aiPlat-management/
```

#### Step 2: 配置 API Key (1 分钟)

```bash
export DEEPSEEK_API_KEY="sk-your-key-here"
### 或 OpenAI:
export OPENAI_API_KEY="sk-your-key-here"
```

#### Step 3: 启动服务 (2 分钟)

```bash
./start.sh
```

服务启动后：

| 端口 | 服务 | 用途 |
|:---|:---|:---|
| 8000 | Management | API 网关 + 诊断面板 |
| 8001 | Infra | 模型管理 + 基础设施 |
| 8002 | Core | Agent 引擎 + Pipeline |
| 8003 | Platform | 知识库 + Builder |

#### Step 4: 验证安装 (1 分钟)

```bash
### 健康检查
curl http://localhost:8000/api/diagnostics/health/all

### 运行验证脚本
bash scripts/verify-l4-pyramid.sh
### → 预期: L5 (元循环工程)
```

#### Step 5: 运行第一个 Agent (3 分钟)

```bash
### 列出可用 Agent
curl http://localhost:8000/api/core/workspace/agents

### 执行一个 Agent 任务
curl -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"用三句话解释 L4 循环工程是什么"}]}'
```

#### Step 6: 查看诊断面板

浏览器打开 `http://localhost:8000/docs` → 查看全部 API 文档。

```bash
### 架构守卫检查
curl -X POST http://localhost:8000/api/diagnostics/guard/run

### 全量诊断
curl -X POST http://localhost:8000/api/diagnostics/run-all
```

#### 下一步

管理端 UI（`./start.sh` 后通常为前端端口，如 `http://localhost:5173`）：

| 你要做的事 | 打开 |
|------------|------|
| 建域 / 改说明书 / 提案 apply | **知识 → 业务本体** `/knowledge/business` |
| 文档入库与检索 | **知识 → 知识库** `/knowledge/library` |
| 一句话生成应用 | **AI 应用工厂** `/app/factory` |
| FDE 现场八步交付 | **FDE 工作台** `/diagnostics/fde` |
| it-ops 组织试点 / 签收准备 | **组织试点** `/org/pilot` |

操作手册入口：[`manuals/README.md`](../../../docs/guides/README.md) · 合册 [`../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md`](../../../docs/contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) · Org [`../contracts/ORG_L5_RUNBOOK.md`](../../../docs/contracts/ORG_L5_RUNBOOK.md)。

- [API Reference](../../../docs/reference/API/api-reference.md) — 完整 API 文档
- [自主性评估报告](../../framework/aiplat-complete-assessment.md) — 系统能力评估
- [验证协议](../../../docs/reference/framework/verification-protocol.md) — 独立复现验证

#### 常见问题

**Q: 启动失败？**
```bash
### 检查端口占用
lsof -i :8000 -i :8001 -i :8002 -i :8003
kill <PID>
```

**Q: Agent 执行返回错误？**
```bash
### 检查 API Key
echo $DEEPSEEK_API_KEY
### 查看日志
tail -f ~/.aiplat/logs/core.log
```

**Q: 如何升级？**
```bash
git pull origin main
./start.sh  # 重启服务
```


### 3.3 变更影响矩阵（节选）

产品评估「改一处影响哪」以矩阵为准，不在卷内另维护影响表。

### Capability Impact Matrix

> Auto-generated from `capability_registry.yaml`
> Version: 1.1.0 | 34 domains | 3576 capabilities (caps_count) | 3576 symbols (provides)

> 口径：`caps_count` 应对齐 `len(provides)`（登记公开符号数）；勿与 `AIPLAT_CAPABILITIES.md` 产品能力行计数混算。

#### Consumer-to-Capability Dependencies

##### aiPlat-infra/infra/management/model/config_loader.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| infra-infrastructure | §二十二 Infra 基础设施 | 6 | adapters 发现与 CredentialPool 共用 DB 路径 |

##### aiPlat-management/frontend/src/pages/Core/Memory/Memory.tsx

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-white-boxing | §二十八 记忆系统白盒化 | 5 | 记忆管理页面 |

##### aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 837 | FDE 能力自描述 |

##### aiPlat-platform/apps/fde/api/router.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| core-api-unified-entry | §二十三 核心API统一入口 | 2 | FDE 路由挂载 |

##### core/api/core_facade.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 873 | evo_compute G0/G1/G2/G3 + production deepen 门面入口 |
| knowledge-engine-ontology | §三 知识引擎（本体） | 837 | N02 ObjectType publish Facade 入口 |
| skill-system | §六 Skill 系统 | 224 | CoreFacade 暴露 skill compat |
| evaluation-system | §十三 评估系统 | 669 | CoreFacade 暴露 m2 deferred estimate |
| diagnosis-system | §十三-b 诊断系统 | 20 | CoreFacade 暴露 get_diagnosis_store |
| tool-ecosystem | §十六 工具生态 | 76 | CoreFacade 暴露 tool compat |
| a2a-protocol | §十四附 A2A 协议 | 2 | CoreFacade 再导出 A2A 能力 |

##### core/api/routers/adapters.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| runtime-intervention | §十九 运行时干预 | 66 | /model-override 端点 |

##### core/api/routers/agents.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| agent-system | §五 Agent 系统 | 338 | Agent REST 端点 |

##### core/api/routers/diagnostics.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| runtime-intervention | §十九 运行时干预 | 66 | adoption-metrics 附带 Howl 干预次数 |

##### core/api/routers/memory.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| memory-subsystem | §二 记忆子系统 | 59 | 全量 REST 端点 |
| memory-runtime-filtering | §二十九 记忆运行时过滤 | 2 | GET/PUT /memory/rules |

##### core/api/routers/pipeline_execution.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-system | §二十四 编排系统 | 4 | fork/forks 端点经 CoreFacade 取 store |

##### core/api/routers/wiki.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 837 | Wiki CRUD + index + ingest 端点 |
| ai-knowledge-layer | §三十一 AI知识层增强 | 3 | /wiki/index-md + /ingest/url 端点 |

##### core/api/routers/wiki_ontology_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| knowledge-engine-ontology | §三 知识引擎（本体） | 837 | 本体引擎 REST API |

##### core/api/routers/workspace_tools.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| tool-ecosystem | §十六 工具生态 | 76 | workspace tools 跑 tool compat |

##### core/apps/agents/discovery.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| a2a-protocol | §十四附 A2A 协议 | 2 | AgentDiscovery 实现/导出 |

##### core/apps/agents/materials_chat.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| rag-retrieval | §四 RAG 检索 | 10 | CRAG + HyDE + RRF 自身 |

##### core/apps/mcp/runtime.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| mcp-protocol | §十四 MCP 协议 | 14 | MCP runtime 消费 finalize_mcp_compat / mark_mcp_connection |

##### core/harness/coordination/swarm_broker.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| orchestration-layer | §二十六 编排层 | 5 | 动态组队 |

##### core/harness/evolution_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| deploy-and-operations | §十 部署与运维 | 3 | self-harness cycle |
| fine-tuning-system | §十七 微调系统 | 2 | nightly LoRA trigger |

##### core/harness/execution/pipeline_engine.py

| Domain | Section | Caps | Reason |
|--------|---------|:---:|--------|
| harness-execution-engine | §一 Harness 执行引擎 | 873 | 自身消费 PipelineStageConfig + StageRunner |
| moa-multi-model-reasoning | §三十 MoA 多模型推理 | 5 | _run_moa 路由模式 |
| model-infrastructure | §九 模型基础设施 | 7 | Pipeline 阶段模型选择 |
| memory-subsystem | §二 记忆子系统 | 59 | _crystallize_skill → save_task_skill |
| arena-and-scheduling | §二十 Arena & 调度 | 6 | Pipeline routing_mode dispatch |
| management-and-quality | §二十五 管理 & 质量 | 119 | Pipeline 质量评分 |
| orchestration-layer | §二十六 编排层 | 5 | Pipeline → Swarm/Debate/Roundtable/MoA dispatch |
| agent-system | §五 Agent 系统 | 338 | Pipeline 调度 Agent |
| observability | §八 可观测性 | 23 | Pipeline trace 事件 |
| extension-and-learning | §十一 扩展

…

_(节选；全文见权威源)_


### 3.4 交付边界摘要（Pi）

厂外默认 **Pi-only**；企业厚度为可选 **Pi + aiPlat 回连**。正文节选见 §3.0.10；技术混合阶梯见 [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md)。接线以 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) 为准；完整能力表见总白皮书第 3 章。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`product-capability`*
