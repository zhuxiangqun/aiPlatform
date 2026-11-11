---
doc_type: Reference
---

# 白皮书分类清单（2026-11-11）

> 仅分类，不移动文件。  
> 判定标准：是否含强制要求、是否定义 canonical、是否用于验收/认证。

## 汇总

| 类别 | 数量 |
|---|---:|
| 规范性标准 | 0 |
| 非规范白皮书 | 5 |
| 模板 | 1 |
| 决策记录 | 1 |
| 指南 | 1 |
| 生成报告 | 6 |
| 索引/治理 | 2 |
| 历史归档 | 2 |
| **合计** | **18** |

## 逐篇判定

| 文档 | 类别 | 建议位置 | 理由 |
|---|---|---|---|
| `docs/whitepaper/README.md` | 索引 | `docs/reference/explanatory/` | 目录入口 |
| `docs/whitepaper/WHITEPAPER_SYSTEM.md` | 非规范/治理 | `docs/reference/explanatory/` | 白皮书体系说明，不是标准 |
| `docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md` | 决策记录 | `docs/decisions/architecture/` | frontmatter 为 architecture-decision-record |
| `docs/archive/whitepaper-generated/aiplat-platform-status-whitepaper.md` | 历史生成物 | `docs/archive/whitepaper-generated/` | status: generated，derived-from-capabilities |
| `docs/whitepaper/cases/README.md` | 指南 | `docs/guides/` 或 `docs/reference/explanatory/cases/` | 案例授权流程 |
| `docs/whitepaper/cases/internal-illustrative-fde.md` | 非规范 | `docs/reference/explanatory/cases/` | 内部示意案例，非客户授权 |
| `docs/whitepaper/commercial-value-model.md` | 非规范 | `docs/reference/explanatory/` | 商业价值模型，非技术规范 |
| `docs/whitepaper/ecosystem-partner-commercial-template.md` | 模板 | `docs/reference/templates/` | 明确“不构成要约” |
| `docs/whitepaper/ecosystem-partner-tiers.md` | 非规范 | `docs/reference/explanatory/` | 伙伴技术分层，非规范 |
| `docs/whitepaper/knowledge-system/aiplat-knowledge-system-engineering-appendix-v4-2026-11-11.md` | 历史归档 | `docs/archive/knowledge-system-v4.1/` | v4.1，非规范附录 |
| `docs/whitepaper/knowledge-system/aiplat-knowledge-system-technical-whitepaper-v4.1-2026-11-11.md` | 历史归档 | `docs/archive/knowledge-system-v4.1/` | v4.1 Proposed，已被 v4.3.1 替代 |
| `docs/whitepaper/verification-protocol.md` | 非规范 | `docs/reference/explanatory/` | 审计验证协议，不是已批准标准 |
| `docs/archive/whitepaper-generated/volumes/01-tech-architecture.md` | 生成报告 | `reports/whitepapers/` | status: generated |
| `docs/archive/whitepaper-generated/volumes/02-product-capability.md` | 生成报告 | `reports/whitepapers/` | status: generated |
| `docs/archive/whitepaper-generated/volumes/03-commercial-value.md` | 生成报告 | `reports/whitepapers/` | status: generated |
| `docs/archive/whitepaper-generated/volumes/04-ecosystem-integration.md` | 生成报告 | `reports/whitepapers/` | status: generated |
| `docs/archive/whitepaper-generated/volumes/05-security-governance.md` | 生成报告 | `reports/whitepapers/` | status: generated |
| `docs/archive/whitepaper-generated/volumes/README.md` | 索引 | `reports/whitepapers/` | 生成卷入口 |

## 结论

- 当前 `docs/whitepaper/` 没有“规范性技术白皮书”；
- 5 卷和平台现状白皮书是**生成报告**，不应放 `docs/`；
- v4.1 知识白皮书/附录应归档；
- 商业价值、伙伴分层、案例、验证协议属于**非规范参考**；
- 伙伴商务条款是**模板**；
- L4 自主性评估是**ADR/决策记录**。

## 迁移顺序建议

1. v4.1 → `docs/archive/knowledge-system-v4.1/`；
2. 生成卷 + 平台现状 → `reports/whitepapers/`；
3. 非规范参考 → `docs/reference/explanatory/`；
4. 模板 → `docs/reference/templates/`；
5. ADR → `docs/decisions/architecture/`；
6. 更新 `docs/README.md` 和 `WHITEPAPER_SYSTEM.md` 链接。

迁移完成前不删除任何文件。
