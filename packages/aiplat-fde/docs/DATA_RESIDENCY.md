# FDE Field D1 — 安全与数据驻留（一页）

> ADR Field deploy **Accepted** · Field D2 ops pack：[`D2_FIELD.md`](./D2_FIELD.md)

## 驻留

- 默认前缀：`$AIPLAT_HOME/fde`（`data/projects`、`data/evidence`、`backups`）
- 客户现场数据**默认不出场**；联机仅按契约上传证据包 / 签收
- 密钥：不复用控制面生产密钥；Thin env 单独 `env` 文件

## 安全基线

| 控制 | 要求 |
|------|------|
| 签收 | 唯一 `acceptance/signoff` |
| Enterprise | 默认 `AIPLAT_ENTERPRISE=0` 于 Field Thin；升 enterprise 另批 |
| MFA / 控制面 token | 联机签收走控制面既有门禁（admin MFA、platform token） |
| 备份 | `d1_backup.sh`；回滚 `d1_rollback.sh` |
| 探针 | `/api/core/fde/healthz` 或 ADR-09 one-shot；**不含**长驻 compose（另批） |

## 非目标（本页）

- PG/HA 控制面切流（见控制面 ADR）
- 五产品全拆 / 对外 E4
