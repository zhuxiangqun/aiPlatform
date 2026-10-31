# ADR — Ontology A3（图服务进程/存储独立）

- **状态**：**Accepted（有条件）** · 2026-10-30  
- **草案**：[`ADR-DRAFT-ontology-a3.md`](./ADR-DRAFT-ontology-a3.md)（保留对照）  
- **联签**：架构 × 业务 · 用户指令「联签 A3」· 2026-10-30  
- **前置**：Ontology D1 Thin 共宿（`packages/aiplat-ontology` · `ontology.api.v0`）

> **诚实性**：聊天联签 ≠ 生产硬门齐；`cutover_authorized` / `process_split_authorized` / `d3_production_authorized` 未全 ✅ 前禁止生产宣称。

## 决策（有条件）

1. **批准** Ontology 独立进程 + 独立存储（PG 或专用图仓）的产品化路径。  
2. 控制面 / FDE / Eval **仅经** `ontology.api.v0` + `/api/core/ontology/healthz`。  
3. 编辑器与 Wiki 经 CoreFacade / HTTP，禁止直读图文件 / `core.harness.knowledge`。  
4. **拆分条件（硬门）**：[`SPLIT_CHECKLIST.md`](../../packages/aiplat-ontology/docs/a3/SPLIT_CHECKLIST.md) 未全部 ✅ 之前，**禁止** `process_split_authorized=true`，默认仍共宿 D1。  
5. 本地文件双写/回滚演练（🟨）**不等于** live 迁移绿。

## 非目标

- 不重写全部 ontology YAML 生态  
- 不把 Knowledge 三分揉进单服务  
- 不借本 ADR 批五产品全拆 / E4 / 生产默认当日拆分  

## 接受门槛

| # | 门槛 | 证据 |
|---|------|------|
| 1 | `ontology.api.v0` + healthz | unit + D1 smoke（🟨 契约层） |
| 2 | Chart / 安装前缀骨架 | `packages/aiplat-ontology/chart/` |
| 3 | 双写/迁移演练 | local 🟨；live 仍须 |
| 4 | 零 harness.knowledge 直导 | `a3_prep_check` |
| 5 | 回滚演练 | local 🟨；live 仍须 |
| 6 | 联签 | 本文 Accepted（有条件） |

## 备选（未采纳）

| 备选 | 原因 |
|------|------|
| 永久仅共宿 | 无法解耦发布/扩缩 |
| 无条件当日拆分 | live 演练未齐 |

## 回滚

停 Ontology 独立进程；读路径切回 core 内嵌 GraphIndex（共宿 D1）。

## 签署

架构 × 业务 · 2026-10-30 · **Accepted（有条件）** · **生产进程拆分仍须 SPLIT_CHECKLIST 全 ✅**
