---
doc_type: Report
title: Phase 2 — catalog exists 诚实锁盘点（非 ADR 表项）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
catalog: reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml
exception_adr: reports/products/knowledge-system/v4.3.1/phase2-exception-adr.md
---

# Phase 2 / catalog 诚实锁盘点

> 范围：`n24-conformance-catalog.yaml` 中 `status: exists` 且 note 仍含深度缺口，但 **未** 单独列入 [`phase2-exception-adr.md`](./phase2-exception-adr.md) 例外表的项。  
> 判定三选一：**仍开放** / **已过时** / **并入既有刀**。  
> **禁止**：本盘点冒充附录 N certified / 关闭 ADR 例外 / 风险已接受签字。

## 本切片修复

| 项 | 判定 | 说明 |
|----|------|------|
| N09 catalog YAML | **已过时（结构债）** | `note` 误嵌进 evidence 列表导致 `ScannerError`，conformance pack 无法加载；已回顶层 item `note` |
| N11 note「切写未授权」 | **已过时** | 作业级切写授权已接线（`phase2-migration-cutover-auth-evidence.md`）；note 改为「非生产切写认证」 |

## 未进 ADR 例外表的 exists 项

| ID | catalog note 摘要 | 判定 | 后续 |
|----|-------------------|------|------|
| N02 | ObjectType 人审发布 deepen 已接线；全量门户/种子替换仍缺 | **并入既有刀**（deepen）+ **仍开放**（全量门户） | deepen 见 ADR N02 + `phase2-object-type-publish-evidence.md`；全量门户仍开放 |
| N05 | 非 Wiki 全量 / certified | **仍开放** | 独立刀 `n05-a`；不并入 N06 Gateway |
| N10 | 非全知识域 gold 流水线 | **并入既有刀**（部分）+ **仍开放**（gold） | 校准门槛并入 ADR「N13/校准」；全域 gold 仍开放 → `n10-a` |
| N15 | 标准包 schema 已发布 | **已过时**（无 deepen 债） | 保持 exists；无单独 deepen todo |
| N16 | phase0 schema validate | **已过时**（无 deepen 债） | 同上 |
| N17 | 参考策略用例；非实现方运行时权威 | **仍开放** | `n17-a` |
| N18 | 非生产 RBAC 源替换 / 非 certified | **仍开放** | `n18-a`；与 N04/N12「非部署 RBAC」相邻但不可合并宣称 |
| N19 | Fact/Query 审计快照未统一 | **仍开放** | `n19-a`；不并入 N08 Action 审计 |
| N20 | 知识面未按标准完整 L1/L2/L3 | **仍开放** | `n20-a`；不并入 N08 Lv4 |
| N21 | 查询统一 abstain+citations 未全覆盖 | **仍开放** | `n21-a`；不并入 N13 校准封顶 |
| N14 生产对账 | note 已写「非 Raw↔Fact↔Index 全链路」 | **仍开放** | `n14-prod`；与 ADR N11/N14 并存（ADR 覆盖切写授权，本项覆盖生产全链路） |

## 已在 ADR 例外表（本盘点不重复开刀）

N01 · N03 · N04/N12 · N06 · N07/N22 · N08 · N09 · N11/N14 · N13/校准 · N23/OCS · N24 · SLO

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog YAML 可解析 | pass | `yaml.safe_load` + `build_conformance_pack` |
| 未宣称任何 Nxx certified | pass | 本文件 honesty |
| 未关闭 ADR 例外行 | pass | `phase2-exception-adr.md` 仍 active |

## 命令

```bash
python3 -c "import yaml; yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); print('ok')"
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -c \
  "from core.harness.knowledge_pipeline.conformance_pack import build_conformance_pack; p=build_conformance_pack(); print('items', len((p.get('catalog') or {}).get('items') or p.get('items') or []))"
```

## 明确未做

- 关闭任何 ADR 例外 / 置 `certified=true`
- 全量 ObjectType 人审、Wiki 全量、gold 流水线、运行时语义权威、RBAC 真源替换、Fact/Query 快照统一、L1–L3 完整分层、abstain+citations 全覆盖、生产 Raw↔Fact↔Index 对账
