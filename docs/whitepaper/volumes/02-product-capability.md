---
title: "aiPlat 产品能力白皮书"
volume_id: product-capability
type: whitepaper-volume
status: generated
generated_at: "2026-10-22T15:32:42Z"
audience: "产品负责人、技术评估者、客户技术链"
core_question: "能解决什么问题？能力边界在哪？"
priority: P1
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30"
caps_sha256: "0537e31c0481bad338ebe03c109558d7c4c73d8257082a9fab523542bcdaf4cc"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=product-capability suite_sha256=0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30 caps_sha256=0537e31c0481bad338ebe03c109558d7c4c73d8257082a9fab523542bcdaf4cc scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 产品能力白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `product-capability` |
| 受众 | 产品负责人、技术评估者、客户技术链 |
| 核心问题 | 能解决什么问题？能力边界在哪？ |
| 优先级 | P1 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-22T15:32:42Z` |
| CAPABILITIES sha256 | `0537e31c0481…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

## 1. 本卷论证目标

本卷面向 **产品负责人、技术评估者、客户技术链**，围绕「**能解决什么问题？能力边界在哪？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) | 唯一能力清单 | ✅ |
| [`docs/whitepaper/aiplat-platform-status-whitepaper.md`](../aiplat-platform-status-whitepaper.md) | 可读包装（含完整能力表） | ✅ |
| [`docs/matrix/capability-impact-matrix.md`](../matrix/capability-impact-matrix.md) | 变更影响 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/manuals/getting-started.md`](../manuals/getting-started.md) | 上手路径 | ✅ |
| [`docs/manuals/fde/README.md`](../manuals/fde/README.md) | FDE 交付场景入口 | ✅ |
| [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) | 执行选型（产品/技术评估共用） | ✅ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) | 厂外薄交付边界（Pi） | ✅ |
| [`packages/aiplat-pi-runtime/README.md`](../../packages/aiplat-pi-runtime/README.md) | Pi Package 用户侧说明 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 典型产品场景 → 权威入口（场景切片，非第二清单）

| 场景 | 客户要解决的问题 | 从哪里看能力/怎么做 |
|------|------------------|---------------------|
| **FDE 交付** | 把业务问题做成可签收的 AI 交付 | [`docs/manuals/fde/README.md`](../manuals/fde/README.md) · CAPABILITIES「平台治理 / FDE」 |
| **App 工厂 / Builder** | 从需求到 Agent/应用产物 | 管理端 Builder · [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md)（厂外交付边界） |
| **Workbench** | 开发与调试工作台 | [`docs/manuals/management.md`](../manuals/management.md) · CAPABILITIES「Workbench」 |
| **评测治理** | 评测流程与治理规则 | CAPABILITIES「评测 / Governance」 |
| **ORG 签收** | 组织级签收与现场闭环 | CAPABILITIES「apps/org」· manuals |
| **渠道接入** | 多渠道消息与集成 | CAPABILITIES「Channel」· 应用端 channels |
| **知识 / 本体 / RAG** | 企业知识可检索、可治理 | [`docs/knowledge-system.md`](../knowledge-system.md) · CAPABILITIES「知识引擎 / RAG」 |
| **Agent / Skill 运行** | 多步工具调用与技能执行 | CAPABILITIES「Agent 系统 / Skill 系统」· [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) |
| **治理下执行** | 权限、审批、审计可证明 | 安全与治理分卷 · CAPABILITIES「Gate / 安全与治理」 |
| **薄交付（Pi）** | 用户侧轻量跑快照、不装全栈 | [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) · [`packages/aiplat-pi-runtime/README.md`](../../packages/aiplat-pi-runtime/README.md) |

> 上表只指路。**接线以 [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) 行为为准**；[`docs/manuals/README.md`](../manuals/README.md) 仅提供操作说明，不作为行为契约。

### 3.1 能力统计（摘自 CAPABILITIES）

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|
| Harness 执行引擎 | 329 | 1 | 330 |
| 记忆子系统 | 93 | 0 | 93 |
| 知识引擎（本体） | 375 | 9 | 384 |
| RAG 检索 | 55 | 0 | 55 |
| 知识基础设施 | 30 | 0 | 30 |
| Agent 系统 | 168 | 0 | 168 |
| Skill 系统 | 171 | 0 | 171 |
| 安全与治理 | 90 | 0 | 90 |
| 可观测性 | 43 | 0 | 43 |
| 模型基础设施 | 46 | 0 | 46 |
| 部署与运维 | 23 | 0 | 23 |
| 扩展与学习 | 135 | 0 | 135 |
| Gate 系统 | 174 | 0 | 174 |
| 评估系统 | 27 | 0 | 27 |
| MCP 协议 | 10 | 0 | 10 |
| A2A 协议 | 9 | 0 | 9 |
| 文档智能 | 27 | 0 | 27 |
| 工具生态 | 74 | 0 | 74 |
| 微调系统 | 14 | 0 | 14 |
| 部署与灰度 | 7 | 0 | 7 |
| 运行时干预 | 44 | 0 | 44 |
| Arena & 调度 | 7 | 0 | 7 |
| 平台治理 | 125 | 0 | 125 |
| Infra 基础设施 | 16 | 0 | 16 |
| 核心API统一入口 | 7 | 0 | 7 |
| 编排系统 | 10 | 0 | 10 |
| 管理 & 质量 | 107 | 0 | 107 |
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
| Skill 目录标准化 | 7 | 0 | 7 |
| Web 工具归并 | 4 | 0 | 4 |
| E2E 端到端验证 | 18 | 0 | 18 |
| **总计** | **2335** | **10** | **2345** |

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

操作手册入口：[`manuals/README.md`](README.md) · 合册 [`../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md`](../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) · Org [`../contracts/ORG_L5_RUNBOOK.md`](../contracts/ORG_L5_RUNBOOK.md)。

- [API Reference](api-reference.md) — 完整 API 文档（若仓库内仍保留）
- [自主性评估报告](../framework/aiplat-complete-assessment.md) — 系统能力评估
- [验证协议](../framework/verification-protocol.md) — 独立复现验证

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


### 3.3 交付边界（Pi 薄 Runtime）

### Plan: aiPlat × Pi 薄 Runtime（1C + 2C）

> Living 摘要 · 2026-10-12 · 包：`packages/aiplat-pi-runtime/`  
> **状态**：Phase 0–2 + 工厂/FE/ZIP **已合并 main**（PR [#251](https://github.com/zhuxiangqun/aiPlatform/pull/251)）  
> **Live 门**：✅ `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh`（Ollama `ollama/qwen2.5:3b` — CLI print + SOP + `/aiplat-status` + HTTP `createAgentSession`）

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

接 Pi **不是为了补上下文**：aiPlat 已有 Memory / CRAG / ContextBus。厂内换心须单独 RFC；当前主路径已是 `coding_closed_loop` + sandbox + `sys_file_*`。

##### 上下文 · 压缩 · 学习（作用域 × 治理）

划分标准：**会话内 vs 跨会话**；**是否要权限 / 审计 / 共享 / 持久化 / 回滚**。

| 能力 | 归属 | 说明 |
|------|------|------|
| 会话内窗口管理 / 自动·手动 compaction / 分支摘要 / `transformContext` | **Pi 原生** | 执行自保：不爆窗口；≠ 平台知识沉淀 |
| 项目上下文（AGENTS.md/CLAUDE.md）/ system prompt 组装 | **Pi 原生** | 仓库指令进会话；与 aiPlat ContextBus 来源不同 |
| 上下文选择（Memory / RAG / CRAG / Team Brain） | **aiPlat** | 租户边界 + 策略 |
| 上下文注入包 | **aiPlat 构建，Pi 消费** | 平台决定「给什么」，Pi 决定「怎么进循环」 |
| 跨会话压缩 / 蒸馏 / 持久记忆 | **aiPlat** | 混合桥只投递 `memory/capture`，不搬 MemoryManager |
| 提示 / 知识 / 技能 / 策略层学习 | **aiPlat** | 需持久化、治理、验证、版本与回滚 |
| 会话内即时适应（重试 / ReAct 自纠） | **Pi** | 单次任务内；跨会话学习仍归平台 |
| Pi 扩展生态（magic-context / continual-harness 等） | **可选参考，非默认交付** | 若引入跨会话记忆，治理仍须回 aiPlat；禁止双头管理 |

> **一句话**：会话内上下文与压缩 → Pi；跨会话记忆与学习 → aiPlat；Pi 扩展可补执行侧能力，但共享边界与审计不得旁路平台。

**厂内处置** — 详见 `packages/aiplat-pi-runtime/docs/FACTORY_IN_EXPERIMENT.md`（⓪ 合并关闭）

1. 巩固 Pi-only 交付 + **Pi + aiPlat 混合回连**（企业 DELIVERY SKU）——主产品轴
2. ~~方式四 Workspace Execute Pi 旁路~~ → **已拆除**（`blank_not_proven`）
3. 方式一/二/三：**不实现**，除非 RFC 重做 ① 空白验证 + 真实 caller
4. 离线 `coding_exec` / RPC 探针仅归档复现，**不得**标 CAPABILITIES「厂内已接线」

#### 结论（Phase 0）

| 假设 | 文档结论 | 离线检查 | 在线 LLM 冒烟 |
|------|----------|:--------:|:-------------:|
| 包内 `skills/` 自动发现 | **成立**（Pi Skills / Packages 文档） | 结构 ✅ | ✅ live_smoke |
| `before_agent_start` 注入 systemPrompt | **成立**（可返回 `systemPrompt` / `forceSystemPrompt`） | 代码含事件 ✅ | ✅ SOP marker |
| `registerCommand` / `registerTool` | **成立** | 代码含 API ✅ | ✅ `/aiplat-status` |
| `registerSkill` API | **不存在** → **方案 A**（导出复制 skills/） | N/A | N/A |

Skills 策略锁定 **方案 A**：`scripts/export_pi_bundle.py` 把工厂 skills 复制进导出包；扩展只注册斜杠命令与 SOP 注入。

#### 职责（厂外薄 Runtime）

| | aiPlat | Pi Runtime（厂外） |
|--|--------|-------------------|
| 工厂 / 合规 / 工作区编辑 | 是 | 否 |
| 用户侧对话执行（薄快照） | 可全栈 | **已交付路径** |
| PolicyGate / Memory / SECI / 审批裁决 | 是 | **不搬**（混合只回连 / 等待） |
| 会话内 compaction / 窗口管理 | 非职责（不侵入循环） | **Pi 原生** |
| 跨会话记忆 / 蒸馏 / 自学治理 | **平台层** | 可选 capture 投递；扩展生态非默认 |
| 扩展 `aiplat-app` | — | 胶水：SOP、斜杠、handler、企业桥；**非** Agent 大脑搬家 |

#### 路径

1. `packages/aiplat-pi-runtime` — Pi Package（扩展 + fixture skills）
2. `scripts/export_pi_bundle.py` — 从 `~/.aiplat/apps/{id}/current` 导出
3. Phase 1b handler 协议：JSON stdin/stdout（见 `fixtures/handler_echo.py`）
4. Phase 2：薄 HTTP — `packages/aiplat-pi-runtime/bin/aiplat-http.mjs`
   - `GET /health` · `POST /v1/chat` · `POST /v1/skills/:name`
   - 有 `handler.py` 时走确定性桥（硬失败）；否则注入 SKILL.md 再对话
   - stub：`AIPLAT_HTTP_STUB=1`；真 Agent：`AIPLAT_PI_MODEL=provider/id` + `createAgentSession`
5. 工厂一键导出：`builder/pi_bundle_export.py`；`deploy-to-app` 响应 `pi_bundle`；`POST …/export-pi-bundle`；`GET …/export-pi-bundle.zip`；管理端「导出 / 下载 ZIP」

#### 命令

```bash
python3 packages/aiplat-pi-runtime/scripts/phase0_offline_check.py
bash packages/aiplat-pi-runtime/scripts/http_smoke.sh
### Full live gate (Ollama default; needs :11434 + model pulled)
AIPLAT_PI_MODEL=ollama/qwen2.5:3b bash packages/aiplat-pi-runtime/scripts/live_smoke.sh

python3 scripts/export_pi_bundle.py \
  --app-home packages/aiplat-pi-runtime/fixtures/sample-app \
  --out dist/aiplat-app-sample
AIPLAT_APP_HOME=$PWD/dist/aiplat-app-sample \
  pi -e dist/aiplat-app-sample --model ollama/qwen2.5:3b
### /aiplat-status  /skill-greet  /skill-demo_skill  /aiplat-sop-check

### Real HTTP Agent (Ollama / OpenAI-compatible)
### AIPLAT_PI_MODEL=ollama/qwen2.5:3b AIPLAT_APP_HOME=dist/aiplat-app-sample \
### node packages/aiplat-pi-runtime/bin/aiplat-http.mjs
### Cloud: set AIPLAT_PI_BASE_URL + AIPLAT_PI_API_KEY, or pi /login + provider/id
```

#### handler 协议

```json
{"skill":"demo_skill","params":{}}
→ stdout {"ok":true,"result":{...}} exit 0
```

`fixtures/handler_runner.py <handler.py>` 包装现有 `async def execute(params)`。


> 完整能力表见总白皮书第 3 章或直接打开 [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`product-capability`*
