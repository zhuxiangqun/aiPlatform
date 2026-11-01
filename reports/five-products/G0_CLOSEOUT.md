# G0 结论文档（2026-11-01）

> **范围**：文档与证据对齐；不宣称生产就绪；不碰 authorize。  
> **SSOT 计划**：[`five-capability-independent-engineering-plan.md`](../../docs/architecture/plans/five-capability-independent-engineering-plan.md)  
> **详细勾选**：[`G0_REPORT.md`](./G0_REPORT.md)

## 结论

**G0 通过（有正式例外 P0-3′）**。

| 项 | 值 |
|----|-----|
| 基线起点 | `b46e286` |
| 初版 CI 锚点 | `17f21d67`（Option B lock-in · **19** 提交） |
| 中间锚点 | `1992e8e1`（47）· `66a6e07a`（52 · 含 D2++ SOC） |
| **现行 CI 锚点（HEAD）** | **`500b4287`**（G0 52-commit receipt · docs 收口） |
| 提交数（HEAD） | **`git rev-list --count b46e286..500b4287` → 54** |
| collect | **3209** / 0 error（G0_REPORT 2026-11-01；初版锚点） |
| unit | **2735** passed / 11 skipped / 0 failed（初版锚点） |
| Tier A 逃逸 | **0**（`paths.py` SSOT fallback 除外） |
| STATUS↔manifest | `check_five_products_status_sync.py` PASS |
| 硬门 | 全 false；`staging_ready=false`；defer → **2026-11-22** |
| 工程环境 | **方案 B** 本机 VM/Docker（[`ops/OPTION_B_LOCAL_VM.md`](./ops/OPTION_B_LOCAL_VM.md)） |

## 正式例外：P0-3′

| | |
|--|--|
| 原判据 | 字面只读 / chmod-555 HOME 下 unit 绿 |
| 例外 | **不作为硬门**（字面只读下 git 红属已知例外，非逃逸） |
| 现行判据 | 假 HOME 可写 + hermetic `AIPLAT_HOME`（与 conftest 同路径）下 collect/unit 绿 |
| 逃逸门 | 仍看 Tier A=0 + hermetic `AIPLAT_HOME` |
| 计划同步 | 计划 §2.2 / §9.1 已改为 P0-3′（2026-11-01） |

## D1c 语义（报告/计划统一）

| 作废 | 保留 |
|------|------|
| 旧 **D0** 叙事；「只停在 D1c 天花板」的旧读法 | **D1c = `delivery_mode: cohost`**（契约/healthz 独立，进程共宿） |

G0_REPORT 第 16 行已改为「旧 D0 作废；D1c 保留为 cohost 别名」。

## CI 证据（P0 · receipt ≠ CI）

defect-gate receipt **不能**替代 CI。

### HEAD `500b4287`（54 提交 · 现行）

| Workflow | 结论 | Run |
|----------|------|-----|
| **CI**（unit/collect 主门） | **success** | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618527 |
| Architecture Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618598 |
| L5 Verification Suite | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618500 |
| Slice E2E (live evidence) | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618570 |
| AI Penetration Test | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618546 |
| aiPlat Contracts Guard | **success** | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41269618504 |

### 中间锚点 `66a6e07a`（52 提交 · 历史 · 含 D2++ SOC）

| Workflow | 结论 | Run |
|----------|------|-----|
| **CI** | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417524 |
| Architecture Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417471 |
| L5 Verification Suite | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417553 |
| Slice E2E | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417609 |
| AI Penetration Test | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417600 |
| aiPlat Contracts Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41268417570 |

### 中间锚点 `1992e8e1`（47 提交 · 历史）

| Workflow | 结论 | Run |
|----------|------|-----|
| **CI** | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488889 |
| Architecture Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488885 |
| L5 Verification Suite | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488882 |
| Slice E2E | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488887 |
| AI Penetration Test | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488902 |
| aiPlat Contracts Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41263488906 |

### 初版锚点 `17f21d67`（19 提交 · 历史）

| Workflow | 结论 | Run |
|----------|------|-----|
| **CI** | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435177 |
| Architecture Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435355 |
| L5 Verification Suite | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435281 |
| Slice E2E | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435090 |
| AI Penetration Test | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435091 |
| aiPlat Contracts Guard | success | https://github.com/zhuxiangqun/aiPlatform/actions/runs/41257435152 |

复验命令：

```bash
git rev-list --count b46e286..HEAD   # expect 54+
python3 scripts/check_five_products_status_sync.py
gh run list --branch main --limit 10
bash scripts/ops_engineering_freeze_check.sh
bash scripts/five_products_gate.sh
```

## 本地冻结自检（HEAD 同期）

| 检查 | 结果 |
|------|------|
| `ops_engineering_freeze_check.sh` | **PASS**（authorize 全 REFUSE · 下次里程碑 11-22） |
| `five_products_gate.sh` | **PASS**（2026-11-01 复跑 · 含 D3/E2E local） |
| `ops_option_b_all.sh` | **PASS**（`pgha_mode=docker` · `OPTION_B_LAST_RUN.md`） |
| 11-22 复审预填 | **READY**（[`STAGING_REVIEW_2026-11-22.md`](./ops/STAGING_REVIEW_2026-11-22.md) · 无主机） |
| Field compose ADR | **继续 Draft**（[`ADR-DRAFT-fde-field-compose.md`](./ADR-DRAFT-fde-field-compose.md)） |

## 非结论

- 不表示五能力生产就绪  
- 不表示 `cutover` / `process_split` / `d3_production` 可 authorize  
- 本机 `local_signed` ≠ `production_signed`

## 下一步（基线 backlog）

1. ✅ HEAD **CI + Contracts Guard** 均 **success**（**54** 提交 · `500b4287` 上表）  
2. ✅ Pi D3 本地收尾 → FDE Field D2 → Eval/Onto D2 → aiPlat D2 thin  
3. ✅ **Plan V2.1 + shared packaging base**  
4. ✅ **D2 local perf baseline**  
5. ✅ **Engineering freeze** + 显式解冻 D3/E2E → 完成后 **再冻结**  
6. ✅ **2026-11-08 / 11-15 预发复审** → **continue_defer**；下次 **2026-11-22**（预填包已就绪）  
7. ✅ **Pi D2++ SOC** schema 硬核（`d2_soc_deeper_check`）  
8. ✅ **Field compose ADR v2** → **继续 Draft**（不实施）  
9. ⏳ **真实预发供给**（可选；[`STAGING_PROVISIONING.md`](./ops/STAGING_PROVISIONING.md)）— 当前决策：**不实施 / 不买服务器**  
