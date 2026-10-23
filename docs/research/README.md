# research/ — aiPlat 对标研究与改进规划

本目录集中存放 aiPlat 与 **Hermes Agent / Claude Code / OpenClaw / DeepSeek Harness / OpenAI Codex** 五家对标的研究与改进文档，供随时查询。

**文档系统现状基线（2026-10）**：[docs-system-status-analysis-2026-10.md](docs-system-status-analysis-2026-10.md)（快照报告；非改造方案）。  
**文档减量清理方案（2026-10）**：[docs-cleanup-plan-2026-10.md](docs-cleanup-plan-2026-10.md)（方案；候选≠删除清单；归档≠减总数）。  
**C1 迁档复核表（2026-10-23）**：[c1-archive-review-2026-10-23.md](c1-archive-review-2026-10-23.md)（17 迁 / 3 留；非删除）。

## 文档索引（维护区）

| 文档 | 内容 | 可信度框架位置 | 生成时间 |
|---|---|---|---|
| **`aiPlat核心能力对标报告.md`** | **现行主报告（2026-10）**：六列（aiPlat+五家）· §1–14 能力维 + §15–20 新维；评分矩阵见 `architecture/comparison.md` | §17 证据口径 | **2026-10-13** |
| **`对标底稿-2026-10-五家.md`** | 本轮指纹（SHA/tag）+ D1–D20 grep 证据 + 复核命令 | 底稿（阳性证据） | **2026-10-13** |
| **`aiPlat治理体系元审计报告.md`** | **元审计**（方法论总纲 §11）：治理体系本身是否正确/合理/完备 | **§11 阳性可信/阴性有盲区** | 2026-08-15 |
| **`企业级AI可信落地全景图-aiPlat对照.md`** | **框架对照**：六层决策操作系统 × aiPlat；立项四问等现行设计依据 | 源码级证据 | 2026-08-19 |
| **`应用工厂分析报告.md`** | 应用工厂双模式/生命周期/验收契约引用 | 验收 MUST 路径 | 2026-08-22 |
| **`plan-tier-ontology-layering.md`** | 本体三层分离设计 | （设计文档） | 2026-08-19 |
| **`LLM自动选择策略审计报告.md`** | infra LLM 自动选择策略审计 | 源码级 + 实测 | 2026-08-19 |
| **`plan-g6-hooks-bridge.md`** | G6 CC/Codex hooks 协议桥专项规划 | （规划文档） | 2026-08-19 |
| **`Hermes调研底稿.md`** | Hermes v0.20.1 调研原始材料 | （原始材料） | 2026-08-15 |
| **`plan-app-factory-l2-import-repo.md`** 等其余 plan-* | 未收官专项（见目录） | （规划） | — |

## 已迁 archive（C1 · 2026-10-23 · 只读）

| 文档 | 说明 |
|---|---|
| [`../archive/aiPlat改进方案.md`](../archive/aiPlat改进方案.md) | P0–P2 已收官 |
| [`../archive/aiPlat问题总清单与行动纲领.md`](../archive/aiPlat问题总清单与行动纲领.md) | 53/53 DONE |
| [`../archive/aiPlat实现完成度审计报告.md`](../archive/aiPlat实现完成度审计报告.md) | 完成度审计快照 |
| [`../archive/知识管理审计报告.md`](../archive/知识管理审计报告.md) | 已闭环审计 |
| [`../archive/对标吸收与架构纯度评估.md`](../archive/对标吸收与架构纯度评估.md) | 吸收核验快照 |
| [`../archive/四元同步体系元审计报告.md`](../archive/四元同步体系元审计报告.md) | 元审计快照 |
| [`../archive/规范体系审计报告.md`](../archive/规范体系审计报告.md) | 审计快照 |
| [`../archive/合规保证机制分析报告.md`](../archive/合规保证机制分析报告.md) | 审计快照 |
| [`../archive/文档体系与目录结构审计报告.md`](../archive/文档体系与目录结构审计报告.md) | 审计快照 |
| [`../archive/宪法测试24项违规修复方案.md`](../archive/宪法测试24项违规修复方案.md) | 已闭环修复记录 |
| [`../archive/architecture-evolution-roadmap.md`](../archive/architecture-evolution-roadmap.md) | Phase 0–4 路线图收官 |
| [`../archive/Codex-Harness开源借鉴分析报告.md`](../archive/Codex-Harness开源借鉴分析报告.md) | 借鉴分析 |
| [`../archive/sba-借鉴分析报告.md`](../archive/sba-借鉴分析报告.md) / [`../archive/sba-harnesseval-执行评测双闭环.md`](../archive/sba-harnesseval-执行评测双闭环.md) | SBA 对标 |
| [`../archive/prime-agent-自进化Harness核实分析.md`](../archive/prime-agent-自进化Harness核实分析.md) | 核实分析 |
| [`../archive/安全体系审计报告.md`](../archive/安全体系审计报告.md) / [`../archive/系统健康审计报告.md`](../archive/系统健康审计报告.md) | 审计快照 |
| [`../archive/plan-pipeline-engine-split.md`](../archive/plan-pipeline-engine-split.md) / [`../archive/plan-tenant-tables-migration.md`](../archive/plan-tenant-tables-migration.md) / [`../archive/CI合并门禁核实报告.md`](../archive/CI合并门禁核实报告.md) | 更早批次 |
| [`../archive/aiPlat核心能力对标报告-2026-08-六系统.md`](../archive/aiPlat核心能力对标报告-2026-08-六系统.md) | 历史六系统稿 |

## 文档关系

```
事实层：aiPlat核心能力对标报告.md（现行）
            │
验证/规划层（只读 archive）：实现完成度 / 宪法修复 / 改进方案 / 行动纲领 / 演进路线图
            ▼
元审计（维护区）：aiPlat治理体系元审计报告.md §11
现行设计依据（维护区）：企业级AI可信落地全景图 · 应用工厂分析报告
```

## 结论可信度总纲（引用任何结论前必读）

> 完整方法论见 **`aiPlat治理体系元审计报告.md` §11**。核心一句话：

- ✅ **"说系统有什么/有问题" = 高可信**（阳性：独立机制验证）
- ⚠️ **"说系统没什么/没问题" = 有盲区**（阴性：漏检/反射/未冒烟）

收官过程记录见 archive：[`../archive/aiPlat改进方案.md`](../archive/aiPlat改进方案.md)、[`../archive/宪法测试24项违规修复方案.md`](../archive/宪法测试24项违规修复方案.md)、[`../archive/aiPlat问题总清单与行动纲领.md`](../archive/aiPlat问题总清单与行动纲领.md)。

## 关键结论速查（带可信度）

| 结论 | 可信度 | 出处 |
|---|---|---|
| aiPlat 治理最强，差距在生态面 | ✅ 高 | 对标报告 §16/§21 |
| 3 子系统未接线已全部接线 | ✅ 高 | [archive 实现审计](../archive/aiPlat实现完成度审计报告.md) / [行动纲领](../archive/aiPlat问题总清单与行动纲领.md) |
| 宪法 24 项违规已全部修复 | ✅ 高 | [archive 宪法方案](../archive/宪法测试24项违规修复方案.md) |
| 治理 12 条 OR 语法 bug 已修复 | ✅ 高 | 元审计 §1.2/§10.4 |
| 行动纲领 53/53 DONE | ✅ 高 | [archive 行动纲领](../archive/aiPlat问题总清单与行动纲领.md) |

## 查询指引

- **对标强弱 / 缺口 / 架构差异** → `aiPlat核心能力对标报告.md`
- **治理体系健不健康 / 可信度方法** → `aiPlat治理体系元审计报告.md`
- **立项四问 / 六层对照** → `企业级AI可信落地全景图-aiPlat对照.md`
- **应用工厂验收依据** → `应用工厂分析报告.md`
- **已收官改进/行动/宪法/审计快照** → 见上表 archive 链接
