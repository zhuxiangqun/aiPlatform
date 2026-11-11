---
title: "aiPlat 产品能力白皮书"
volume_id: product-capability
type: whitepaper-volume
status: generated
generated_at: "2026-11-11T12:57:01Z"
audience: "产品负责人、技术评估者、客户技术链"
core_question: "能解决什么问题？能力边界在哪？"
priority: P1
source_status: ready
suite: docs/reference/explanatory/whitepaper-suite.yaml
suite_sha256: "8ef15832e16896a7cc72bb8e2dbbbc6b6753e9727a98e352bd83cb4ed8df25c6"
caps_sha256: "3674a4361be7f38185ecb4dae9582c08a189d51ca84954fcd16454c185f71946"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=product-capability suite_sha256=8ef15832e16896a7cc72bb8e2dbbbc6b6753e9727a98e352bd83cb4ed8df25c6 caps_sha256=3674a4361be7f38185ecb4dae9582c08a189d51ca84954fcd16454c185f71946 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

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
| 生成时间 (UTC) | `2026-11-11T12:57:01Z` |
| CAPABILITIES sha256 | `3674a4361be7…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

## 1. 本卷论证目标

本卷面向 **产品负责人、技术评估者、客户技术链**，围绕「**能解决什么问题？能力边界在哪？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) | 唯一能力清单 | ✅ |
| [`docs/whitepaper/aiplat-platform-status-whitepaper.md`](../aiplat-platform-status-whitepaper.md) | 可读包装（含完整能力表） | ❌ |
| [`docs/reference/matrix/capability-impact-matrix.md`](../../../docs/reference/matrix/capability-impact-matrix.md) | 变更影响 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/manuals/getting-started.md`](../../../docs/guides/getting-started.md) | 上手路径 | ❌ |
| [`docs/manuals/fde/README.md`](../../../docs/guides/fde/README.md) | FDE 交付场景入口 | ❌ |
| [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md) | 执行选型（产品/技术评估共用） | ✅ |
| [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | 厂外薄交付边界（Pi） | ✅ |
| [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | Pi Package 用户侧说明 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 典型产品场景 → 权威入口（场景切片，非第二清单）

| 场景 | 客户要解决的问题 | 从哪里看能力/怎么做 |
|------|------------------|---------------------|
| **FDE 交付** | 把业务问题做成可签收的 AI 交付 | [`docs/manuals/fde/README.md`](../../../docs/guides/fde/README.md) · CAPABILITIES「平台治理 / FDE」 |
| **App 工厂 / Builder** | 从需求到 Agent/应用产物 | 管理端 Builder · [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md)（厂外交付边界） |
| **Workbench** | 开发与调试工作台 | [`docs/manuals/getting-started.md`](../../../docs/guides/getting-started.md) · CAPABILITIES「Workbench」 |
| **评测治理** | 评测流程与治理规则 | CAPABILITIES「评测 / Governance」 |
| **ORG 签收** | 组织级签收与现场闭环 | CAPABILITIES「apps/org」· manuals |
| **渠道接入** | 多渠道消息与集成 | CAPABILITIES「Channel」· 应用端 channels |
| **知识 / 本体 / RAG** | 企业知识可检索、可治理 | [`docs/manuals/ontology.md`](../../../docs/guides/ontology.md) · CAPABILITIES「知识引擎 / RAG」 |
| **Agent / Skill 运行** | 多步工具调用与技能执行 | CAPABILITIES「Agent 系统 / Skill 系统」· [`docs/architecture/execution-decision-matrix.md`](../../../docs/architecture/execution-decision-matrix.md) |
| **治理下执行** | 权限、审批、审计可证明 | 安全与治理分卷 · CAPABILITIES「Gate / 安全与治理」 |
| **薄交付（Pi）** | 用户侧轻量跑快照、不装全栈 | [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) · [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) |

> 上表只指路。**接线以 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) 行为为准**；[`docs/manuals/getting-started.md`](../../../docs/guides/getting-started.md) 仅提供操作说明，不作为行为契约。

### 3.1 能力统计（摘自 CAPABILITIES）

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|
| Harness 执行引擎 | 577 | 1 | 578 |
| 记忆子系统 | 93 | 0 | 93 |
| 知识引擎（本体） | 392 | 9 | 401 |
| RAG 检索 | 58 | 0 | 58 |
| 知识基础设施 | 30 | 0 | 30 |
| Agent 系统 | 315 | 0 | 315 |
| Skill 系统 | 171 | 0 | 171 |
| 安全与治理 | 92 | 0 | 92 |
| 可观测性 | 43 | 0 | 43 |
| 模型基础设施 | 46 | 0 | 46 |
| 部署与运维 | 23 | 0 | 23 |
| 扩展与学习 | 174 | 0 | 174 |
| Gate 系统 | 177 | 0 | 177 |
| 评估系统 | 575 | 0 | 575 |
| MCP 协议 | 10 | 0 | 10 |
| A2A 协议 | 9 | 0 | 9 |
| 文档智能 | 27 | 0 | 27 |
| 工具生态 | 74 | 0 | 74 |
| 微调系统 | 14 | 0 | 14 |
| 部署与灰度 | 7 | 0 | 7 |
| 运行时干预 | 44 | 0 | 44 |
| Arena & 调度 | 7 | 0 | 7 |
| 平台治理 | 149 | 0 | 149 |
| Infra 基础设施 | 16 | 0 | 16 |
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
| Skill 目录标准化 | 7 | 0 | 7 |
| Web 工具归并 | 4 | 0 | 4 |
| E2E 端到端验证 | 18 | 0 | 18 |
| **总计** | **3375** | **10** | **3385** |

### 3.2 上手路径（节选）

_(存在性检查失败：文件缺失 `docs/manuals/getting-started.md`)_


### 3.3 交付边界（Pi 薄 Runtime）

厂外默认 **Pi-only**（薄 Runtime 跑工厂产物）；企业厚度为可选 **Pi + aiPlat 回连**，**不等于**五产品目标方案中的完整 Enterprise Runtime，也不等于在用户机默认安装全栈。

| 权威源 | 读什么 |
|--------|--------|
| [`docs/architecture/plans/pi-thin-runtime.md`](../../../docs/architecture/plans/pi-thin-runtime.md) | 产品定位、轴 A/B、Thin≠Enterprise |
| [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md) | 包入口、Pi-only / 企业回连用法 |
| [`packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`](../../../packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md) | 企业混合阶梯（技术） |

> 本卷**不粘贴**上述 living 正文。接线以 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md) 为准；完整能力表见总白皮书第 3 章。

## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/reference/explanatory/WHITEPAPER_SYSTEM.md`](../../../docs/reference/explanatory/WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`product-capability`*
