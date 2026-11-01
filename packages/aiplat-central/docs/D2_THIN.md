# aiPlat Central D2 Thin — packaging / compat / security

> **Status**：D2 Thin 工程收口（本地可验）· **非** PG/HA 生产切流  
> 前置：D1 Thin install · A2 versioning · ADR PG/HA Accepted（有条件）

## 决策

1. Central 是五能力中心宿主；D2 Thin = **安装/升级/兼容矩阵/安全基线**，不是多租户/HA 生产宣称。  
2. 兼容矩阵覆盖 Central + Pi + Ontology + Evaluation + FDE。  
3. 安全基线覆盖 token 中间件、admin MFA、各能力 D2 pack、PG/HA authorize **REFUSE** 路径。  
4. PG/HA 仅允许 `environment=local` 演练；`cutover_authorized` 保持 false。  

## 验证

```bash
bash packages/aiplat-central/scripts/d2_local_closeout.sh
# 拆步：
bash packages/aiplat-central/scripts/a2_version_check.sh
bash packages/aiplat-central/scripts/d2_compat_check.sh
bash packages/aiplat-central/scripts/d2_security_check.sh
```

## 非目标

- `cutover_authorized=true`  
- 真实预发 DSN/OIDC live → sign → authorize  
- 五产品全拆 / E4  
