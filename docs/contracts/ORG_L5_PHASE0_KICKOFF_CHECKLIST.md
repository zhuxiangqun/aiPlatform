# Org L5 — Phase 0 开工清单

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-P0-KICKOFF-2026-09` |
| 版本 | **v1.0** |
| 日期 | 2026-09-18 |
| 关联 | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) · [`ORG_L5_PILOT_SPEC.md`](./ORG_L5_PILOT_SPEC.md) |
| 状态 | ☑ **P0 已生效** · ☑ **Phase 1 开工 2026-09-18** |

**纪律**：勾完 §E 且决策记录勾选 P0 生效后，方可开始 Phase 1 **改码**。本清单本身不授权写生产系统（见 D3）。

---

## A. 文档齐套

| # | 项 | 状态 |
|---|----|------|
| A1 | Charter v1.0 已审阅 / Go | ☑ |
| A2 | Pilot Spec v1.0 已审阅 | ☑ |
| A3 | Decision Record 五问已决 | ☑ |
| A4 | 本清单 Owner / 复核人已填 | ☑ 会话确认 |

Owner：工程（会话确认）　复核：产品（会话确认）

---

## B. 边界与冲突检查

| # | 项 | 状态 |
|---|----|------|
| B1 | 已确认本文 L5 ≠ 工厂 release L5 | ☑ |
| B2 | 已确认不替代 FDE Workbench Contract | ☑ |
| B3 | 已确认 Phase 1 不往 harness 塞 it-ops 字符串分叉 | ☑ |
| B4 | 已确认 locate 不做任意 SQL | ☑ |
| B5 | D4 模块位置已决（独立 org） | ☑ |

---

## C. 试点前置（代码侧盘点，只读）

| # | 项 | 证据命令 / 路径 | 状态 |
|---|----|-----------------|------|
| C1 | it-ops Action 种子存在 | `aiPlat-core/core/workspace_seeds/actions/it_ops_alert_lifecycle.yaml` | ☑ |
| C2 | abox_connector 可扩展点已读 | `core/apps/fde/service/abox_connector.py` | ☑（P0 文档已锚定） |
| C3 | locate / quality API 已存在 | `action_routes.py` governance/* | ☑ |
| C4 | GraphIndex + ActionRegistry 可用 | 现有 FDE⑦ 演示路径 | ☑ |
| C5 | 审计 schema 可挂 OrgRun 引用 | `audit_schema.v1.yaml` | ☑ |

---

## D. Phase 1 设计冻结（开工前填）

| # | 项 | 填写 |
|---|----|------|
| D1 | fetch API 挂载 | **Phase 1**：路由可暂挂 `/api/platform/apps/fde/.../governance/fetch`；**逻辑**进可迁至 `core/apps/org` 的服务；**M2 前**收敛到 `apps/org` |
| D2 | 沙箱 stub 形态 | 内存 / 文件 stub（`AIPLAT_ORG_IO_MODE=sandbox`） |
| D3 | `AIPLAT_ORG_IO_MODE` 默认值 | **`sandbox`** |
| D4 | 是否做 D5 data-gov 薄切片 | **是** |
| D5 | Phase 1 PR 验收用例列表（≥3） | (1) it-ops fetch stub OK (2) 无配置明确错误 (3) data-gov 只读 fetch OK (4) live 默认拒绝 |

---

## E. P0 生效签字（缺一不可）

| # | 项 | 签字 / 日期 |
|---|----|-------------|
| E1 | 架构：同意 Charter 验收定义与非目标 | 会话确认 / 2026-09-18 |
| E2 | 产品：同意试点故事与 KPI | 会话确认 / 2026-09-18 |
| E3 | 工程：同意 D3 非 live + 模块归属 | 会话确认 / 2026-09-18 |
| E4 | 决策记录已勾选「P0 生效」 | ☑ 2026-09-18 |

**已宣布**：  
> Org L5 P0 于 2026-09-18 生效；Phase 1 仅沙箱 I/O；主试点 it-ops；并行 data-gov 只读 fetch 薄切片；对外话术仍为 L3 + 原型，直至 M4。

---

## F. Phase 1 开工勾选（P0 生效后）

| # | 项 | 状态 |
|---|----|------|
| F1 | §E 已完成 | ☑ |
| F2 | §D 设计冻结已填 | ☑ |
| F3 | 建分支 / 任务板条目 | ☑ 会话开工 |
| F4 | **宣布 Phase 1 开工** | ☑ **2026-09-18** |

---

## G. 第一批改码范围（备忘；§F4 宣布后授权）

仅 Phase 1 宣布后：

1. 扩展 connector：`fetch_by_entity` + sandbox stub  
2. Facade + 路由：`governance/fetch`（暂挂 fde）→ 逻辑可迁  
3. data-gov 只读薄切片测试  
4. 单测 + 文档诚实更新（PPT B4.4a ⑦、CAPABILITIES）  
5. **不做** OrgGoal 调度器（属 Phase 2）  
6. **不做** `IO_MODE=live`
