# FDE 现场范围（A1 · 不拆进程）

> 对齐 V2 §4.2 · `ADR09_FDE_BOUNDARY.md`  
> **现场 D1 安装包 / 独立进程长驻 → 另走 ADR**（见 `ADR-DRAFT-fde-field-deploy.md`）

## 现场能力（可做 · 共置或可选独立 one-shot）

| 能力 | 说明 | 入口 |
|------|------|------|
| 项目 / 需求 / 实施 / 任务 | 工作台既有 API | `/api/platform/apps/fde/*` |
| Bundle 导入 | 消费 Pi / 工厂 Artifact Bundle | 既有 export / APP_HOME 路径 |
| 证据导出 | `evidence_export` 契约 v0 | schema 见 `contracts/schemas/` |
| 验收签收 | **唯一** signoff | `POST …/acceptance/signoff` |
| Health | D1 `healthz` + ADR-09 one-shot | `scripts/adr09_fde_optional_phase_health.sh` |

## 明确不做（本阶段）

- 不自建 Runtime / Ontology / Evaluation 引擎  
- 不新开第二套 `acceptance/signoff`  
- 不默认 compose 长驻（BOUNDARY：长驻须另批）  
- 不跨模块读表；只走 API / 事件  
- 不在无 Field-deploy ADR 时宣称「现场可独立交付包」

## 部署形态

```text
默认：Central 宿主共置 FDE API
可选：ADR-09 one-shot / 可选独立进程（非生产默认）
目标：Field D1（本地优先 DB + 安装/备份/回滚）— 需 ADR Accepted
```

## 与 Pi / 评测

- Pi：执行宿主；FDE 消费证据 / `report_id`  
- Evaluation：评测协议另册；FDE 不实现评分引擎  
