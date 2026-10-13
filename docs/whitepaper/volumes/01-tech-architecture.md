---
title: "aiPlat 技术架构白皮书"
volume_id: tech-architecture
type: whitepaper-volume
status: generated
generated_at: "2026-10-13T03:53:28Z"
audience: "CTO、架构师、平台工程师"
core_question: "为什么这样设计？边界与权衡是什么？"
priority: P0
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30"
caps_sha256: "e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=tech-architecture suite_sha256=0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30 caps_sha256=e2e1936484e9ca34a1fedaa4193db677b76758c50291c870feca845ce034fc94 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 技术架构白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `tech-architecture` |
| 受众 | CTO、架构师、平台工程师 |
| 核心问题 | 为什么这样设计？边界与权衡是什么？ |
| 优先级 | P0 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-13T03:53:28Z` |
| CAPABILITIES sha256 | `e2e1936484e9…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

## 1. 本卷论证目标

本卷面向 **CTO、架构师、平台工程师**，围绕「**为什么这样设计？边界与权衡是什么？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/whitepaper/aiplat-platform-status-whitepaper.md`](../aiplat-platform-status-whitepaper.md) | 现状总册（能力全收录，由 CAPABILITIES 生成） | ✅ |
| [`docs/architecture/overview.md`](../architecture/overview.md) | 架构全景唯一入口 | ✅ |
| [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) | 执行选型矩阵 | ✅ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) | 厂外薄 Runtime 决策边界 | ✅ |
| [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) | 文档权威模型 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/architecture/comparison.md`](../architecture/comparison.md) | 架构层对比 | ✅ |
| [`docs/architecture/plans/comparison.md`](../architecture/plans/comparison.md) | 规划期对比 | ✅ |
| [`CLAUDE.md`](../../CLAUDE.md) | 执行规约 / 层边界 | ✅ |
| [`docs/manuals/deployment.md`](../manuals/deployment.md) | 部署与运维视图 | ✅ |
| [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) | 灾备 / RPO·RTO | ✅ |
| [`docs/standards/规范-性能.md`](../standards/规范-性能.md) | 性能预算与扩展约束 | ✅ |
| [`docs/architecture/slo.md`](../architecture/slo.md) | SLI/SLO / 误差预算 | ✅ |
| [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) | 可观测性架构 | ✅ |
| [`docs/knowledge-system.md`](../knowledge-system.md) | 数据 / 知识存储路径 | ✅ |
| [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | 知识库架构 | ✅ |
| [`docs/security/security-architecture.md`](../security/security-architecture.md) | 安全嵌入（技术视角交叉） | ✅ |
| [`docs/manuals/testing.md`](../manuals/testing.md) | 测试金字塔与策略 | ✅ |
| [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | 执行质量门禁 | ✅ |
| [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) | 架构演进路线 | ✅ |
| [`docs/manuals/getting-started.md`](../manuals/getting-started.md) | 开发上手 | ✅ |
| [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | 应用模块目录规范 | ✅ |
| [`docs/mcp/index.md`](../mcp/index.md) | 集成 / MCP 入口 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 关键设计决策索引

本卷不重抄 ADR 全文，以索引方式消解散落问题。设计决策分散在以下权威源：

| 决策域 | 权威源 |
|--------|--------|
| 平台总览与边界 | [`docs/architecture/overview.md`](../architecture/overview.md) |
| 执行决策矩阵 | [`docs/architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) |
| Pi 薄运行时 | [`docs/architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) |
| 文档体系与 ADR 分布 | [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) |

索引维护责任与更新触发条件见 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)「ADR 索引维护」节。

> 索引只指向权威源，不复制 ADR 正文。修改 overview / execution-decision-matrix / pi-thin-runtime / DOCUMENT_SYSTEM 任一文件时，必须同步本索引。

### 3.1 架构全景（设计叙事）

aiPlat 按**四层**组织，依赖严格单向 `应用接入 → 平台服务 → AI 核心引擎 → 基础设施`：

1. **应用接入**：管理端 / 应用端 / 频道与会话——用户看得见的入口。
2. **平台服务**：网关、鉴权、限流、Builder、知识库等平台能力——不实现 Agent 内核。
3. **AI 核心引擎（Harness）**：像操作系统。负责任务流水线、ReAct 循环、记忆与知识、以及唯一的外部交互边界（syscall）。业务 Agent 像「应用」，共享同一套执行内核。
4. **基础设施**：模型目录、LLM/嵌入客户端、存储与网络——**零业务知识**。

**一次提问怎么跑通**：请求进入 API → 选中 Agent → ReAct（推理 / 调工具或技能 / 观察）→ 模型与工具只能经 syscall 出去，并经过策略门禁（PolicyGate 等）。

**多阶段交付怎么跑通**：Pipeline 按配置阶段推进，可在人机审批点暂停与恢复，再进入下一阶段；这是相对「单会话助手」的关键差异。

**十条设计铁律（摘要）**：Harness=OS 且不懂业务名；Syscall 是唯一出口；四层记忆；CRAG 检索回退；模型目录集中在 infra；协作模式由配置驱动；文档/能力统计与 CI 同步；Spec 生命周期；企业多租户与治理门禁。

需要图示、子系统地图或代码入口时，打开 [`docs/architecture/overview.md`](../architecture/overview.md) （本卷刻意不粘贴路径清单，便于阅读）。

### 3.2 多系统对标（摘要）

本卷**主体是架构设计与边界**；对标只作定位参照，避免喧宾夺主。
完整 18 维表、证据与可借鉴清单见权威源（勿在卷内手抄第二份）。

- 架构对比入口：[`docs/architecture/comparison.md`](../architecture/comparison.md)
- 深度主报告：[`docs/research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md)
- 证据底稿：[`docs/research/对标底稿-2026-10-五家.md`](../research/对标底稿-2026-10-五家.md)

#### 六平台一句话定位

| 系统 | 定位（一句话） |
|------|----------------|
| **aiPlat** | 企业 AI 操作系统：交付流水线 + 治理 + 知识本体 |
| **Hermes Agent** | 自学习个人/团队 Agent，多通道 + 多终端后端 |
| **Claude Code** | 终端/IDE agentic coding（引擎闭源） |
| **OpenClaw** | 多端个人助手（Gateway + 广通道） |
| **DeepSeek Harness** | 高纯度插件化 agent harness |
| **OpenAI Codex** | 可嵌入 coding 运行时（app-server + OS 沙箱） |

#### 加权总分（论证用，非商务承诺）

| 维 | aiPlat | Hermes | Claude Code | OpenClaw | DSH | Codex |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **加权总分** | **92** | **70** | **56** | **60** | **62** | **61** |


> 18 维拆解与可借鉴清单不在本卷展开。尽调请打开 comparison.md / 研究主报告。

### 3.3 工程落地视图索引（部署 / 性能 / 可观测 / 数据 / 测试 …）

工程落地以**索引指路**为主，本卷不粘贴部署手册/测试手册/源码节选，避免变成「文件路径合集」。CTO/架构师尽调时按下表进入权威源。

| 工程维度 | 读者要回答的问题 | 权威源（优先） | CAPABILITIES / 姊妹卷 |
|----------|------------------|----------------|----------------------|
| **部署与运维** | 生产怎么布？环境/灾备/灰度？ | [`docs/manuals/deployment.md`](../manuals/deployment.md) · [`docs/architecture/plans/disaster-recovery-plan.md`](../architecture/plans/disaster-recovery-plan.md) · `deploy/helm/aiplat/` | CAPABILITIES「部署与运维 / 部署与灰度」 |
| **性能与扩展** | QPS/P95/容量/扩展策略？ | [`docs/standards/规范-性能.md`](../standards/规范-性能.md) · [`docs/architecture/slo.md`](../architecture/slo.md) · `scripts/benchmark_all.sh` | CAPABILITIES「部署与运维」基准条目 |
| **可观测性** | 日志/指标/追踪怎么采与告警？ | [`docs/architecture/plans/observability-eval-repair-architecture.md`](../architecture/plans/observability-eval-repair-architecture.md) · [`docs/standards/规范-core-run_id-trace_id-request_id.md`](../standards/规范-core-run_id-trace_id-request_id.md) | CAPABILITIES「可观测性」· 安全卷可交叉 |
| **数据架构** | 存什么、隔离、备份？ | [`docs/knowledge-system.md`](../knowledge-system.md) · [`docs/architecture/knowledge-base-architecture.md`](../architecture/knowledge-base-architecture.md) | CAPABILITIES「知识引擎」· 灾备计划（备份） |
| **安全嵌入视图** | Gate/信任边界如何嵌进运行时？ | [`docs/security/security-architecture.md`](../security/security-architecture.md) | 分卷 05 · CAPABILITIES「安全与治理 / Gate」 |
| **测试与验证** | 金字塔 / CI / 质量门？ | [`docs/manuals/testing.md`](../manuals/testing.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) · `.github/workflows/` | CAPABILITIES「管理 & 质量」 |
| **技术风险与演进** | 技术债、依赖风险、路线？ | [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) · [`docs/research/architecture-evolution-roadmap.md`](../research/architecture-evolution-roadmap.md) · [`CLAUDE.md`](../../CLAUDE.md) §16 | 商业卷 ROADMAP 节选（非财务） |
| **开发视图** | 代码组织、模块边界、上手？ | [`CLAUDE.md`](../../CLAUDE.md) · [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) · [`docs/manuals/getting-started.md`](../manuals/getting-started.md) · [`docs/architecture/plans/app-module-layout.md`](../architecture/plans/app-module-layout.md) | — |
| **集成架构** | MCP/A2A/外部适配？ | [`docs/mcp/index.md`](../mcp/index.md) · [`docs/policy/mcp-stdio-prod-allowlist.md`](../policy/mcp-stdio-prod-allowlist.md) | 分卷 04 · CAPABILITIES「MCP / A2A」 |
| **质量属性 / SLA·SLO** | 可用性目标与误差预算？ | [`docs/architecture/slo.md`](../architecture/slo.md) · [`docs/architecture/execution-quality-gates.md`](../architecture/execution-quality-gates.md) | CAPABILITIES「管理 & 质量」 |

> **阅读约定**：索引保证「只读本卷也知道去哪尽调」。性能数字以 SLO / `benchmark_all.sh` 为准，勿在卷内编造 QPS。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`tech-architecture`*
