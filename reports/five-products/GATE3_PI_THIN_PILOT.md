# Gate3 试点边界：Pi Thin 独立部署

> **批准**：`GATE3_DECISION.md` G3-1  
> **场景**：`fp-customer-lock-service-bundle-pi-diag-001`  
> **非目标**：拆 aiPlat 控制面 / 诊断中台 / 五产品全拆

## 1. 目标

验证 Pi Thin **执行宿主**可在与 aiPlat 控制面**进程分离**的情况下：

1. 加载已签名/已导出 Bundle；  
2. 使用**独立运行密钥/环境变量前缀**（与控制面凭据分离）；  
3. 按既有离线/拒权策略 fail-closed；  
4. 证据仍可被诊断 MVP ingest（路径可经文件/HTTP 薄接线，不新建诊断微服务）。

## 2. 允许改动的路径（冻结清单）

| 路径/产物 | 允许 |
|-----------|:----:|
| `packages/aiplat-pi-runtime/**` 启动/README/env 示例 | ✅ |
| `reports/five-products/GATE3_*` / 运维备忘 | ✅ |
| 可选：仓库根或 `packages/aiplat-pi-runtime` 下 **试点** compose/脚本（明确 `gate3-pi-thin` 名） | ✅ |
| `aiPlat-core` / `aiPlat-platform` 拆服务、搬目录 | ❌ |
| 改生产默认共部署路径为强制独立 | ❌（试点并行） |

## 3. 配置与密钥

| 项 | 约定 |
|----|------|
| 控制面 | 继续既有 `AIPLAT_*` / 平台配置 |
| Thin 试点 | 使用文档化的独立 env 文件（例：`.env.gate3-pi-thin`）；**禁止**复用生产控制面密钥文件 |
| Bundle | 仍由 aiPlat `export_pi_bundle` / 切片导出产生；试点只消费产物 |

## 4. 健康与回滚

| 项 | 做法 |
|----|------|
| 健康 | 进程存活 + 能加载 Bundle 清单；不把「无证据」报成 healthy |
| 回滚优先 | Bundle 版本回滚（落地方案 A3.5） |
| 备选 | 停试点容器/进程，切回共置 Thin |

## 5. 验收（试点 DoD）

- [ ] 试点环境与控制面**不同进程**可启动 Thin  
- [ ] 密钥/env 与控制面文件分离（检查清单有路径）  
- [ ] 跑通客户场景主路径技术夹具（sample-app 可）且诊断证据规则不降标  
- [ ] 回滚演练记录写入本目录或切片证据包索引  
- [ ] 无新增跨域私有 import / 无搬仓  

## 6. 后续代码 PR 约束

- 单 PR 遵守 physical merge inflation；超限则拆 PR 或短豁免并退役  
- 先文书合入，再开接线 PR（可同里程碑）  
