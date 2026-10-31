# ADR — 控制面 PG/HA/多租户产品化（D1）

- **状态**：**Accepted（有条件）** · 2026-10-30  
- **草案**：[`ADR-DRAFT-control-plane-d1.md`](./ADR-DRAFT-control-plane-d1.md)（保留对照）  
- **联签**：架构 × 业务 · 用户指令「联签 Field ADR及 PG-HA ADR」· 2026-10-30  
- **交叉**：A2 versioning 已先行（`VERSIONING.md` / 五包 `0.1.0`）

> **诚实性**：聊天联签 ≠ 生产硬门齐；`cutover_authorized` / `process_split_authorized` / `d3_production_authorized` 未全 ✅ 前禁止生产宣称。

## 决策（有条件）

1. **批准**控制面从「开发默认 SQLite」走向 **可交付 PG + HA + 租户隔离** 的产品化路径。  
2. **批准**维护独立 Chart / 发布节奏文书与 runbook（见 `packages/aiplat-central/docs/pg_ha/`）。  
3. **切流条件（硬门）**：下列未全部绿之前，**禁止**将生产默认库切到 PG/HA：  
   - 租户/身份契约（standalone + OIDC）回归绿  
   - PG 迁移 + 备份恢复演练记录  
   - HA runbook 演练记录（failover / 回切）  
   - 与 Pi / FDE / Ontology / Evaluation **仅契约耦合**（无跨库直读）  
4. Thin Central 打包（`packages/aiplat-central`）与 SQLite 开发默认路径**继续合法**，直至切流清单勾齐。

## 非目标

- 不在本 ADR 当日强制生产 cutover  
- 不做销售/SLA 运营层  
- 不批准五产品全拆 / 对外 E4  

## 备选（未采纳）

| 备选 | 原因 |
|------|------|
| 维持永久仅 SQLite | 无法交付企业 HA/租户隔离 |
| 无条件当日 cutover | 迁移/HA 演练未齐；爆破过大 |

## 回滚

生产未切流：无动作。已切流：按 `pg_ha/ROLLBACK.md` 回 SQLite/单实例（仅非承诺生产）或备份还原。

## 签署

架构 × 业务 · 2026-10-30 · **Accepted（有条件）** · **生产 PG/HA 切流仍须演练绿**
