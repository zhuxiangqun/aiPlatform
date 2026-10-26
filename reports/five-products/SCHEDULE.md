# L1→Gate3 日程

| 阶段 | 状态 |
|------|------|
| L1 WP0–WP2 | ✅ |
| Gate 1（修订：完整切片） | ✅ |
| WP3 DESIGN | ✅ |
| WP4 执行 + 证据包 | ✅ |
| WP5 回顾 | ✅ |
| Gate 2 | ✅ **已批准并落地**（PR #387–#389） |
| D13 客户场景 | ✅ **已升格**（江苏锁安 / lock-service；`D13_CUSTOMER_ENDORSEMENT.md`） |
| Gate 3 Phase A | ✅ G3-1/2/3 已接线（#394/#396） |
| Gate 3 Phase B | ✅ Bundle + 证据发射已接线（#398 → `f92897d`；`GATE3_PHASE_B_DECISION.md`） |
| Gate 3 Phase C | ✅ JSONL → 诊断 MVP ingest 已接线（#400 → `30e8154`；`GATE3_PHASE_C_DECISION.md`） |
| Gate 3 Phase D | ✅ FDE 验收绑定 report_id 已接线（#402 → `58ac428`；`GATE3_PHASE_D_DECISION.md`） |
| Gate 3 Phase E | ✅ lock-service Bundle 物化（#404 → `a9790f7`；`GATE3_PHASE_E_DECISION.md`） |
| Gate 3 Phase F | ✅ HTTP ⑥b 签收（#405 → `4d47ae2`；`GATE3_PHASE_F_DECISION.md`） |
| Gate3 观察窗口 | ✅ **同日双端已关闭**（#412） |
| ADR-09 前置 #2 §10 | ✅ 再闭合 2 项（`ADR09_S10_DRIVER_CLOSURE.md`）；扩缩容仍 ⬜ |
| 第二产品拆分 | ✅ ADR-10 **Accepted（有条件）** — 诊断 MVP |
| ADR-10 接线 Phase A | ✅ 清单 + env + 沙箱烟测（`ADR10_DIAGNOSIS_MVP_WIRING_DECISION.md`）；**≠** 改生产默认路径 |
| ADR-10 接线 Phase B | ✅ compose 容器烟测（`ADR10_DIAGNOSIS_MVP_PHASE_B_DECISION.md`）；**≠** 改生产默认 / 长驻微服务 |
| ADR-10 接线 Phase C | ✅ 双端×2 + 拒切默认 + **compose PASS**（`ADR10_PHASE_C_COMPOSE_RERUN.txt`）；**≠** 第 2–4 步 |
| ADR-10 Phase D（第 2 步） | ✅ **仅 D1** 已批 — `ADR10_DIAGNOSIS_MVP_PHASE_D_DECISION.md` |
| ADR-10 D2（第 2 步剩余） | ✅ **已批** — #434 / `ADR10_DIAGNOSIS_MVP_D2_DECISION.md`（入口=`acceptance/signoff`；回滚 flag=0）；**≠** E4 / 全拆 / compose 长驻 |
| ADR-09 前置 #3 再确认 | ✅ 知情接受兼任（无 7×24）；宣传 E4 已翻签 — `ADR09_ROLES_ONCALL_CONFIRM.md` |
| ADR-09 前置 #4/#5 | ✅ 边界内文案可发布 + CLEAN_ENV 对外证据引用 — `ADR09_E4_*`（第 3 步） |
| ADR-09 停泊 | ✅ `ADR09_PREWORK_COSIGN_PARK.md` — ADR-09 仍 **Proposed**（≠ Accepted）；默认维持 ADR-08/10 试点 |
| ADR-09 第 3 步（对外 E4） | ✅ **已批（窄）** — #436 / `ADR09_E4_STEP3_DECISION.md`；**≠** 全拆 / SLA |
| 全拆 / compose 长驻 | ❌ **本阶段明确不授权** — `ADR09_DEFER_FULL_SPLIT_E4_PROD.md`（再议须另批） |

路径证据目录：`reports/five-products/slice-fp-internal-bundle-pi-diag-001/`（历史内部 id；新场景 id 见 SCENE.md）。
