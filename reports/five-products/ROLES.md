# 五产品域角色与临时 R

> 与 [L1_AUTHORIZATION.md](./L1_AUTHORIZATION.md) §3、[DECISIONS_AND_AUTHORIZATIONS.md](./DECISIONS_AND_AUTHORIZATIONS.md) A5 同步。  
> **日期**：2026-10-23（L1 确认日补全安全/测试/运维兼任）

## 关键角色

| 角色 | 任职 |
|------|------|
| 架构决策 owner | 本仓库维护者（L1 授权确认人） |
| 业务场景 owner | 同上（兼任） |
| 业务验收人 | 同上（兼任） |
| Gate 1 / 暂停 / 恢复 | 架构 × 业务联合签署（兼任则一人双签并注明） |
| 安全/身份 reviewer | **架构决策 owner 兼任**（见授权 A5：可预签；高风险一票否决） |
| 测试/验收 owner（过程） | **业务验收人兼任** |
| 运维 owner（隔离） | **架构决策 owner 兼任** |

## 临时产品 R（§2.4）

| 产品域 | 临时 R | 正式 R（待补） |
|--------|--------|----------------|
| aiPlat | 架构决策 owner | |
| Pi | 架构决策 owner | |
| 本体 | 架构决策 owner（本场景未使用本体时不得标「已具备」） | |
| FDE | 业务场景 owner | |
| 诊断 | 架构决策 owner | |

正式 owner：授权延期至 **WP1 结束**仍可用临时 R；到位后填「正式 R」并复核签字。  
转正步骤与签字表：[MB04_OWNER_TRANSFER.md](./MB04_OWNER_TRANSFER.md)（2026-10-24 清单；**尚未转正**）。
