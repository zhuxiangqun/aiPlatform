# D4 复核 — contracts 责任分型（2026-10-23）

> 批准：用户「继续」（D3 之后）。方案 §3.4。

## 原则

| 子类 | 本批动作 |
|------|----------|
| 约束正文 / 仍生效 Charter / Pilot / Runbook | **路径保留**；§0 / §3.0 |
| 现行操作清单（Phase5 接入、护航退出） | **路径保留**；§1 操作向入口 |
| 开工勾选（已宣布）/ 扫描 / 烟测 | **路径保留** + **§3.1 降权** |
| 签收包 | **§3.2**；**不删** |
| 无入链且无义务 | 本批 **未找到** 可删/迁 archive 对象 |

## 14 候选裁定（文件名启发式）

| 文件 | R6 |
|------|-----|
| `ORG_*_CHARTER.md`（L5/Channel/K/V/E/H/S） | 保留（约束） |
| `ORG_L5_PILOT_SPEC.md` | 保留（规格） |
| `ORG_M4_SIGNOFF_PACK.md` | 保留 + §3.2 |
| `ORG_L5_PHASE0_KICKOFF_CHECKLIST.md` | 路径保留；§3.1 |
| `FDE_PHASE0_KICKOFF_CHECKLIST.md` | 路径保留；§3.1 |
| `FDE_PHASE1_HITL_SMOKE.md` | §3.1（C3 已降权） |
| `FDE_PHASE5_CUSTOMER_ONBOARDING.md` | 保留；§1 现行操作 |
| `FDE_ESCORT_EXIT_CHECKLIST.md` | 保留；§1 现行操作 |

## 索引变更

- §0：Kickoff 移出主序；补 `ORG_S_WAVE_CHARTER`
- §1：扫描/烟测/Kickoff 移出主序；补 Phase5 / Escort Exit
- §3：拆 3.0 / 3.1 / 3.2

## 未做

- **删除 0** / **迁 archive 0**
- 未改契约正文、未改 CI 路径

## 验收

`docs/contracts/README.md` 可指认：**约束 / 现行操作 / 过程留存 / 签收**。
