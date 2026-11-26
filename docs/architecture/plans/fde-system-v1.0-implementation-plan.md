---
doc_type: Architecture
title: FDE 系统 v1.0 实施方案
status: draft
authority: supporting
language: zh-CN
created: 2026-11-26
doc_id: FDE_SYS_V10_IMPL_PLAN
last_reviewed: 2026-11-26
purpose: 将 FDE 系统 v1.0 标准落到可认证路径（不扩大 ADR-09）
---
# FDE 系统 v1.0 实施方案

> 依据：`docs/standards/fde-system/v1.0/` 标准包。  
> 承接：`ADR09_FDE_BOUNDARY.md`、`ADR09_NEXT_FDE_DECISION.md`、Gate3 签收绑定。  
> 非标准正文；不授权 compose 长驻或强制默认独立进程。

## 0. 结论先行

```text
先锁唯一 signoff + CoreFacade + 证据字段
再工作台 / 可选独立进程文书
长驻与生产独立 authorize 另批
```

评测绿 ≠ 签收；ImportReport ≠ 签收。

### 0.1 代码证据基线（2026-11-26 · 刷新）

测量：`reports/products/fde-system/v1.0/core-gap-evidence.md`。

| Core | 测量 |
|---|---|
| F01–F06 | **exists** |
| 正式 core_ready | 待非作者复核附录 N |
| certified | **否** |

已收口：signoff 写 `tenant_id`；skills 路径经 CoreFacade。  
Extended 建议：禁止 `tenant_resolved_from=default` 的生产签收（强制 body/header）。

## 1. 目标

1. Core：附录 N F01–F06 `exists`；
2. Extended：F07–F09（对齐已有边界收口证据可引用）；
3. Operational：F10–F11（另批）。

## 2. 非目标

- 新建第二套验收系统；
- 拆本体 / 控制面；
- 未另批 compose 长驻；
- 把 FDE 做成评测中心。

## 3. 阶段

| Phase | 内容 | Gate | 相对基线 |
|---|---|---|---|
| P0 | 签收路径盘点 / 平行入口扫描 | 差距表 | **已完成** |
| P1 | 唯一 signoff + 前缀锁定 | F01–F02、F05 | **exists** |
| P2 | CoreFacade / 无 harness 直连证明 | F03 | **exists（已收口）** |
| P3 | 签收记录字段 + 回滚文书 | F04、F06 | **exists（已收口）** → 待复核 core_ready |
| P4 | report_id 策略 / 工作台 | F07–F08 | **exists（测量）** — 见 `extended-gap-evidence.md` |
| P5 | 可选独立进程 + one-shot health | F09 | **exists（测量）**；compose 长驻仍否 |
| P6 | 生产 authorize / 长驻另批 | Operational F10–F11 | **exists（门禁）**；authorized=false；compose 仍否 — 见 `operational-gap-evidence.md` |

## 4. 证据目录

`reports/products/fde-system/v1.0/`；ADR-09 closeout 可引用，须映射附录 N ID。

## 5. 交叉约束

| 系统 | 约束 |
|---|---|
| 评测 | 门禁结果不得写入签收表冒充客户验收 |
| 外援 | 客户交付外援必须走 FDE 签收 |
| 知识 | 交付手册可 Wiki；签收权威在 FDE |
| ADR-09 | 本计划不得扩大已批边界 |
