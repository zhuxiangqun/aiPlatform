---
doc_type: Report
---

# Batch 07 reports 抽样事实审核

## 范围

`reports/` 共 305 份，本轮抽样 10 份：

| 类别 | 样本 |
|---|---|
| framework | `reports/framework/scoring-detail.md` |
| framework | `reports/framework/aiplat-complete-assessment.md` |
| framework | `reports/framework/aiplat-autonomy-framework.md` |
| security | `reports/security/aiplat-security-quality-report-2026-11-09-v3.md` |
| security | `reports/security/aiplat-security-quality-report-2026-11-09-v2-evidence.md` |
| security | `reports/security/security-quality-dimensions.md` |
| ops | `reports/five-products/ops/STAGING_REVIEW_EVENT_DRIVEN.md` |
| ops | `reports/five-products/ops/STAGING_REVIEW_2026-11-29.md` |
| ops | `reports/five-products/ops/STAGING_READY.md` |
| governance | `reports/docs-governance/docs-system-status-analysis-2026-10.md` |
| whitepaper | `reports/whitepapers/aiplat-platform-status-whitepaper.md` |

## 检查结果

```text
pass 10 / fix 0 / needs-owner 0
```

### 关键检查点

- framework 三份已按中间报告处理，未宣称 canonical；
- security 报告明确“非认证 / 非完整审计”，未有过度声明；
- staging review 已标注 2026-11-29 作废、不排期，并转向事件驱动；
- `STAGING_READY` 与事件驱动结论一致：`staging_ready=false`；
- whitepaper 生成物 freshness 通过；
- docs-governance 报告为历史过程材料，带有日期与边界。

## 限制

```text
reports 是运行证据/历史快照，不做逐篇商业或外部事实核验
本轮为抽样，不代表 305 份全部语义通过
```

## 验证

```text
全量链接：0 断链
whitepaper freshness：通过
```

## 累计

```text
standards  16
contracts  36
architecture 61
products   14
guides     34
subrepos   159
packages   107
reports    10（抽样）
合计       437 份文档
needs-owner 10
```
