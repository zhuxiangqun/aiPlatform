# FDE Field D1 — N-1 兼容说明

> ADR: Field deploy **Accepted** · Pi Bundle / Diagnosis `report_id`

## Pi Bundle

| 项 | 约定 |
|----|------|
| 消费 | Field 导入 / 引用 Pi Thin Bundle（`agent_manifest.json` + skills） |
| 兼容范围 | ADR-04 / Gate3 Thin：`runtime_compat_range` + integrity；坏包安装前拒绝 |
| 禁止 | Field 不内嵌 Pi Runtime；不改 Bundle 字段语义 |
| 回滚 | **Bundle 版本优先**于 Field 前缀回滚 |

## Diagnosis `report_id`

| 项 | 约定 |
|----|------|
| 证据导出 | `fde.evidence.v0` 可含 `report_id` / `items[].ref` 指向诊断报告 |
| 签收 | **唯一** `POST /api/platform/apps/fde/acceptance/signoff`；可携带既有 `report_id` |
| N-1 | 旧诊断 MVP report id 字符串仍可引用；不强制新 UUID schema |
| 禁止 | 平行签收入口；Field 不自建第二套诊断引擎 |

## 验证

```bash
python3 reports/five-products/modules/fde/contracts/validate_sample.py
# evidence schema 含 report_id + items[].ref
```
