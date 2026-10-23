# WP5 回顾（首切片）

> 日期：2026-10-23  
> 场景：`fp-internal-bundle-pi-diag-001`（非客户验收）  
> 依据：落地方案 §5 WP5；证据：`slice-fp-internal-bundle-pi-diag-001/WP4_CLOSEOUT.md`

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| 首切片路径 E3 | **达成**（live Pi + 诊断 ok + 验收绑 report + 故障注入 4/4） |
| 对外 E4 | **未做**（默认非对外承诺） |
| Gate 2 | **建议：维持 / 暂停扩大** — 缺 D13（见 §3） |
| Gate 3 | **不建议** — 无独立部署驱动证据 |
| 合入 main | ✅ [PR #381](https://github.com/zhuxiangqun/aiPlatform/pull/381) → `5bfdb86`（2026-10-23） |

## 2. ADR 状态

| ADR | 原状态 | WP5 |
|-----|--------|-----|
| ADR-01 边界与非目标 | Draft | **Accepted（切片范围）** — 见文件头更新 |
| ADR-02 控制面 | Draft | **Accepted（本切片）** — aiPlat 默认 |
| ADR-03 数据 owner | Draft | **Accepted（本切片）** |
| ADR-04 Pi/Bundle | Draft | **Accepted（本切片）** — Thin + mjs 导出修复 |

全仓长期 ADR 库迁移仍可后置；本目录草稿对五产品切片具约束力。

## 3. Gate 2 建议（含 D13）

**建议：维持切片成果，不进入 Gate 2 扩大。**

| Gate 2 条件 | 现状 |
|-------------|------|
| WP4 行为/安全通过 | ✅ |
| 失败可观察 / 边界成立 | ✅ |
| 五产品正式 owner | ⏳ 仍临时 R |
| **D13 客户背书 / 真实客户场景** | ❌ **缺口** — 场景为「非客户验收」 |
| 架构×业务签署扩大 | 未签 |

**D13 缺口单列**：在取得符合 §6.0.1 的书面客户背书或替换为真实客户路径之前，**不得**批准 Gate 2。内部技术通过 ≠ 客户背书。

## 4. 模块化 backlog

仅来自暴露边，见 [MODULE_BACKLOG.md](./MODULE_BACKLOG.md)。禁止「因目录好看而搬迁」。

## 5. 经验（正确/合理/合规）

1. 复用 `export_pi_bundle` 正确，但必须保证扩展依赖完整（`*.mjs`）——否则 live 路径假绿。  
2. 诊断 MVP 必须强制 unknown/stale，不能默健康。  
3. 「简化三条接线」曾偏离 §3.4；已纠正为完整切片验收。  
4. Gate 命名 L1≠Gate1≠Gate2 避免了未授权扩大。
