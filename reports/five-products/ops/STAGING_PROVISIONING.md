# Staging 供给包（远程预发 · 非本机 Option B）

> **用途**：旧笔记本 / 闲置机 / 免费云上搭**独立**预发，供复审填 [`STAGING_READY.md`](./STAGING_READY.md)。  
> **不是** [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)。证据环境名必须是 `staging`（或 `prod-canary`），**禁止** `local` / `scaffold`。  
> **不**自动改 `staging_ready`；齐套后人工更新 STAGING_READY + 复审 Outcome。  
> **2026-11-01 决策**：继续 defer — **本包不实施、不买服务器**；下次看 [`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md)。

## 目标拓扑（最小）

| 组件 | 建议 | 备注 |
|------|------|------|
| 主机 | 独立机器（非日常开发本机） | 方案 A 旧机 / 方案 C 免费云 |
| Postgres 16+ | 独立库 `aiplat_staging` + 最小权限用户 | TLS；开启备份或可证明 PITR/快照 |
| Keycloak（或兼容 OIDC） | realm + client + 测试用户；admin MFA | issuer HTTPS 可达 |
| aiPlat Central | 指向上述 DSN/OIDC | 勿复用开发 `$AIPLAT_HOME` 数据 |

## 与本机 Option B 的对照（防混淆）

| | Option B（本机） | 本供给包（预发） |
|--|------------------|------------------|
| `environment` | `local` | `staging` |
| PG 例 | `127.0.0.1:5433` | 预发主机名/内网 IP |
| OIDC | Keycloak `:8081` 本机 | 预发 issuer URL |
| 证据签名 | `local_signed` | 可走 `production_signed`（sign 流程后） |
| authorize | **禁止** | 仅 checklist 全 ✅ + signed live 后 |

## 建议安装步骤（草稿 · 人工执行）

```bash
# 在预发主机上（示例；按发行版调整）
# 1) Postgres
# 2) Keycloak / OIDC
# 3) 导出给操作者（勿提交密钥进 git）:
export AIPLAT_LIVE_DRILL_ENV=staging
export AIPLAT_LIVE_DRILL_OPERATOR=$USER
export AIPLAT_PG_DSN='postgresql://aiplat_stg:***@staging-host:5432/aiplat_staging?sslmode=require'
export AIPLAT_OIDC_ISSUER='https://staging-host/realms/aiplat'
# 4) 从工作站（有仓库处）:
bash scripts/ops_pgha_live_kickoff.sh   # 期望 can_record=true 后才进入 record
```

Compose 可参考本机 `compose.local-staging.yml`，但必须：

- 改网络/端口/卷到预发主机路径  
- 改默认密码  
- 文档标明 `environment=staging`  
- **不要**把预发 compose 默认值写回 Option B 文档当 local

## 复审材料清单

- [ ] 主机身份（主机名、谁拥有、是否与开发隔离）  
- [ ] PG DSN（红acted 可进 runlog；完整值只在操作者密钥库）  
- [ ] OIDC issuer + client id（无 client secret 进 git）  
- [ ] 备份/快照证明（截图或脚本输出）  
- [ ] 变更窗口 + 回滚预案一段话  

齐套后打开 [`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md) 填 Outcome。
