# 五产品首切片落地收口（2026-10-24）

> L1 + Gate1 修订内工作已合入 main。**Gate 2 / D13 已批准**（见 `GATE2_DECISION.md`）。Gate 3 仍未批。

## 已合入（摘要）

| 项 | 证据 |
|----|------|
| 首切片 WP0–WP5 / E3 | PR [#381](https://github.com/zhuxiangqun/aiPlatform/pull/381) → `5bfdb86` |
| MB-02 models 模板 | [#382](https://github.com/zhuxiangqun/aiPlatform/pull/382) |
| MB-05 emit opt-in | [#383](https://github.com/zhuxiangqun/aiPlatform/pull/383) |
| MB-01 再核实 + MB-03 RFC + MB-04 清单 | [#384](https://github.com/zhuxiangqun/aiPlatform/pull/384) |
| inflation 豁免退役（首切片） | PR [#385](https://github.com/zhuxiangqun/aiPlatform/pull/385) → `a4c4e0c`：`exemptions: []` |
| Gate2 批准文书 + MB-03 SQLite + MB-01 首批 Facade | PR [#387](https://github.com/zhuxiangqun/aiPlatform/pull/387) → `5b56477` |
| Gate2 inflation 豁免退役 | 本 PR：`exemptions: []`（合入 #387 后立即退役） |

## Gate 2 已批可做 / 已做

| 项 | 状态 |
|----|------|
| Gate 2 / D13（内部背书） | ✅ `GATE2_DECISION.md` |
| MB-04 正式 R | ✅ `ROLES.md` + `MB04_OWNER_TRANSFER.md` |
| MB-03 存储迁移（方案 B） | ✅ 默认 SQLite；`AIPLAT_SLICE_EVIDENCE_STORE=file` 回退 |
| MB-01 core 解耦（首批） | ✅ `core/apps/fde` knowledge/ontology 调用改经 CoreFacade；残留：`agent.py` interfaces、`prompts/` register |

## 明确未做 / 未批

| 项 | 状态 |
|----|------|
| Gate 3 / 拆部署 / 对外产品化 | ❌ 未授权 |
| MB-01 全量清零（interfaces/prompts/archive） | 后续小批；不阻塞 Gate2 交付 |

## 临时 R → 正式表

见 `MB04_OWNER_TRANSFER.md` / `ROLES.md`（2026-10-24 生效）。

## 运维备忘

- 本机 Pi 告警：`~/.pi/agent/models.json` 须含实际 `ollama list` id（模板见 `packages/aiplat-pi-runtime/models.json.example`）  
- 证据发射：`AIPLAT_SLICE_EVIDENCE=1`（默认关）  
- 证据存储：默认 SQLite（`~/.aiplat/five_products_slice/evidence/evidence.db`）；回退 `AIPLAT_SLICE_EVIDENCE_STORE=file`  
