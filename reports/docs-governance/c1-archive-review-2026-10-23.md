# C1 复核表 — research 收官候选（2026-10-23）

> 批次批准：用户指示「开始实施」（C1）。**未批准 C2–C4。**  
> 输入：`docs-cleanup-plan-2026-10.md` §8.5.1 冻结 20 份。  
> R3 普查时点：与实施同日（仓库内 grep）；外部留存 **未核实** 处已标。

## 裁决摘要

| # | 文件 | R1 | R2 现行责任 | R6 | R7 |
|---|------|----|-------------|----|-----|
| 1 | Codex-Harness开源借鉴分析报告.md | 报告快照 | 无；代码注释仅设计依据 | **迁 archive** | 维护区 −1 |
| 2 | aiPlat实现完成度审计报告.md | 报告快照 | 无（未接线项已收官） | **迁 archive** | −1 |
| 3 | aiPlat改进方案.md | 过程纸/规划收官 | 无（P0–P2 已落地） | **迁 archive** | −1 |
| 4 | aiPlat治理体系元审计报告.md | 报告快照 | **有**：research README 可信度方法论入口 §11 | **保留维护区** | 0 |
| 5 | aiPlat问题总清单与行动纲领.md | 过程纸收官 | 无（53/53 DONE；脚本一句指向） | **迁 archive** | −1 |
| 6 | architecture-evolution-roadmap.md | 规划收官 | 无操作责任；白皮书/脚本引用可改链 | **迁 archive** | −1 |
| 7 | prime-agent-自进化Harness核实分析.md | 报告快照 | 无 | **迁 archive** | −1 |
| 8 | sba-harnesseval-执行评测双闭环.md | 报告快照 | 无；模块头注释设计依据 | **迁 archive** | −1 |
| 9 | sba-借鉴分析报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 10 | 企业级AI可信落地全景图-aiPlat对照.md | 报告/框架对照 | **有**：four_questions / 测试 / 白皮书现行设计依据 | **保留维护区** | 0 |
| 11 | 合规保证机制分析报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 12 | 四元同步体系元审计报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 13 | 安全体系审计报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 14 | 宪法测试24项违规修复方案.md | 过程纸收官 | 无（宪法已绿；记录可归档） | **迁 archive** | −1 |
| 15 | 对标吸收与架构纯度评估.md | 报告快照 | 无操作责任；白皮书引用可改链 | **迁 archive** | −1 |
| 16 | 应用工厂分析报告.md | 报告快照 | **有**：acceptance contract MUST 路径 + 架构契约引用 | **保留维护区** | 0 |
| 17 | 文档体系与目录结构审计报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 18 | 知识管理审计报告.md | 报告快照 | 无（文内自陈已闭环） | **迁 archive** | −1 |
| 19 | 系统健康审计报告.md | 报告快照 | 无 | **迁 archive** | −1 |
| 20 | 规范体系审计报告.md | 报告快照 | 无 | **迁 archive** | −1 |

**本批迁档 17 · 保留 3。** 不删除。

## R3 入链与处置（迁档篇）

说明：`docs-cleanup-plan` / 本表 / disposition CSV 中的文件名枚举 → **确认无需改**（候选表留档，非运行时引用）。`reports/` 根目录 CSV → 同。外部系统副本 → **未核实·待确认**（无仓库证据）。

| 文件 | 引用处 | 处置 |
|------|--------|------|
| Codex-Harness… | `stdio_server.py` / `os_sandbox.py` / `import_claude_sessions.py` 头注释 | 已改路径 → `docs/archive/…` |
| | `docs/archive/aiPlat核心能力对标报告-2026-08-六系统.md` | 已改路径（若含链） |
| aiPlat实现完成度… | research README、行动纲领（同批迁） | README 改 archive 链；交叉文随迁 |
| aiPlat改进方案 | README、Hermes调研底稿、路线图（同批） | 已改 |
| aiPlat问题总清单… | README、Hermes调研底稿、`scripts/rule_golden_sample.py` | 已改 |
| architecture-evolution-roadmap | README；whitepaper suite YAML；`docs/whitepaper/volumes/01-tech-architecture.md`；`scripts/generate_whitepaper_volumes.py`；`scripts/coupling_metrics.py` | 已改 → archive |
| prime-agent… | （仅方案/CSV） | 确认无需改 |
| sba-harnesseval… | `experience_feedback.py` 头注释 | 已改 |
| sba-借鉴… | （仅方案/CSV） | 确认无需改 |
| 合规保证… | README | 已改 |
| 四元同步… | README、行动纲领 | 已改 |
| 安全体系… | （仅方案/CSV） | 确认无需改 |
| 宪法测试24项… | README、改进方案、行动纲领 | 已改 |
| 对标吸收… | README；核心对标报告；plan-g6；白皮书 yaml/生成脚本/status 白皮书；archive 六系统稿 | 已改 |
| 文档体系… | README、行动纲领 | 已改 |
| 知识管理… | README | 已改 |
| 系统健康… | （仅方案/CSV）；文内链到应用工厂（保留维护区） | 文内相对链已修 |
| 规范体系… | README、行动纲领 | 已改 |

## 保留三篇（不迁）

| 文件 | 理由 |
|------|------|
| aiPlat治理体系元审计报告.md | README「结论可信度总纲」仍指向 §11 |
| 企业级AI可信落地全景图-aiPlat对照.md | 生产代码/测试设计依据 |
| 应用工厂分析报告.md | `06-acceptance-contract` MUST `ls docs/research/…` |

## R5

仓库内未见合规签收强制留存条款。外部归档副本：**未核实·待确认**（不默认无义务；本批仅迁 archive，不删）。

## 批次验收

| 项 | 结果 |
|----|------|
| 迁档数 | **17**（保留 3） |
| 删除 | **0** |
| 单篇相对链接（迁入 17 篇 Markdown 链） | checked 5 · **broken 0** |
| 批次级复查 | 同上统一扫描 · **broken 0**；`docs/research/<已迁文件>` 路径残留 **0** |
| C0 口径复测 | total **260**（+1 本复核表）· maint **196**（基线 212 −17 迁档 +1 复核表） |
| 仓库总数 | 升 1 因新增本表；**未因迁档下降**（符合 archive≠减总数） |

**C2–C4：未实施、未批准。**
