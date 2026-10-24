# 五产品落地收口（2026-10-24）

> L1 + Gate1 修订 + Gate2 落地已合入。**D13 已升格客户场景**；**Gate 3 有条件批准（仅 Pi Thin 试点）**。五产品全拆 / 对外 E4 宣传仍未批。

## 已合入（摘要）

| 项 | 证据 |
|----|------|
| 首切片 WP0–WP5 / E3 | PR [#381](https://github.com/zhuxiangqun/aiPlatform/pull/381) → `5bfdb86` |
| MB-02 models 模板 | [#382](https://github.com/zhuxiangqun/aiPlatform/pull/382) |
| MB-05 emit opt-in | [#383](https://github.com/zhuxiangqun/aiPlatform/pull/383) |
| MB-01 再核实 + MB-03 RFC + MB-04 清单 | [#384](https://github.com/zhuxiangqun/aiPlatform/pull/384) |
| inflation 豁免退役（首切片） | PR [#385](https://github.com/zhuxiangqun/aiPlatform/pull/385) → `a4c4e0c` |
| Gate2 批准 + MB-03 SQLite + MB-01 Facade | PR [#387](https://github.com/zhuxiangqun/aiPlatform/pull/387) → `5b56477` |
| Gate2 inflation 豁免退役 | PR [#388](https://github.com/zhuxiangqun/aiPlatform/pull/388) → `3530d9a` |
| MB-01 agent interfaces | PR [#389](https://github.com/zhuxiangqun/aiPlatform/pull/389) → `e0b089a` |
| D13 升格 + Gate3 有条件批准（文书） | PR [#391](https://github.com/zhuxiangqun/aiPlatform/pull/391) → `364f319` |
| Gate3/D13 inflation 豁免退役 | PR [#392](https://github.com/zhuxiangqun/aiPlatform/pull/392) → `3afc58e`：`exemptions: []` |
| CLOSEOUT 引用 #392 | PR [#393](https://github.com/zhuxiangqun/aiPlatform/pull/393) → `d1d2ccb` |
| G3-1 Pi Thin 试点接线 | PR [#394](https://github.com/zhuxiangqun/aiPlatform/pull/394) → `028f922`：`scripts/gate3_pi_thin_pilot.sh` + env + 回滚演练 |
| G3-2/G3-3 compose + Bundle 优先回滚 | PR [#396](https://github.com/zhuxiangqun/aiPlatform/pull/396) → `79dc33a`：`compose.gate3-pi-thin.yml` + `AIPLAT_HTTP_HOST` |
| Gate3 Phase B（Bundle + 证据） | PR [#398](https://github.com/zhuxiangqun/aiPlatform/pull/398) → `f92897d`：`GATE3_PI_THIN_PHASE=b` + `emitSliceEvidenceEvent` |
| Gate3 Phase C（JSONL → 诊断 ingest） | PR [#400](https://github.com/zhuxiangqun/aiPlatform/pull/400) → `30e8154`：`GATE3_PI_THIN_PHASE=c` |
| Gate3 Phase D（FDE 绑 report_id） | PR [#402](https://github.com/zhuxiangqun/aiPlatform/pull/402) → `58ac428`：`GATE3_PI_THIN_PHASE=d` |
| Gate3 Phase E（lock-service Bundle） | PR [#404](https://github.com/zhuxiangqun/aiPlatform/pull/404) → `a9790f7`：`GATE3_PI_THIN_PHASE=e` |
| Gate3 Phase F（HTTP ⑥b 签收） | PR [#405](https://github.com/zhuxiangqun/aiPlatform/pull/405) → `4d47ae2`：`GATE3_PI_THIN_PHASE=f` |
| ADR-09 全拆/E4 草案 | PR [#406](https://github.com/zhuxiangqun/aiPlatform/pull/406) → `f6a3a9a`：**Proposed**（非落地） |
| Gate3 观察窗口（后修订同日双端） | PR [#408](https://github.com/zhuxiangqun/aiPlatform/pull/408) → `d859559`；同日双端关闭见本批 OBS/ROLLBACK |
| 观察复跑脚本 + mid-window | PR [#409](https://github.com/zhuxiangqun/aiPlatform/pull/409) → `1626b28`：`gate3_observation_rerun.sh` |
| 观察同日双端关闭 | PR [#412](https://github.com/zhuxiangqun/aiPlatform/pull/412) → `9a6471b` |
| ADR-09 §10 再闭合 + ADR-10 Accepted | PR [#413](https://github.com/zhuxiangqun/aiPlatform/pull/413) → `ca03f00`：`ADR09_S10_DRIVER_CLOSURE.md` + 诊断 MVP |
| CLOSEOUT 引用 #412/#413 | PR [#414](https://github.com/zhuxiangqun/aiPlatform/pull/414) |
| ADR-10 接线 Phase A | PR [#415](https://github.com/zhuxiangqun/aiPlatform/pull/415) → `80cc8e2`：沙箱 ingest→report；禁生产默认切换 |
| ADR-10 接线 Phase B | PR [#417](https://github.com/zhuxiangqun/aiPlatform/pull/417) → `01f34da`：compose 一键烟测；daemon 本机 skip |

## Gate 2 / D13 / Gate 3

| 项 | 状态 |
|----|------|
| Gate 2 | ✅ 已落地 |
| D13 | ✅ 客户场景 `fp-customer-lock-service-bundle-pi-diag-001`（江苏锁安 / lock-service）；见 `D13_CUSTOMER_ENDORSEMENT.md` |
| Gate 3 | ✅ **有条件** — Pi Thin A–F + 观察**同日双端已关闭**（#412）；ADR-09 前置 #1–#2 齐，#4–#5 未齐 |
| 第二产品拆分 | ✅ **有条件 Accepted**（ADR-10）；Phase A/B [#415](https://github.com/zhuxiangqun/aiPlatform/pull/415)/[#417](https://github.com/zhuxiangqun/aiPlatform/pull/417)；≠ 改生产默认 / 长驻微服务 |
| 五产品全拆 / 对外 E4 宣传 | ❌ 未授权（ADR-09 仍 Proposed） |

## 运维备忘

- Pi models：`~/.pi/agent/models.json`（模板见 `packages/aiplat-pi-runtime/models.json.example`）  
- 证据发射：`AIPLAT_SLICE_EVIDENCE=1`（默认关）  
- 证据存储：默认 SQLite；`AIPLAT_SLICE_EVIDENCE_STORE=file` 回退  
- Gate3 试点：`bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh`；Phase B–F：`GATE3_PI_THIN_PHASE=b|c|d|e|f bash ...`；可选 compose（见 `GATE3_PI_THIN_PILOT.md`）  
