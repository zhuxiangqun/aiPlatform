# Gate 2 决定（2026-10-24）

**结论：批准进入 Gate 2（有条件）。**

## 依据

| 项 | 内容 |
|----|------|
| 授权人 | 架构决策 owner × 业务场景 owner（兼任：本仓库维护者） |
| 对话授权 | 2026-10-24 用户明示「全部可以授权」 |
| 真源 | 落地方案 v1.3 §6 Gate 2；本文件为书面生效记录 |
| 取代 | [`GATE2_RECOMMENDATION.md`](./GATE2_RECOMMENDATION.md) 之「维持」建议（该文件保留为历史） |

## D13

**（2026-10-24 升格）** 原内部场景背书已被客户场景替换 **supersede**：  
见 [`D13_CUSTOMER_ENDORSEMENT.md`](./D13_CUSTOMER_ENDORSEMENT.md) + [`SCENE.md`](./SCENE.md)（`fp-customer-lock-service-bundle-pi-diag-001` / 江苏锁安 / `lock-service`）。  

Gate 2 **技术批准范围仍有效**；D13 段以升格文件为准。历史内部 id 仅对照。

## 批准范围（可执行）

| ID | 范围 |
|----|------|
| MB-01 | `core/apps/fde` → harness knowledge/ontology 直连改为经 CoreFacade（或已有公开 API）；分批；禁止搬仓/拆微服务 |
| MB-03 | 按 `MB03_EVIDENCE_STORE_RFC.md` **方案 B（SQLite）** 实现；默认 sqlite，可用 env 回退 file |
| MB-04 | 正式 R 转正：五产品正式 R = 原临时 R 任职（本仓库维护者兼任），见 `ROLES.md` / `MB04_OWNER_TRANSFER.md` |
| 维护 | 切片路径与契约文档可持续演进 |

## 明确不在本次批准内

| 项 |
|----|
| Gate 3 / 独立部署拆分 |
| 诊断全功能 / Evaluation 二期 |
| 启用本体进首切片主路径（除非另改 WP1） |
| 对外宣称五产品已全面产品化 |
| 改与本 Gate 无关的生产默认路径 |

## 签署

架构 × 业务（兼任）：**批准进入 Gate 2** · 2026-10-24  
诊断临时 R（兼任）：**批准 MB-03 方案 B 实现** · 2026-10-24  
