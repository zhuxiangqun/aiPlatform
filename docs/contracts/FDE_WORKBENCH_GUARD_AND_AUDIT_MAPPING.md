# 工作台否定清单检查 × audit 映射 — 设计骨架（方案层）

| 字段 | 值 |
|------|-----|
| 版本 | v0.5（Phase 2：D3 别名 + D4 压测关闭） |
| 日期 | 2026-09-14 |
| 状态 | Phase 0/1 开工后的实施参考；评审通过前不默认可写码 |
| 关联 | `FDE_WORKBENCH_CONTRACT.md` §4 · `FDE_GUARD_REGISTRY_LANDING.md` §2.0 · `audit_schema.v1.yaml` · 开工清单 §B |

---

## 0. 定位

把「否定清单自动检查」与「audit_schema↔ActionStore 映射脚本」收成**设计说明**，避免再起平行 guard / mapping 包。

| 能力 | 落点（复用） | 禁止 |
|------|--------------|------|
| 前端否定项 CI | `arch_guard_rules.yaml` / `arch_guard_rules/*.py` | `core/tools/architecture_guard` |
| 运行时 4/6/9 | `AsyncActionRegistry.execute` 前置 + Facade KPI 出口 | `FdeActionRegistry` |
| 映射报告 / 加列 SQL | `scripts/fde_audit_mapping.py`（Phase 1 立项后） | 脚本内直接改生产库 |

---

## 1. 否定清单检查矩阵

| # | 否定项 | 类型 | 落点 | 规则 id / 类 | 现状 |
|---|--------|------|------|--------------|------|
| 1–3 | 编辑器/文件树/终端 | CI import | ArchRule | `fde_domain_literals` 旁：`FdeWorkbenchForbiddenFrontendCheck`（code=`fde_workbench_forbidden_components`） | **已有** |
| 4 | 未注册 Action | 运行时 | execute 前置 | `WorkbenchRuntimeGuard.check_action_registered` | **Phase 1 已接 execute** |
| 5 | Agent 拓扑 / dynamic spawn | CI (+ 运行时) | §98 YAML | `workbench_no_agent_topology` | **Phase 0 warning 已合入**（排除隔离文件 `AgentNetworkPanel.tsx`） |
| 6 | 绕过 PolicyGate | 运行时 | execute 前置 | `WorkbenchRuntimeGuard.check_policy_gate_called` | **Phase 1 soft（审计形状）**；产品门 Phase 2 |
| 7 | 硬编码 Action 分支 | CI | YAML §98 | `fde_no_hardcoded_action_branch` | **已有** |
| 8 | 假进度条 | CI | §98 YAML / ArchRule | `workbench_no_fake_progress` | **Phase 0 warning 已合入** |
| 9 | 空 stub KPI | 运行时 | Facade 出口 | `WorkbenchRuntimeGuard.check_kpi_not_stub` | **Phase 1 已接 dashboard** |
| 10 | 平行 FDE API | CI | YAML §98 | `fde_no_parallel_fde_api` | **已有** |

### 1.1 路径事实（强制）

| 层 | 正确路径 | 错误（扫空） |
|----|----------|--------------|
| 前端 UI | `aiPlat-management/frontend/src/pages/Diagnostics/**/*.{ts,tsx}` | `aiPlat-platform/platform/apps/fde/**/*.{ts,tsx}` |
| 后端 API | `aiPlat-platform/apps/fde/**/*.py` | `aiPlat-platform/platform/apps/fde/**` |

**已落地：** `FdeWorkbenchForbiddenFrontendCheck` 已扫 Diagnostics；`fde_no_workbench_direct_harness` 已扫 `aiPlat-platform/apps/fde`。  
**待建** 假进度 / Agent 拓扑规则 **必须**用 Diagnostics 路径（见开工清单 §B）。

---

## 2. audit 映射脚本（Phase 1）

| 目标 | 说明 |
|------|------|
| 输入 | `audit_schema.v1.yaml` + `PRAGMA table_info(action_audit)` |
| 输出 | markdown 报告 + ADD COLUMN NULL SQL + 回滚 SQL |
| 默认 | `--dry-run`，不改库 |
| 策略 | Phase 1 优先 JSON 嵌入；缺列再 ADD NULL |
| 落点 | `scripts/fde_audit_mapping.py` |

### 映射脚本验收

- [x] dry-run 输出 markdown，字段状态分类无遗漏（present / missing / embedded）
- [x] 加列 SQL 全部允许 NULL
- [x] 回滚 SQL 与加列一一对应
- [x] 单测覆盖 present / missing / embedded 三种状态
- [x] 报告入库 `docs/contracts/audit_mapping_report.md`

字段别名与嵌入集合以 Landing §4.1 为准。

---

## 3. 建议落地顺序（评审通过 / 开工清单勾选后）

1. Phase 0 后半：假进度 / Agent 拓扑以 **warning** 合入 §98（正确前端路径）；观察误报。  
2. Phase 1 前半：映射脚本 dry-run 报告入库；RuntimeGuard 骨架已接 execute/dashboard。  
3. Phase 1 后半：HITL 冒烟；DomainRouter 硬验收。  
4. Phase 2：RuntimeGuard 挂 accept_order 全链路 + 别名（D3）— **已合入**（canonical + alias；bench 200 PASS）。

---

## 4. 修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-09-14 | 检查矩阵 + 映射落点 |
| v0.2 | 2026-09-14 | 规则 id 列；路径强制表；映射验收清单 |
| v0.3 | 2026-09-14 | Phase 0：`workbench_no_fake_progress` / `workbench_no_agent_topology` warning 合入 |
| v0.4 | 2026-09-14 | Phase 1：映射脚本 + RuntimeGuard 接线；验收清单勾选 |
| v0.5 | 2026-09-14 | Phase 2：D3 别名 + D4 压测关闭 |

