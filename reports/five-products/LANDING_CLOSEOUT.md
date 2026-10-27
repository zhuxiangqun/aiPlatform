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
| ADR-10 接线 Phase B | PR [#417](https://github.com/zhuxiangqun/aiPlatform/pull/417) → `01f34da`：compose 一键烟测（后补宿主/compose PASS 见 #422） |
| CLOSEOUT 引用 #417 | PR [#418](https://github.com/zhuxiangqun/aiPlatform/pull/418) → `61d9d0b` |
| ADR-09 前置 #4/#5 草案 | PR [#419](https://github.com/zhuxiangqun/aiPlatform/pull/419) → `c2c1d45`：`ADR09_E4_*` + 干净环境脚本；**≠** Accepted / 对外 |
| CLOSEOUT 引用 #419 | PR [#420](https://github.com/zhuxiangqun/aiPlatform/pull/420) → `c20edb7` |
| ADR-09 前置 #3 + #5 PASS 归档 | PR [#422](https://github.com/zhuxiangqun/aiPlatform/pull/422) → `1a96f40`：on-call 再确认 + 宿主/compose PASS；**≠** Accepted / 对外 |
| ADR-09 前置联签 + 停泊 | PR [#424](https://github.com/zhuxiangqun/aiPlatform/pull/424) → `df79936`：`ADR09_PREWORK_COSIGN_PARK.md`；仍 **Proposed**；拒签对外 E4 |
| 全拆/E4/改生产默认延期 | PR [#425](https://github.com/zhuxiangqun/aiPlatform/pull/425) → `0c7ac34`：`ADR09_DEFER_FULL_SPLIT_E4_PROD.md` |
| ADR-10 Phase C 单产品加深 | PR [#426](https://github.com/zhuxiangqun/aiPlatform/pull/426) → `bef8e4a`：双端加深 + 拒切默认；**≠** 第 2–4 步 |
| ADR-10 Phase C compose 残差 | PR [#429](https://github.com/zhuxiangqun/aiPlatform/pull/429) → `907120b`：compose PASS + `down -v` |
| ADR-10 Phase D 仅 D1 | PR [#431](https://github.com/zhuxiangqun/aiPlatform/pull/431) → `ba0243d`：共享 home opt-in；**≠** D2 / E4 / 全拆 |
| ADR-10 D2 签收默认绑定 | PR [#434](https://github.com/zhuxiangqun/aiPlatform/pull/434) → `968f3a7`：`acceptance/signoff` + `PROD_DEFAULT=1`；**≠** E4 / 全拆 / compose 长驻 |
| ADR-09 第 3 步对外 E4（窄） | PR [#436](https://github.com/zhuxiangqun/aiPlatform/pull/436) → `87a49c5`：边界内文案 + CLEAN_ENV 引用；**≠** 全拆 / SLA |
| ADR-09 第 4 步全拆（诊断 MVP） | PR [#438](https://github.com/zhuxiangqun/aiPlatform/pull/438) → `05281fe`：单产品 Accepted |
| BOUNDARY A / B / C | [#439](https://github.com/zhuxiangqun/aiPlatform/pull/439) / [#440](https://github.com/zhuxiangqun/aiPlatform/pull/440) / [#441](https://github.com/zhuxiangqun/aiPlatform/pull/441) → `385d4a8` |
| 建议顺序主轨收口 | `SUGGESTED_ORDER_CLOSEOUT.md`（诊断 MVP 轨结案） |
| 下一单产品 Pi Thin | [#443](https://github.com/zhuxiangqun/aiPlatform/pull/443)–[#446](https://github.com/zhuxiangqun/aiPlatform/pull/446) → `2286cbe`；收口 `ADR09_PI_THIN_BOUNDARY_CLOSEOUT.md` |
| 下一单产品 FDE | [#448](https://github.com/zhuxiangqun/aiPlatform/pull/448)–[#451](https://github.com/zhuxiangqun/aiPlatform/pull/451) → `40891a2`；收口 `ADR09_FDE_BOUNDARY_CLOSEOUT.md` |
| 下一单产品 本体 | [#453](https://github.com/zhuxiangqun/aiPlatform/pull/453)–[#456](https://github.com/zhuxiangqun/aiPlatform/pull/456) → `549b86a`；收口 `ADR09_ONTOLOGY_BOUNDARY_CLOSEOUT.md` |
| 下一单产品 控制面 | [#458](https://github.com/zhuxiangqun/aiPlatform/pull/458)–[#461](https://github.com/zhuxiangqun/aiPlatform/pull/461) → `868a8df`；收口 `ADR09_CONTROL_PLANE_BOUNDARY_CLOSEOUT.md` |
| compose 长驻 | `ADR09_COMPOSE_LONG_RUNNING_DECISION.md`（含；≠ 强制默认） |

## Gate 2 / D13 / Gate 3

| 项 | 状态 |
|----|------|
| Gate 2 | ✅ 已落地 |
| D13 | ✅ 客户场景 `fp-customer-lock-service-bundle-pi-diag-001`（江苏锁安 / lock-service）；见 `D13_CUSTOMER_ENDORSEMENT.md` |
| Gate 3 | ✅ **有条件** — Pi Thin A–F + 观察**同日双端已关闭**（#412）；ADR-09 **Accepted（仅诊断 MVP）** |
| 第二产品拆分 | ✅ ADR-10 + 第 4 步 + BOUNDARY A–C |
| 对外 E4（窄） | ✅ **第 3 步已批**（#436）；边界见 `ADR09_E4_COPY_DRAFT.md` |
| 建议顺序主轨 | ✅ **已收口** — `SUGGESTED_ORDER_CLOSEOUT.md` |
| Pi Thin 单产品 + 边界 A–C | ✅ **已收口** — `ADR09_PI_THIN_BOUNDARY_CLOSEOUT.md` |
| FDE 单产品 + 边界 A–C | ✅ **已收口** — `ADR09_FDE_BOUNDARY_CLOSEOUT.md`（长驻不含） |
| 本体单产品 + 边界 A–C | ✅ **已收口** — `ADR09_ONTOLOGY_BOUNDARY_CLOSEOUT.md`（长驻不含） |
| 控制面单产品 + 边界 A–C | ✅ **已收口** — `ADR09_CONTROL_PLANE_BOUNDARY_CLOSEOUT.md` |
| compose 长驻 | ✅ **已批** — `ADR09_COMPOSE_LONG_RUNNING_DECISION.md`（含；≠ 强制默认） |

## 运维备忘

- Pi models：`~/.pi/agent/models.json`（模板见 `packages/aiplat-pi-runtime/models.json.example`）  
- 证据发射：`AIPLAT_SLICE_EVIDENCE=1`（默认关）  
- 证据存储：默认 SQLite；`AIPLAT_SLICE_EVIDENCE_STORE=file` 回退  
- Gate3 试点：`bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh`；Phase B–F：`GATE3_PI_THIN_PHASE=b|c|d|e|f bash ...`；可选 compose（见 `GATE3_PI_THIN_PILOT.md`）  
