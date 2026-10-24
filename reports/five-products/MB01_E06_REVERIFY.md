# MB-01 / E-06 再核实（2026-10-24）

> 顺序：首切片合入后按 MODULE_BACKLOG 推进到 MB-01。  
> **范围**：只做事实再核实与文档收口；**不**开 Gate 2，**不**改生产默认路径，**不**全仓解耦搬迁。

## 1. 分层结果（以代码为准）

| 层 | 命令意图 | 结果 |
|----|----------|------|
| **platform** `aiPlat-platform/apps/fde` | `from core.harness` / `knowledge\|ontology` | **0 命中** — HTTP 层经 `core.api.core_facade` |
| **core** `aiPlat-core/core/apps/fde` | `from core.harness.knowledge` / `ontology_engine` / `knowledge_pipeline` | **仍有多处** — 业务服务直连 harness（E-06 技术债在此） |

示例（非穷尽）：`usage_signal.py`→`DomainRouter`；`clarify_dialog.py`/`abox_connector.py`/`k_wave_*`/`governance_deepen.py`→`GraphIndex`；`ontology_code_suggestions.py`→`VersionedOntologyStore` 等。

平台层「无直连」**不等于** E-06 全仓关闭。

## 2. 与 WP0 盘点对照

| 来源 | 原结论 | 再核实 |
|------|--------|--------|
| `wp0-inventory.md` E-06 | `core/apps/fde/service/*` 多处直连 | **仍成立（core 层）**；platform 层已干净 |
| MODULE_BACKLOG MB-01 | 须 Gate 2 解耦 | **仍须 Gate 2（+ D13）** 方可改 core 调用方 |

## 3. 结论（本步）

| 项 | 决定 |
|----|------|
| MB-01 代码改造 | **未开工** — 需 Gate 2；目标：core/apps/fde 对 knowledge/ontology 经 CoreFacade（或已有公开 API），禁平行直连 |
| 文档 | inventory：区分 platform As-Is / core Known Gap |
| Gate 2 | **仍维持**（缺 D13）；本核实 ≠ 批准扩大 |
| 残留风险 | platform 新增路由须继续只走 Facade；core 解耦按调用点分批，禁止一次搬仓 |

## 4. 建议解耦顺序（仅设计，未授权实施）

1. 盘点 `core/apps/fde` 中 `harness.knowledge*` / `ontology_engine*` / `knowledge_pipeline*` caller 清单  
2. 对已有 Facade 导出做映射；缺口补 Facade 唯一入口  
3. 逐文件改 import → Facade；每批跑 architecture / constitution  
4. 禁止借机搬目录或拆微服务  

## 5. 下一顺序项

- **MB-03**：诊断 MVP 持久化 — 独立 RFC 草案（可写，不实现）→ `MB03_EVIDENCE_STORE_RFC.md`  
- **MB-04**：正式 owner 转正 — 组织动作  
- **Gate 2 / MB-01 实施**：仍待 D13 + 联签  
