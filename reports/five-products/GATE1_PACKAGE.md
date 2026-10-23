# Gate 1 材料包索引（待评审 · 未批准）

> **警告**：本文件只是材料索引。**列出 ≠ 通过 Gate 1 ≠ 授权 WP3–WP4。**

## 必附

| # | 材料 | 路径 |
|---|------|------|
| 1 | L1 授权 | `L1_AUTHORIZATION.md` |
| 2 | 执行决策包 | `DECISIONS_AND_AUTHORIZATIONS.md` |
| 3 | 场景 | `SCENE.md` |
| 4 | WP0 事实清单 | `wp0-inventory.md` |
| 5 | WP1 边界 | `wp1-boundary-signoff.md` |
| 6 | ADR-01～04 草稿 | `ADR-0*-*.md` |
| 7 | 契约矩阵 + 离线 + 分册 | `contracts/` |
| 8 | WP2 DoD | `wp2-dod-checklist.md` |
| 9 | 角色 | `ROLES.md` |

## Gate 1 预检（自评 · 非正式通过）

| 检查 | 自评 |
|------|:----:|
| 无未关闭 Blocker | ✅（WP0） |
| Known Gap 含 §3.6.3 字段 | ✅ |
| 未要求已有端到端 E3 | ✅ |
| 启用集契约草案可测 | ✅ |
| 隔离「能」 | ✅ |
| 安全触及 gap 预签 | ⏳ Gate1 会上由安全兼任角色逐条签 |
| 架构×业务「批准进入 WP3–WP4」 | ❌ **未签** |

## 建议评审问句

1. Known Gap 是否有伪装成普通缺口的安全/权威未知？  
2. 诊断 MVP 范围是否仍可接受（非全功能）？  
3. 是否确认开跑后 E3 不降标？  

通过后另写 `GATE1_DECISION.md`（通过/附条件/驳回）。
