# 控制面部署边界清单（ADR-09 下一单产品后续 #1）

- **状态**：**清单已立** · 2026-10-27 — 授权真源 `ADR09_NEXT_CONTROL_PLANE_DECISION.md`（#458）  
- **产品**：控制面（aiPlat）  
- **对照**：`ADR-02-control-plane-draft.md` · `contracts/identity-policy-fp-001.md` · `contracts/enablement-matrix.md`  
- **不含**：compose 长驻；超边界 E4；第二 Identity/Policy 权威；一次大搬仓

## As-Is（当前）

| 面 | 现状 |
|----|------|
| 进程 | platform / core 控制面 API **共进程或同部署单元**挂载各 apps；Identity 注入 `require_auth` / `_resolve_identity` |
| 权威 | Identity / Policy **生产者=aiPlat**（ADR-02）；PolicyGate 为权限唯一执行点 |
| 消费方 | FDE / ontology-editor / 诊断路径等经控制面 HTTP；Pi Thin 可选独立进程仍消费身份上下文 |
| Compose | 无控制面「长驻拆分」profile；随仓库默认部署 |
| 回滚 | 保持共部署；关任何实验性独立控制面进程 |

## To-Be（单产品立项后 · 分 PR）

| 面 | 目标 | 回滚 |
|----|------|------|
| 进程 | 控制面可作**正式可选**独立进程（Identity·Policy·apps 挂载面）；发布节奏可独立 | 停独立进程；切回共部署 |
| Identity | **仍单一权威**；禁止并行外部 IAM / 第二 PolicyGate | ADR-02 路径 |
| 端口 | env 配置监听；禁止硬编码业务名进 core | 改回默认共置 |
| Compose | 仅允许 one-shot / 显式试点；**长驻须另批** | `down -v` |
| 与其余四产品 | 消费者关系不变；不扩大其边界收口 | 既有路径 |

## 分 PR 建议顺序（各 ≤ inflation）

| 序 | 主题 | 非目标 |
|----|------|--------|
| A | ✅ 本清单 + SCHEDULE / LANDING 引用立项 | 搬仓 |
| B | ✅ `aiPlat-platform/README.md` + `control_plane_optional.env.example`：「正式可选」用语 | 改生产默认强制独立；compose 长驻；双重 Identity |
| C | 可选 one-shot 健康 / 启动别名（若需要）→ 共部署真源不改名 | compose 长驻；第二 PolicyGate |

## 回滚总则

1. 停任何控制面独立进程 / `compose … down -v`  
2. 切回共部署 platform 挂载路径  
3. Identity / Policy 权威仍为 aiPlat（不启用平行权威）  
4. 详见后续 BOUNDARY C / rollback 文书（若增补）
