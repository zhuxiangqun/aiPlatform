---
doc_type: Architecture
title: 外援互通 v1.0 实施方案
status: draft
authority: supporting
language: zh-CN
created: 2026-11-26
doc_id: EXT_INTEROP_V10_IMPL_PLAN
last_reviewed: 2026-11-26
purpose: 将外援互通 v1.0 标准落到可认证路径
clause_sync: "2026-11-26 · 对齐非作者 Core/Extended/Operational 批准记录"
---
# 外援互通 v1.0 实施方案

> 依据：`docs/standards/external-interop/v1.0/` 标准包。  
> 承接：`external-asset-interop-compat-tiers.md`。  
> 非标准正文。**实现徽章以** `reports/products/external-interop/v1.0/*-approval-record.approved.json` **为准**（clause-sync）。

## 0. 结论先行

```text
先 L0/L1 + 审计 + Policy
再 L2 语义判定
最后生产 authorize
```

导入成功 ≠ L2；评测绿 ≠ 自动升层。

### 0.1 代码证据基线（2026-11-26 · clause-sync）

测量与批准：`reports/products/external-interop/v1.0/`。

| 层 | 状态 |
|---|---|
| X01–X06 | **exists** + **conditional core_ready**（朱鸿林） |
| X07–X09 | **exists** + **conditional extended_ready**（朱莹） |
| X10–X11 | **authorized / operational_ready=true**（朱莹；pilot SLA + vendor） |
| certified | **否**（≠ L2 auto-grant） |

已收口：checksum；claimed/verified；§C.1；half_import；L0 fail-closed；PolicyGate+COMPAT syscall 门。

## 1. 目标

1. Core：附录 N X01–X06 `exists`；
2. Extended：X07–X09；
3. Operational：X10–X11。

## 2. 非目标

- 一次对接所有供应商协议；
- 跳过 PolicyGate；
- 用 demo 冒充生产授权。

## 3. 阶段

| Phase | 内容 | Gate | 相对基线 |
|---|---|---|---|
| P0 | 资产类型盘点 / 旧导入路径表 | 差距表 | **已完成** |
| P1 | Manifest Schema + checksum | X01–X02 | **exists（已收口）** |
| P2 | claimed/verified + 半导入禁 | X03、X06 | **exists（已收口）** |
| P3 | PolicyGate 接线证明 | X04–X05 | **exists** → **core_ready conditional** |
| P4 | L1 沙箱试调用 | X07 | **exists**（extended 已批）— `run_l1_sandbox_trial` |
| P5 | L2 探针 + 目录 | X08–X09 | **exists** → **extended_ready conditional** |
| P6 | 生产 authorize / SLA | Operational X10–X11 | **authorized / operational_ready** — 见 `operational-gap-evidence.md` |

## 4. 证据目录

`reports/products/external-interop/v1.0/`。

## 5. 交叉约束

- 评测系统：Tool/MCP subject 引用 `verified_tier`；
- FDE：客户侧外援签收独立；
- 知识体系：外援文档 ingest 不改变互通权威源。
