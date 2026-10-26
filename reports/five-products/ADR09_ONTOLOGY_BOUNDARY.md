# 本体部署边界清单（ADR-09 下一单产品后续 #1）

- **状态**：**清单已立** · 2026-10-27 — 授权真源 `ADR09_NEXT_ONTOLOGY_DECISION.md`（#453）  
- **产品**：本体（Ontology）  
- **对照**：`ADR-01-boundaries-draft.md` · `ADR-03-data-owners-draft.md` · DomainRouter  
- **不含**：compose 长驻；控制面拆；超边界 E4；第二套域注册表；一次大搬仓

## As-Is（当前）

| 面 | 现状 |
|----|------|
| 进程 | 本体读写与控制面**共进程**（core `DomainRouter` / GraphIndex；platform 可选挂载 editor） |
| 配置权威 | `~/.aiplat/ontologies/{domain_id}.yaml` + `registry.json`（经 `DomainRouter`） |
| HTTP（编辑） | `registry/apps.yaml` → `ontology-editor` → `/api/platform/apps/ontology-editor` |
| 内核约束 | core/infra **禁止**硬编码业务域名；扩展走 YAML / DomainRouter |
| Compose | 无本体专用长驻 profile；随控制面共部署 |
| 回滚 | 保持共部署；关任何实验性独立进程即可 |

## To-Be（单产品立项后 · 分 PR）

| 面 | 目标 | 回滚 |
|----|------|------|
| 进程 | 本体可作**正式可选**独立进程（配置目录 + 只读/查询面可分离）；发布节奏可独立 | 停独立进程；切回控制面共部署 |
| 配置 | 继续 `AIPLAT_HOME/ontologies`（或显式子目录）；**禁止**平行 registry | 指回共部署 home |
| 路由 | editor 前缀不变；查询/健康若暴露须 env 端口，禁止硬编码进 core | 指回共部署挂载 |
| Compose | 仅允许 one-shot / 显式试点；**长驻须另批** | `down -v` |
| 与 FDE / Pi / 诊断 | 消费者关系不变；不扩大其范围 | 既有路径 |

## 分 PR 建议顺序（各 ≤ inflation）

| 序 | 主题 | 非目标 |
|----|------|--------|
| A | ✅ 本清单 + SCHEDULE / CLOSEOUT 引用立项 | 搬仓 |
| B | README / env.example：「正式可选」独立部署用语（非强制默认独立） | 改生产默认强制独立；compose 长驻；拆控制面 |
| C | 可选 one-shot 健康 / 启动别名（若需要）→ 共部署真源不改名 | 第二套 DomainRouter；compose 长驻 |

## 回滚总则

1. 停任何本体独立进程 / `compose … down -v`  
2. 切回控制面共部署 DomainRouter / ontology YAML / editor 路径  
3. 配置权威仍为 `~/.aiplat/ontologies`（不启用平行 registry）  
4. 详见后续 `ADR09_ONTOLOGY_ROLLBACK`（若 BOUNDARY C 增补）
