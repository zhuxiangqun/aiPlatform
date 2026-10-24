# 模块化 / Gate3 Backlog

> **Gate 2 已落地**；**Gate 3 有条件批准** — Phase A/B/C 已接线；**Phase D 已批**（`GATE3_PHASE_D_DECISION.md`）。  
> 五产品全拆 / 对外 E4 仍未批。

| ID | 边/问题 | 严重度 | 建议手法 | 后置条件 |
|----|---------|--------|----------|----------|
| MB-01 | FDE→harness knowledge/ontology | 中 | CoreFacade | **已落地** |
| MB-02 | Pi models.json | 低 | 运维模板 | **已对齐** |
| MB-03 | 诊断证据持久化 | 中 | SQLite 默认 | **已实现** |
| MB-04 | 正式 R 转正 | 中 | ROLES | **已转正** |
| MB-05 | Pi emit opt-in | 低 | slice_evidence_emit | **已接线** |
| G3-1 | Pi Thin 独立部署试点 | 中 | `GATE3_PI_THIN_PILOT.md` 清单内接线 | **已接线** [#394](https://github.com/zhuxiangqun/aiPlatform/pull/394) → `028f922` |
| G3-2 | 试点 compose / 启动说明 / env | 低 | `compose.gate3-pi-thin.yml` + README | **已接线** [#396](https://github.com/zhuxiangqun/aiPlatform/pull/396) → `79dc33a` |
| G3-3 | 回滚：Bundle 优先；Runtime 备选 | 低 | `GATE3_PI_THIN_ROLLBACK_DRILL.md` | **已接线** [#396](https://github.com/zhuxiangqun/aiPlatform/pull/396) → `79dc33a` |
| G3-B1 | 试点消费 export Bundle | 中 | `GATE3_PI_THIN_PHASE=b` | **已接线** [#398](https://github.com/zhuxiangqun/aiPlatform/pull/398) → `f92897d` |
| G3-B2 | HTTP Thin 切片证据发射 | 中 | `emitSliceEvidenceEvent` | **已接线** [#398](https://github.com/zhuxiangqun/aiPlatform/pull/398) → `f92897d` |
| G3-B3 | Phase B 脚本断言证据 | 低 | pilot exit 4/5/6 | **已接线** [#398](https://github.com/zhuxiangqun/aiPlatform/pull/398) → `f92897d` |
| G3-C1 | JSONL → 诊断 MVP ingest | 中 | `ingest_slice_evidence_from_jsonl` | **已接线** [#400](https://github.com/zhuxiangqun/aiPlatform/pull/400) → `30e8154` |
| G3-C2 | 诊断报告 ok 断言 | 中 | `build_slice_diagnosis_report` | **已接线** [#400](https://github.com/zhuxiangqun/aiPlatform/pull/400) → `30e8154` |
| G3-C3 | `GATE3_PI_THIN_PHASE=c` | 低 | pilot 沙箱 `AIPLAT_HOME` | **已接线** [#400](https://github.com/zhuxiangqun/aiPlatform/pull/400) → `30e8154` |
| G3-D1 | FDE 验收须绑 report_id | 中 | `validate_slice_signoff_reports` | **已接线**（本 PR） |
| G3-D2 | 负向拒签 + 正向绑定 | 中 | `GATE3_PI_THIN_PHASE=d` | **已接线**（本 PR） |
| G3-D3 | 沙箱验收绑定落盘 | 低 | `$AIPLAT_HOME/.../acceptance/` | **已接线**（本 PR） |

**明确不做**：全仓搬目录、五产品一次全拆、诊断全功能、启用本体进主路径（除非另改 WP1/ADR）。
