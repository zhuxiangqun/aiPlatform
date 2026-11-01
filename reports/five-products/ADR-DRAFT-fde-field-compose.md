# ADR-DRAFT — FDE Field compose 长驻

> **状态**：Draft · **非 Accepted** · 冻结期仅文档  
> **范围**：现场长驻 compose（进程常驻、卷持久、可选本地 DB）  
> **非范围**：本草案不实施；不改 Field Accepted D1；不触碰 PG/HA cutover。

## Context

Field D1/D2 本地 pack 已 PASS（install / N-1 / security）。  
`MODULE.md` / compat 仍将 **compose 长驻** 列为另批（`forbidden_without_adr`）。

## Options

| 方案 | 说明 | 倾向 |
|------|------|------|
| A | 继续 one-shot / 短生命周期 demo compose | 现状 |
| B | 长驻 compose + 本地卷 + health 探活 + 备份脚本 | 本草案目标 |
| C | 独立 Field 进程拆分（A3） | 超出本草案；另 ADR |

## 草案决策（未批准）

若 Accepted：选 **B** — 现场可长驻，但：

1. 默认 `production_field` 行为不变；长驻为运维形态，非新产品宣称。  
2. compose 不得默认连中心写库；中心同步仍走既有 sync 契约。  
3. 必须有 stop/backup/rollback runbook + 本地证据模板。  
4. 不授权 control-plane PG/HA cutover。

## Consequences

- 需新增 `packages/aiplat-fde/compose.field-longrunning.yml`（实施阶段）  
- compat `forbidden_without_adr` 在 Accepted 前保持拦截长驻宣称  
- 实施须显式解冻或新 ADR Accepted 后开 PR

## Validation（Accepted 后）

```bash
# 草案阶段不执行
# docker compose -f packages/aiplat-fde/compose.field-longrunning.yml up -d
# bash packages/aiplat-fde/scripts/d1_smoke.sh
```
