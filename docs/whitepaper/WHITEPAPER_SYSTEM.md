# aiPlat 白皮书体系（五维）

> Living · 2026-10-13  
> **原则**：每维有唯一权威源；白皮书**索引 + 摘录评分戳**，禁止手抄第二份能力/评分表。  
> 总入口生成物：[`aiplat-platform-status-whitepaper.md`](./aiplat-platform-status-whitepaper.md)（`scripts/generate_platform_whitepaper.py`）

## ready 定义

`ready` 表示该卷已具备对外可用论证能力，且生成器不再标记「材料缺口」。`ready` 是**论证闭环**，不是**商务承诺闭环**。

具体边界：

1. 论证卷结构完整，核心章节无阻断性缺口。
2. 不编造客户授权 ROI%、人天单价、伙伴分成比例。
3. 商业卷以已接线价值系统、TCO 对照清单、标注为「内部示意」的 worked example 闭环。
4. 生态卷以技术伙伴分层和开放边界闭环；商务条款提供可盖章模板，正文声明以盖章版为准。
5. 真实客户案例走 [`cases/`](./cases/) 授权流程，但不阻塞 ready。
6. 后续如有真实客户数字或渠道政策，只追加 `cases/` 与商务附录，不重做卷骨架。

### 五卷状态

| 卷 | 主题 | suite id | 状态 |
|----|------|----------|:----:|
| 01 | 技术 | `tech-architecture` | ready |
| 02 | 产品 | `product-capability` | ready |
| 03 | 商业 | `commercial-value` | ready |
| 04 | 生态 | `ecosystem-integration` | ready |
| 05 | 治理 | `security-governance` | ready |

## 为什么不能只靠「能力清单白皮书」

`aiplat-platform-status-whitepaper.md` 是 CAPABILITIES 的**可读包装（executive digest）**：定位叙事 + 统计表 + 各子系统 ✅/⚠️ 摘要；**不**粘贴完整 `文件:行号` 能力表（完整清单仍以根目录 `AIPLAT_CAPABILITIES.md` 为准）。  
若缺 **对标 / 评级 / 商业 / 生态 / 治理论证**，对外说服链不完整——这些材料仓库里已有，须纳入体系，但**不得**再写成会漂移的手抄本。

## 五维映射（权威源 → 受众）

| 维度 | 白皮书角色 | 核心问题 | 主要受众 | 仓库权威源（勿另起炉灶） | 状态 |
|------|------------|----------|----------|--------------------------|:----:|
| **技术** | 技术架构 | 为什么这样设计 | CTO / 架构师 / 工程师 | [`../architecture/overview.md`](../architecture/overview.md) · 决策矩阵 · Pi 薄 Runtime · 分卷 01 | ready |
| **产品** | 产品能力 | 能解决什么问题 | 产品 / 技术评估链 | 分卷 [`volumes/02-product-capability.md`](./volumes/02-product-capability.md) · [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) · manuals | ready |
| **商业** | 商业价值 | 投资回报如何 | CEO / CFO / 业务线 | 分卷 03 · [`commercial-value-model.md`](./commercial-value-model.md) · [`cases/`](./cases/) | ready |
| **生态** | 生态与集成 | 如何接入协作 | ISV / 社区 / 渠道 | 分卷 04 · [`ecosystem-partner-tiers.md`](./ecosystem-partner-tiers.md) · 商务模板 | ready |
| **治理** | 安全与治理 | 如何可信可控 | CISO / 合规 | CAPABILITIES「安全与治理 / Gate」· [`../security/`](../security/) · L 级 ADR | ready |

## 自动同步（CAPABILITIES → 白皮书）

真相链：

```text
代码 / 测试
  → AIPLAT_CAPABILITIES.md（auto_sync_docs + verify_doc_sync + architecture_guard）
  → assessment-scores.json（评分戳）
  → whitepaper-suite.yaml（分卷清单）
  → 现状总册 + 五维分卷（本段自动再生成）
```

| 动作 | 命令 |
|------|------|
| 全量再生成 + 新鲜度检查 | `bash scripts/sync_whitepapers.sh` |
| 仅检查（CI / pre-commit 后） | `python3 scripts/generate_platform_whitepaper.py --check` + `python3 scripts/generate_whitepaper_volumes.py --check` |
| ready 验收（含免责声明） | `bash scripts/verify-whitepaper-ready.sh`（加 `--regen` 先 sync） |

**触发（pre-commit Step 2.8）**：staged 变更命中 `AIPLAT_CAPABILITIES.md`、`whitepaper-suite.yaml`、`assessment-scores.json`、商业/生态专稿、`cases/`、或白皮书生成器脚本时，自动 `sync_whitepapers.sh` 并 stage 生成物。

**新鲜度戳**：

- 现状总册：`source_sha256`（CAPABILITIES）+ `scores_sha256`
- 分卷：`suite_sha256` + `caps_sha256` + `scores_sha256`

任一权威源变化而未再生成 → `--check` / CI 阻断。

能力是否「代码真实接线」仍以 CAPABILITIES ↔ 代码的既有守卫为准；白皮书层保证**不落后于清单与评分戳**。

## ADR 索引维护

01 技术卷 §3.0「关键设计决策索引」只指向权威源，不复制 ADR 正文。

### 权威源清单

| 决策域 | 权威源 |
|--------|--------|
| 平台总览与边界 | [`../architecture/overview.md`](../architecture/overview.md) |
| 执行决策矩阵 | [`../architecture/execution-decision-matrix.md`](../architecture/execution-decision-matrix.md) |
| Pi 薄运行时 | [`../architecture/plans/pi-thin-runtime.md`](../architecture/plans/pi-thin-runtime.md) |
| 文档体系与 ADR 分布 | [`../DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) |

### 维护责任

- **责任人**：白皮书 suite owner。
- **同步触发条件**：修改上表任一权威源时，必须在同一 PR 内同步更新 01 技术卷 §3.0 索引（即 `scripts/generate_whitepaper_volumes.py` 中 tech 分支表 + 再生成）。
- **验收**：`bash scripts/verify-whitepaper-ready.sh` 通过，且 `git diff --exit-code` 干净。

### 更新触发清单

- [ ] 修改 `docs/architecture/overview.md` → 检查索引
- [ ] 修改 `docs/architecture/execution-decision-matrix.md` → 检查索引
- [ ] 修改 `docs/architecture/plans/pi-thin-runtime.md` → 检查索引
- [ ] 修改 `docs/DOCUMENT_SYSTEM.md` → 检查索引

### 技术卷正文编排（01 卷 §3）

技术卷面向 CTO/架构师，**以设计叙事为主**，避免变成对标报告或源码路径合集：

| 节 | 内容策略 |
|----|----------|
| §3.0 | 关键设计决策**索引**（不复制 ADR） |
| §3.1 | 架构全景**白话叙事**（分层/请求路径/铁律）；图示与代码入口见 overview |
| §3.2 | 多系统对标**摘要**（一句话定位 + 加权总分一行）；18 维全文见 `comparison.md` |
| §3.3 | 工程落地**索引表**（部署/性能/可观测/数据/测试…）；不粘贴手册/源码节选 |

- **维护位置**：`scripts/generate_whitepaper_volumes.py` → `tech-architecture`（`_tech_architecture_narrative` / `_tech_comparison_digest` / §3.3 表）
- **同步触发**：overview / comparison / 工程权威源变更时，同一 PR 内 `bash scripts/sync_whitepapers.sh`
- **验收**：01 卷以 §3.1 叙事为主；§3.2 无完整 18 维星级表；无大段 `*.py` 路径清单

## 对标与评级（横切，必须进总白皮书目录）

| 类型 | 权威源 | 说明 |
|------|--------|------|
| 核心能力对标（主） | [`../research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) | vs Hermes / Claude Code / OpenClaw / DeepSeek Harness / OpenAI Codex（2026-10）；底稿 `research/对标底稿-2026-10-五家.md` |
| 架构对比入口 | [`../architecture/comparison.md`](../architecture/comparison.md) | 六平台 18 维摘要 + 加权分；旧四平台稿见 archive |
| 综合评估 / 分数 | [`../framework/aiplat-complete-assessment.md`](../framework/aiplat-complete-assessment.md) · [`../framework/assessment-scores.json`](../framework/assessment-scores.json) | 分数唯一源经 `assessment-spec.yaml` |
| 自主性 L 级 | [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md) | L5 定级 ADR + `verify_whitepaper_refs.sh` |
| 厂商策略对比 | [`../strategy/comparison-vs-vendors.md`](../strategy/comparison-vs-vendors.md) | 商业/厂商视角 |
| 历史对比 | [`../archive/`](../archive/) | **只读**，不进现行论证 |

生成器在现状白皮书中插入 **「对标、评级与五维体系」** 章：摘录 `assessment-scores.json` 关键综合分 + 上表链接（不复制整份对标报告）。

## 推进优先级

1. **P0**：技术架构论证入口 + 安全治理入口 + 对标/评级戳进总白皮书 — ✅  
2. **P1**：产品能力专章（场景 × CAPABILITIES 切片）— ✅  
3. **P2**：生态开放边界 + 技术伙伴分层 — ✅（商务条款以盖章模板为准）  
4. **P3**：商业价值模型 + 内部示意 — ✅（真实客户 ROI → [`cases/`](./cases/) 授权后追加）

## 五维分卷（生成物）

清单：[`whitepaper-suite.yaml`](./whitepaper-suite.yaml)  
输出：[`volumes/`](./volumes/)  

```bash
python3 scripts/generate_whitepaper_volumes.py
python3 scripts/generate_whitepaper_volumes.py --check
bash scripts/verify-whitepaper-ready.sh
```

## 反模式

| ❌ | ✅ |
|----|----|
| 把对标报告全文粘进生成白皮书 | 索引权威源 + 评分 JSON 戳 |
| 白皮书手改 ✅ 数 / L 级 | 改 CAPABILITIES / assessment-spec 再生成 |
| 多份「现行对比」并行 | `architecture/comparison.md` + `research/` 主报告 |
| 未授权客户 ROI / 假分成写入卷正文 | 示意案例 + 商务模板 + 盖章版 |

## 命令

```bash
python3 scripts/generate_platform_whitepaper.py
python3 scripts/generate_platform_whitepaper.py --check
# 自主性评估引用（既有）
bash scripts/verify_whitepaper_refs.sh
# ready 全量验收
bash scripts/verify-whitepaper-ready.sh
```
