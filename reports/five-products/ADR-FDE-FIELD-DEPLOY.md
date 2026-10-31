# ADR — FDE 现场部署（Field D1）

- **状态**：**Accepted** · 2026-10-30  
- **草案**：[`ADR-DRAFT-fde-field-deploy.md`](./ADR-DRAFT-fde-field-deploy.md)（保留对照）  
- **联签**：架构 × 业务 · 用户指令「联签 Field ADR及 PG-HA ADR」· 2026-10-30  
- **范围**：Field D1 交付形态（安装前缀 / 备份回滚 / 证据 / 唯一签收）；**不含** compose 长驻；**不含** PG/HA

> **诚实性**：聊天联签 ≠ 生产硬门齐；`cutover_authorized` / `process_split_authorized` / `d3_production_authorized` 未全 ✅ 前禁止生产宣称。

## 决策

批准 **Field D1**：

1. 现场安装前缀 `$AIPLAT_HOME/fde`（或 `AIPLAT_FDE_PREFIX`）+ 备份/回滚脚本（`packages/aiplat-fde`）  
2. 本地项目/验收数据目录；可导出 `fde.evidence.v0`  
3. 签收仍唯一：`POST /api/platform/apps/fde/acceptance/signoff`  
4. 默认可与控制面共置；独立进程为**正式可选**；compose 长驻另批  
5. `INSTALL_META.production_field=true` · `field_d1_adr=accepted`

## 接受门槛（闭合）

| # | 门槛 | 证据 |
|---|------|------|
| 1 | FIELD_SCOPE + healthz/evidence 契约 | `modules/fde/contracts/validate_sample.py` |
| 2 | 安装/备份/回滚 + health | `packages/aiplat-fde/scripts/d1_*.sh` + ADR-09 / `/api/core/fde/healthz` |
| 3 | N-1 Pi Bundle / report_id | `packages/aiplat-fde/docs/N1_COMPAT.md` |
| 4 | 安全/数据驻留一页 | `packages/aiplat-fde/docs/DATA_RESIDENCY.md` |
| 5 | 联签 Accepted | 本文 |

## 禁止

- 平行签收入口  
- 自建 Runtime / Ontology / Evaluation  
- 借本 ADR 默示批准 PG/HA 或五产品全拆  

## 回滚

停现场前缀进程；切回控制面共置；保留证据导出包与 `d1_backup` 产物。

## 签署

架构 × 业务 · 2026-10-30 · **Field D1 Accepted** · compose 长驻 / PG-HA 仍须另批
