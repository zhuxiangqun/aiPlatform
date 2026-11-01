# ADR-DRAFT — FDE Field compose 长驻（v2）

> **状态**：Draft v2 · **继续 Draft**（2026-11-01 决议）· **非 Accepted / 非 Rejected**  
> **范围**：现场长驻 compose（进程常驻、卷持久、可选本地 DB）  
> **非范围**：本草案不实施；不改 Field Accepted D1；不触碰 PG/HA cutover；不 authorize。

## Context

Field D1/D2 本地 pack 已 PASS（install / N-1 / security / D3 local UAT dry-run）。  
`MODULE.md` / compat 仍将 **compose 长驻** 列为另批（`forbidden_without_adr`）。  
v1 仅列选项；v2 补齐运行面、失败模式、证据模板与验收门槛，供 11-15 后解冻评审。

## Options

| 方案 | 说明 | 倾向 |
|------|------|------|
| A | 继续 one-shot / 短生命周期 demo compose | 现状（冻结默认） |
| B | 长驻 compose + 本地卷 + health 探活 + 备份脚本 | **本草案目标** |
| C | 独立 Field 进程拆分（A3） | 超出本草案；另 ADR |

## 草案决策（未批准）

若 Accepted：选 **B** — 现场可长驻，但：

1. 默认 `production_field` 行为不变；长驻为运维形态，非新产品宣称。  
2. compose 不得默认连中心写库；中心同步仍走既有 sync 契约。  
3. 必须有 stop/backup/rollback runbook + 本地证据模板。  
4. 不授权 control-plane PG/HA cutover。  
5. `environment=local|field` 明示；禁止把长驻证据标 `staging` / `production_signed`。

## 运行面（Accepted 后实施，本稿不建文件）

| 构件 | 意图 |
|------|------|
| `compose.field-longrunning.yml` | 单节点常驻：field API + 本地卷；无中心 PG |
| 卷 | `./data/field`（状态）+ `./data/backups` |
| health | `GET /healthz` 周期探活；失败 → restart 策略文档化 |
| 备份 | 复用 `d1_backup.sh`；长驻日更一次证据 JSON |
| 回滚 | compose down → 卷快照恢复 → up；与 Field D1 rollback 对齐 |

## 失败模式（须在 runbook 写明）

| 失败 | 期望 |
|------|------|
| 进程 OOM / crash | compose restart；health 变红；不静默绿 |
| 磁盘满 | backup 失败非 0；禁止宣称 drill PASS |
| 中心不可达 | 本地只读/队列；**不得**伪造 sync 成功 |
| 误连中心写库 | compat / baseline 阻断（Accepted 后接线） |

## 证据模板（Accepted 后）

```json
{
  "kind": "fde_field_longrunning_local_not_production",
  "environment": "local",
  "production_signed": false,
  "uptime_minutes": 0,
  "healthz_ok": true,
  "backup_ok": true,
  "center_write": false
}
```

## Consequences

- 需新增 `packages/aiplat-fde/compose.field-longrunning.yml`（**实施阶段**）  
- compat `forbidden_without_adr` 在 Accepted 前保持拦截长驻宣称  
- 实施须显式解冻或新 ADR Accepted 后开 PR  
- 不改变 `staging_ready` / 任何 authorize 轨

## Validation（Accepted 后）

```bash
# 草案阶段不执行
# docker compose -f packages/aiplat-fde/compose.field-longrunning.yml up -d
# bash packages/aiplat-fde/scripts/d1_smoke.sh
# bash packages/aiplat-fde/scripts/d1_backup.sh
```

## 决策记录（冻结兼容）

| 日期 | 决议 | 说明 |
|------|------|------|
| 2026-11-01 | **继续 Draft** | 本地工程已冻结；无独立预发 / Field 长驻需求未触发；**不 Accepted、不实施、不 Reject**。下次可在 11-22 复审或显式解冻后重开。 |

## Changelog

| 版 | 日期 | 变更 |
|----|------|------|
| v1 | 2026-11-01 | 初稿：选项 A/B/C + 四条约束 |
| v2 | 2026-11-01 | 运行面 / 失败模式 / 证据模板 / 验收门槛 |
| v2.1 | 2026-11-01 | 记录「继续 Draft」；仍禁止实施 |
