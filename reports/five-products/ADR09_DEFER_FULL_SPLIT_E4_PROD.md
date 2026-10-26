# 决定：延期范围更新（2026-10-27；本体窄批后）

- **效力**：架构决策 owner × 业务场景 owner（兼任 · 本仓库维护者）  
- **上级**：`ADR09_NEXT_ONTOLOGY_DECISION.md`；`ADR09_NEXT_FDE_DECISION.md`；`ADR09_NEXT_PI_THIN_DECISION.md`；`ADR09_STEP4_DECISION.md`

## 裁决

| 事项 | 本阶段 | 理由（一句话） |
|------|:------:|----------------|
| 五产品一次全拆 | ❌ **不批** | 仅已点名单产品；禁止一次五服务 |
| ADR-09 Accepted（诊断 MVP） | ✅ | 第 4 步 |
| ADR-09 Accepted（Pi Thin） | ✅ | #443；长驻不含 |
| ADR-09 Accepted（FDE） | ✅ | #448；长驻不含 |
| ADR-09 Accepted（本体） | ✅ | `ADR09_NEXT_ONTOLOGY_DECISION.md`；长驻不含；不含控制面 |
| 对外 E4（窄） | ✅ | #436 |
| 控制面拆 | ❌ **不批** | 批句已写不含；须另点名 |
| compose 长驻 | ❌ **不批** | 本体批句填默认「不含」 |
| 改生产默认（D1+D2） | ✅ | #431 / #434 |

**进度**：诊断 MVP + Pi Thin + FDE + 本体立项 ✅。控制面 / compose 长驻仍 ❌（`ADR09_REMAINING_PRODUCTS_DRAFT.md`）。  
「继续」**不得**默示批准未点名项。

## 签字

| 角色 | 决定 | 日期 |
|------|------|------|
| 架构决策 owner | ✅ 诊断+Pi+FDE+本体；**仍不授权**控制面/compose 长驻 | 2026-10-27 |
| 业务场景 owner | ✅ 同上（兼任双签） | 2026-10-27 |
