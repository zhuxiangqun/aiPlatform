# aiPlat 白皮书体系（五维）

> Living · 2026-10-12  
> **原则**：每维有唯一权威源；白皮书**索引 + 摘录评分戳**，禁止手抄第二份能力/评分表。  
> 总入口生成物：[`aiplat-platform-status-whitepaper.md`](./aiplat-platform-status-whitepaper.md)（`scripts/generate_platform_whitepaper.py`）

## 为什么不能只靠「能力清单白皮书」

`aiplat-platform-status-whitepaper.md` 完整收录 **CAPABILITIES**，回答「平台有什么、是否接线」。  
若缺 **对标 / 评级 / 商业 / 生态 / 治理论证**，对外说服链不完整——这些材料仓库里已有，须纳入体系，但**不得**再写成会漂移的手抄本。

## 五维映射（权威源 → 受众）

| 维度 | 白皮书角色 | 核心问题 | 主要受众 | 仓库权威源（勿另起炉灶） | 状态 |
|------|------------|----------|----------|--------------------------|------|
| **技术** | 技术架构 | 为什么这样设计 | CTO / 架构师 / 工程师 | [`../architecture/overview.md`](../architecture/overview.md) · [`../architecture/comparison.md`](../architecture/comparison.md) · 各仓 `CLAUDE.md` · 本目录现状白皮书第 1–3 章 | ✅ 有源；生成白皮书已链入 |
| **产品** | 产品能力 | 能解决什么问题 | 产品 / 技术评估链 | 分卷 [`volumes/02-product-capability.md`](./volumes/02-product-capability.md) · [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) · manuals / FDE / Pi 边界 | ✅ 分卷已生成（场景切片 + 统计）；细节仍链回清单 |
| **商业** | 商业价值 | 投资回报如何 | CEO / CFO / 业务线 | 分卷 [`volumes/03-commercial-value.md`](./volumes/03-commercial-value.md) · ROADMAP · [`cases/`](./cases/) | ✅ v1 论证框架；**ROI 数字**仍 gap |
| **生态** | 生态与集成 | 如何接入协作 | ISV / 社区 / 渠道 | 分卷 [`volumes/04-ecosystem-integration.md`](./volumes/04-ecosystem-integration.md) · mcp/API/Pi | ✅ 开放边界矩阵；**伙伴商务条款**仍 gap |
| **治理** | 安全与治理 | 如何可信可控 | CISO / 合规 | CAPABILITIES「安全与治理 / Gate」· [`../security/`](../security/) · [`../compliance/`](../compliance/) · PolicyGate 规约 | ✅ 材料厚；生成白皮书链入评分与安全入口 |

## 对标与评级（横切，必须进总白皮书目录）

| 类型 | 权威源 | 说明 |
|------|--------|------|
| 核心能力对标（主） | [`../research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) | vs Claude Code / DeepSeek Harness / Hermes；见 `research/README.md` |
| 架构对比入口 | [`../architecture/comparison.md`](../architecture/comparison.md) | 旧多份对比已归档，以此为准 |
| 综合评估 / 分数 | [`../framework/aiplat-complete-assessment.md`](../framework/aiplat-complete-assessment.md) · [`../framework/assessment-scores.json`](../framework/assessment-scores.json) | 分数唯一源经 `assessment-spec.yaml` |
| 自主性 L 级 | [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md) | L5 定级 ADR + `verify_whitepaper_refs.sh` |
| 厂商策略对比 | [`../strategy/comparison-vs-vendors.md`](../strategy/comparison-vs-vendors.md) | 商业/厂商视角 |
| 历史对比 | [`../archive/`](../archive/) | **只读**，不进现行论证 |

生成器在现状白皮书中插入 **「对标、评级与五维体系」** 章：摘录 `assessment-scores.json` 关键综合分 + 上表链接（不复制整份对标报告）。

## 推进优先级（与你的建议对齐）

1. **P0**：技术架构论证入口 + 安全治理入口 + 对标/评级戳进总白皮书 — ✅  
2. **P1**：产品能力专章（场景 × CAPABILITIES 切片）— ✅ 分卷 `02-product-capability.md`（可再生成）  
3. **P2**：生态开放边界收敛 — ✅ 分卷 `partial`（商务伙伴条款仍 gap）  
4. **持续**：商业 v1 框架 — ✅；真实 ROI → [`cases/`](./cases/) 授权后追加

## 五维分卷（生成物）

清单：[`whitepaper-suite.yaml`](./whitepaper-suite.yaml)  
输出：[`volumes/`](./volumes/)  

```bash
python3 scripts/generate_whitepaper_volumes.py
python3 scripts/generate_whitepaper_volumes.py --check
```

## 反模式

| ❌ | ✅ |
|----|----|
| 把对标报告全文粘进生成白皮书 | 索引权威源 + 评分 JSON 戳 |
| 白皮书手改 ✅ 数 / L 级 | 改 CAPABILITIES / assessment-spec 再生成 |
| 多份「现行对比」并行 | `architecture/comparison.md` + `research/` 主报告 |

## 命令

```bash
python3 scripts/generate_platform_whitepaper.py
python3 scripts/generate_platform_whitepaper.py --check
# 自主性评估引用（既有）
bash scripts/verify_whitepaper_refs.sh
```
