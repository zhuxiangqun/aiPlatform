# ADR — Pi D3（Edge 深度运维 / SOC 产品化路径）

- **状态**：**Accepted（有条件）** · 2026-10-30  
- **草案**：[`ADR-DRAFT-pi-d3.md`](./ADR-DRAFT-pi-d3.md)（保留对照）  
- **联签**：架构 × 业务 · 用户指令「另批 Pi D3 ADR」· 2026-10-30（2026-10-31 再确认）  
- **前置**：ADR-08 / Gate3 Thin · Pi D1 · **D2 admin pack**（`docs/D2_ADMIN.md`）  
- **交叉**：不扩大 ADR-09 五产品全拆 / E4；不改 Ontology/Eval/FDE 边界

> **诚实性**：聊天联签 ≠ 生产硬门齐；`cutover_authorized` / `process_split_authorized` / `d3_production_authorized` 未全 ✅ 前禁止生产宣称。

## 决策（有条件）

1. **批准** Pi Edge **D3** 产品化路径：在 D2 admin 之上增加深度运维 / SOC 能力族（见范围）。  
2. **默认仍 offline-first**：`AIPLAT_ENTERPRISE` 安装与 smoke **默认保持 0**；企业回连仍为 opt-in。  
3. **生产 D3 宣称条件（硬门）**：[`D3_CHECKLIST.md`](../../packages/aiplat-pi-runtime/docs/d3/D3_CHECKLIST.md) 未全部 ✅ 之前，**禁止** `d3_production_authorized=true`，对外不得宣称「Pi D3 生产就绪」。  
4. D3 能力经 Bundle / HTTP Thin / 文档化扩展接入；**禁止** Pi 默认路径直导 `aiPlat-platform` / `core.harness`。  
5. 本地 baseline / prep 🟨 **不等于** 生产 SOC 绿。

## D3 范围（拟交付族）

| 族 | 说明 |
|----|------|
| Bundle 完整性 | 安装/升级校验签名或校验和策略（可配置；离线可关） |
| 运维面 | 结构化 healthz 扩展 + 日志/证据导出约定（不强制上云） |
| SOC 钩子 | 可选告警/审计事件出口（enterprise opt-in） |
| 升级通道 | 文档化 N-1 回滚；**不**新开绕过 ADR-08 的隐式更新通道 |
| 企业回连 | 沿用 `HYBRID_ENTERPRISE.md`；生产剖面另检，默认仍 off |

## 非目标

- 多租户中心化治理落在 Edge  
- 替代 Ontology / Evaluation / FDE  
- 强制生产默认 `AIPLAT_ENTERPRISE=1`  
- 借本 ADR 批五产品全拆 / 对外 E4  
- compose 长驻升格为唯一生产形态（仍按 ADR-09 另批）

## 接受门槛

| # | 门槛 | 证据 |
|---|------|------|
| 1 | D2 admin pack 绿 | `d2_admin_check.sh` |
| 2 | D3 checklist + prep_check | `docs/d3/` · `d3_prep_check.sh` |
| 3 | Chart `d3_production_authorized=false` 直至硬门齐 | `chart/Chart.yaml` |
| 4 | enterprise 默认仍 0 | install/smoke/baseline |
| 5 | authorize 未全 ✅ → REFUSE | `d3_authorize.sh` |
| 6 | 联签 | 本文 Accepted（有条件） |

## 备选（未采纳）

| 备选 | 原因 |
|------|------|
| 跳过 ADR 直接宣称 D3 | 与收口「需另批」冲突 |
| D3 默认打开企业回连 | 破坏 offline-first / 现场驻留 |
| 无条件当日生产就绪 | checklist / live 未齐 |

## 回滚

停用 D3 剖面配置；回退 D2 admin + D1 Thin；`d3_production_authorized` 保持或置回 false。

## 签署

架构 × 业务 · 2026-10-30 · **Accepted（有条件）** · **生产 D3 宣称仍须 D3_CHECKLIST 全 ✅**
