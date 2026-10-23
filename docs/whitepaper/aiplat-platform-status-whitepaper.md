---
title: "aiPlat 平台现状白皮书"
type: platform-status-whitepaper
authority: derived-from-capabilities
status: generated
generated_at: "2026-10-23T10:47:44Z"
source: AIPLAT_CAPABILITIES.md
source_sha256: "d5282dffed22016eb78ebe29f746ecf9f3e1b2ca7e383bba49d3b7cdce13e103"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
total_capabilities: 2348
capabilities_version: "30.12"
capabilities_last_updated: "2026-10-22"
language: zh-CN
packaging: executive-digest
---

<!-- whitepaper_stamp source_sha256=d5282dffed22016eb78ebe29f746ecf9f3e1b2ca7e383bba49d3b7cdce13e103 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 total_capabilities=2348 -->

# aiPlat 平台现状白皮书

> **本文是可再生成的平台现状说明书（可读包装），不是第二真相源。**  
> 能力清单唯一权威：仓库根目录 [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)  
> 机器登记：[`aiPlat-core/core/capability_registry.yaml`](../../aiPlat-core/core/capability_registry.yaml)  
> 重新生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_platform_whitepaper.py`  
> 新鲜度校验：`python3 scripts/generate_platform_whitepaper.py --check`

## 0. 阅读约定与权威模型

| 问题 | 以谁为准 |
|------|----------|
| 平台有哪些能力、是否已接线 | **AIPLAT_CAPABILITIES.md**（完整路径表）；本文第 3 章仅为**摘要索引** |
| 架构分层与依赖方向 | [`docs/architecture/overview.md`](../architecture/overview.md) · 技术分卷 |
| 自主性定级（L5 等） | [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md) + `assessment-scores.json` |
| 对标 / 差异化 | 研究主报告 + [`architecture/comparison.md`](../architecture/comparison.md) |
| 五维白皮书体系 | [`WHITEPAPER_SYSTEM.md`](./WHITEPAPER_SYSTEM.md) |
| 设计目标 vs 现状 | 代码与 CAPABILITIES；冲突时以代码为准 |

**怎么读本文**

1. §1 平台定位 → 它是什么、分层与交付边界  
2. §2 统计与评级戳 → 规模与外部评估入口  
3. §3 能力全景摘要 → 按子系统看覆盖，**不要**指望在这里读源码路径  
4. 需要逐项证据 / `文件:行号` → 打开 CAPABILITIES.md  

**生成元数据**

| 字段 | 值 |
|------|-----|
| 生成时间 (UTC) | `2026-10-23T10:47:44Z` |
| CAPABILITIES SHA-256 | `d5282dffed22016eb78ebe29f746ecf9f3e1b2ca7e383bba49d3b7cdce13e103` |
| assessment-scores SHA-256 | `96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687` |
| CAPABILITIES version | `30.12` |
| CAPABILITIES last_updated | `2026-10-22` |
| frontmatter total_capabilities | `2348` |
| CAPABILITIES 内 ✅ 计数 | 2362 |
| CAPABILITIES 内 ⚠️ 计数 | 24 |
| 能力表行（估） | 2357 |
| 包装模式 | executive-digest（不含完整能力路径表） |

## 1. 平台定位（现状摘要）

aiPlat 是企业级 AI **操作系统式平台**：以执行内核（Harness）调度任务，叠加记忆、知识、编排、治理与可观测——目标是「可交付、可审计、可演进」，而不是「又一个聊天 Agent」。

用业务语言概括：aiPlat 把「能跑 Agent」扩展成「能交付、能治理、能积累知识」的平台。

当前能力登记总量约 **2348** 项（✅≈2362 · ⚠️≈24，以 CAPABILITIES 扫描为准）。对外论证时不必通读路径表，可按下面五块理解：

1. **执行与编排**：多阶段流水线、ReAct 循环、多 Agent 协作——把任务跑完，而不是只聊一轮。
2. **记忆与知识**：会话记忆 + 企业知识/本体/RAG——回答有出处、可跨会话。
3. **技能与工具**：Skill / Tool / MCP / A2A——能力可扩展，且走统一调用边界。
4. **治理与安全**：策略门、审批、审计、多租户——企业可上线的前提。
5. **质量与运维**：评测、可观测、部署灰度、管理端诊断——可运营、可验收。

薄交付（Pi）只带走快照级运行时，**不等于**上述全平台能力；边界见技术分卷与 `docs/architecture/plans/pi-thin-runtime.md`。


**仓库分层（依赖单向：应用 → 平台 → 核心 → 基础设施）**

| 层 | 仓库 | 读者可记的职责 |
|----|------|----------------|
| L3 应用接入 | management / app | 人用的界面与接入通道 |
| L2 平台服务 | platform | 网关、鉴权、Builder、业务 API |
| L1 AI 核心 | core | 流水线、Agent 循环、记忆/知识、统一调用边界 |
| L0 基础设施 | infra | 模型目录与运行时依赖（无业务知识） |

架构全景：见 [`docs/architecture/overview.md`](../architecture/overview.md)  
自主性评估（L 级定级，**不等于**能力全表）：见 [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md)

**交付边界（一句话）**

- **厂内**：完整治理与知识能力在平台侧。  
- **厂外 Pi 薄 Runtime**：可跑快照技能包，能力厚度远小于全平台；不足时用厚运行时或回连。详见 `pi-thin-runtime` 文档。

## 2. 能力统计总表

以下表格从 `AIPLAT_CAPABILITIES.md`「统计」节抽取（生成时原文复制）：

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|
| Harness 执行引擎 | 329 | 1 | 330 |
| 记忆子系统 | 93 | 0 | 93 |
| 知识引擎（本体） | 375 | 9 | 384 |
| RAG 检索 | 57 | 0 | 57 |
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
| 平台治理 | 126 | 0 | 126 |
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
| **总计** | **2338** | **10** | **2348** |

## 2.5 对标、评级与五维白皮书体系

> **完整性要求**：仅有能力清单不足以对外论证。对标报告、自主性/工程成熟度评分、安全合规材料必须进入白皮书**体系目录**；本生成章只做**索引 + 评分戳**，正文仍以各权威源为准（避免第二真相源）。

体系说明：[`WHITEPAPER_SYSTEM.md`](./WHITEPAPER_SYSTEM.md)

### 2.5.1 权威评分戳（自动摘录）

> 评分戳来源：[`assessment-scores.json`](../framework/assessment-scores.json)（generated_at=`2026-07-08T09:51:09` · spec=`1.0.0`）。改分请改 `assessment-spec.yaml` 后重算，勿手改本表。

| 框架 | 综合结果 | 说明 |
|------|----------|------|
| 8轴自主性成熟度 | **L5** (5.0) | sum(axis_level*weight)/sum(weight) — normalized |
| 工程落地评估(58项) | **100.0%** | (yes*1 + partial*0.5)/total * 100 |
| 三层企业评估(~110项) | _(见 JSON tiers)_ | per-tier mean of manual scores (all source=manual) |


完整评估叙述：[`../framework/aiplat-complete-assessment.md`](../framework/aiplat-complete-assessment.md) · 自主性 ADR：[`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md)

### 2.5.2 对标与对比入口（勿读 archive 当现行）

| 文档 | 用途 |
|------|------|
| [`../research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) | **主对标**：Hermes / Claude Code / OpenClaw / DeepSeek Harness / OpenAI Codex（2026-10；见 `research/README.md`） |
| [`../architecture/comparison.md`](../architecture/comparison.md) | 六平台 18 维架构对比入口 |
| [`../strategy/comparison-vs-vendors.md`](../strategy/comparison-vs-vendors.md) | 厂商/策略对比 |
| [`../framework/hermes-comparison.md`](../framework/hermes-comparison.md) | Hermes 专项 |
| [`../research/对标吸收与架构纯度评估.md`](../research/对标吸收与架构纯度评估.md) | 吸收核验 |
| [`../archive/`](../archive/) | 历史对比（只读，已被主报告取代） |

### 2.5.3 五维白皮书 ↔ 仓库映射（摘要）

| 维度 | 核心问题 | 分卷（生成） | 权威源 |
|------|----------|--------------|--------|
| 技术 | 为什么这样设计 | [`volumes/01-tech-architecture.md`](./volumes/01-tech-architecture.md) | overview + comparison + 本册第 1–3 章 |
| 产品 | 能解决什么问题 | [`volumes/02-product-capability.md`](./volumes/02-product-capability.md) | CAPABILITIES + manuals + Pi 边界 |
| 商业 | 投资回报如何 | [`volumes/03-commercial-value.md`](./volumes/03-commercial-value.md) | 价值模型 + ROADMAP + 内部示意（真实案例走 cases/ 授权） |
| 生态 | 如何参与协作 | [`volumes/04-ecosystem-integration.md`](./volumes/04-ecosystem-integration.md) | 技术伙伴分层 + MCP/A2A/Pi（商务条款以盖章版为准） |
| 治理 | 如何可信可控 | [`volumes/05-security-governance.md`](./volumes/05-security-governance.md) | security + Gate + L 级评估 |

分卷清单：[`whitepaper-suite.yaml`](./whitepaper-suite.yaml) · 重生成：`python3 scripts/generate_whitepaper_volumes.py`

## 3. 能力全景摘要（非完整路径表）

> **请勿在本章查找 `*.py` 清单。** 完整能力表、接线状态与位置字段只在  
> [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)。  
> 本章由生成器按 CAPABILITIES 章节**自动汇总计数**，改能力请改源文件后 `sync_whitepapers`。

### 3.1 子系统目录

1. 一、Harness 执行引擎
2. 二、记忆子系统
3. 三、知识引擎（本体）
4. 四、RAG 检索
5. 四附、知识基础设施（Knowledge）
6. 五、Agent 系统
7. 六、Skill 系统
8. 七、安全与治理
9. 八、可观测性
10. 九、模型基础设施
11. 十、部署与运维
12. 十一、扩展与学习
13. 十二、Gate 系统
14. 十三、评估系统
15. 十四、MCP 协议
16. 十四附、A2A 协议 (Agent-to-Agent)
17. 十五、文档智能
18. 十六、工具生态
19. 十七、微调系统
20. 十八、部署与灰度
21. 十九、运行时干预
22. 二十、Arena & 调度
23. 二十一、平台治理
24. 二十二、Infra 基础设施
25. 二十三、核心API统一入口
26. 二十四、编排系统
27. 二十五、管理 & 质量
28. 二十六、编排层 (Orchestration)
29. 二十七、L6 自主能力 (Phase 39-41)
30. 二十八、记忆系统白盒化 (Phase 40 记忆升级)
31. 二十九、记忆运行时过滤 (Phase 40 记忆引擎)
32. 三十、MoA 多模型推理 (Phase 42)
33. 三十一、AI知识层增强 (Phase 42)
34. 三十二、Hermes压缩对标 (Phase 42)
35. 三十三、Scenario Simulation — 多场景沙盒推演 (Palantir 对齐)
36. 三十四、Decision Lineage — 决策血缘 (Palantir 对齐)
37. 三十五、Security 3D — 三维权限 (Palantir 对齐)
38. 三十六、Global Branching — 本体分支管理 (Palantir 对齐)
39. 三十七、EvoX 蜂群协作层 (EvoMap 对齐)
40. 三十八、闭环执行层 (TemplateEngine + OperationRecorder + MCP Ecosystem)
41. 三十九、知识编译与 OKF 导出 (Karpathy LLM Wiki 对齐)
42. 四十、对话→Wiki 自动管线 (CodeAlmanac 对齐)
43. 四十一、Web 工具归并 (Firecrawl 对齐)
44. 四十一、Skill 目录标准化与验收 (文章对齐)
45. 四十一、E2E端到端验证
46. 统计

### 3.2 各子系统覆盖度（摘要表）

<!-- BEGIN_GENERATED_FROM_AIPLAT_CAPABILITIES -->

| 子系统 / 章节 | ✅ | ⚠️ | 一句话（若有） |
|---------------|---:|---:|----------------|
| 一、Harness 执行引擎 | 329 | 1 | — |
| 二、记忆子系统 | 93 | 1 | — |
| 三、知识引擎（本体） | 376 | 9 | — |
| 四、RAG 检索 | 59 | 1 | — |
| 四附、知识基础设施（Knowledge） | 30 | 0 | — |
| 五、Agent 系统 | 168 | 0 | — |
| 六、Skill 系统 | 172 | 2 | — |
| 七、安全与治理 | 90 | 0 | — |
| 八、可观测性 | 43 | 0 | — |
| 九、模型基础设施 | 46 | 0 | — |
| 十、部署与运维 | 23 | 0 | — |
| 十一、扩展与学习 | 136 | 1 | — |
| 十二、Gate 系统 | 174 | 0 | — |
| 十三、评估系统 | 27 | 0 | — |
| 十四、MCP 协议 | 10 | 0 | — |
| 十四附、A2A 协议 (Agent-to-Agent) | 9 | 0 | — |
| 十五、文档智能 | 27 | 0 | — |
| 十六、工具生态 | 74 | 0 | — |
| 十七、微调系统 | 14 | 0 | — |
| 十八、部署与灰度 | 7 | 0 | — |
| 十九、运行时干预 | 44 | 0 | — |
| 二十、Arena & 调度 | 7 | 0 | — |
| 二十一、平台治理 | 129 | 5 | — |
| 二十二、Infra 基础设施 | 16 | 0 | — |
| 二十三、核心API统一入口 | 7 | 1 | — |
| 二十四、编排系统 | 10 | 0 | — |
| 二十五、管理 & 质量 | 107 | 0 | — |
| 二十六、编排层 (Orchestration) | 22 | 0 | — |
| 二十七、L6 自主能力 (Phase 39-41) | 8 | 0 | — |
| 二十八、记忆系统白盒化 (Phase 40 记忆升级) | 7 | 1 | — |
| 二十九、记忆运行时过滤 (Phase 40 记忆引擎) | 2 | 0 | — |
| 三十、MoA 多模型推理 (Phase 42) | 5 | 0 | — |
| 三十一、AI知识层增强 (Phase 42) | 3 | 0 | — |
| 三十二、Hermes压缩对标 (Phase 42) | 3 | 0 | — |
| 三十三、Scenario Simulation — 多场景沙盒推演 (Palantir 对齐) | 5 | 0 | — |
| 三十四、Decision Lineage — 决策血缘 (Palantir 对齐) | 6 | 0 | — |
| 三十五、Security 3D — 三维权限 (Palantir 对齐) | 4 | 0 | — |
| 三十六、Global Branching — 本体分支管理 (Palantir 对齐) | 3 | 0 | — |
| 三十七、EvoX 蜂群协作层 (EvoMap 对齐) | 9 | 0 | — |
| 三十八、闭环执行层 (TemplateEngine + OperationRecorder + MCP Ecosystem) | 7 | 0 | — |
| 三十九、知识编译与 OKF 导出 (Karpathy LLM Wiki 对齐) | 8 | 0 | — |
| 四十、对话→Wiki 自动管线 (CodeAlmanac 对齐) | 6 | 0 | — |
| 四十一、Web 工具归并 (Firecrawl 对齐) | 4 | 0 | — |
| 四十一、Skill 目录标准化与验收 (文章对齐) | 7 | 0 | — |
| 四十一、E2E端到端验证 | 18 | 0 | — |

<!-- END_GENERATED_FROM_AIPLAT_CAPABILITIES -->

子系统共 **46** 个章节索引；逐项能力说明与代码位置 → [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)。

## 4. 如何验证本文未过期

```bash
# 与当前 CAPABILITIES 比对（不一致则 exit 1）
python3 scripts/generate_platform_whitepaper.py --check

# 重新生成
python3 scripts/generate_platform_whitepaper.py

# 能力登记一致性（既有门禁）
# bash scripts/architecture_guard.sh   # 含 doc-sync 等
```

## 5. 相关文档索引

| 文档 | 用途 |
|------|------|
| [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) | 唯一能力清单（编辑入口） |
| [`capability_registry.yaml`](../../aiPlat-core/core/capability_registry.yaml) | 机器可读 provides |
| [`docs/architecture/overview.md`](../architecture/overview.md) | 架构全景 |
| [`docs/matrix/capability-impact-matrix.md`](../matrix/capability-impact-matrix.md) | 变更影响矩阵 |
| [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) | 文档治理宪法 |
| [`WHITEPAPER_SYSTEM.md`](./WHITEPAPER_SYSTEM.md) | 五维白皮书体系 |
| [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性定级评估 |
| [`../framework/assessment-scores.json`](../framework/assessment-scores.json) | 评估分数机器源 |
| [`../research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) | 主对标报告 |
| [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) | 商业/路线图 |
| [`docs/archive/AIPLAT_WHITEPAPER.md`](../archive/AIPLAT_WHITEPAPER.md) | 旧叙事稿（归档，非现状权威） |

---

*生成器：`scripts/generate_platform_whitepaper.py`*
