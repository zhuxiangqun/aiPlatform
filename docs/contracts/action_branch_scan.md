# Action 分支存量扫描报告

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-SCAN-ACTION-BRANCH-2026-09` |
| 版本 | v0.2（初扫 + D4 影响 + P8 表） |
| 日期 | 2026-09-14 |
| 状态 | ☐ 初扫中 · ☑ 初扫完成 · ☑ 分类完成 · ☐ 关闭条件已满足（升 error） |
| 关联方案 | [`fde-workbench-evolution-plan.md`](../architecture/plans/fde-workbench-evolution-plan.md) §6.2 |
| 关联契约 | [`FDE_GUARD_REGISTRY_LANDING.md`](./FDE_GUARD_REGISTRY_LANDING.md) · [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) D3 |
| 关联规则 | `fde_no_hardcoded_action_branch`（§98 YAML） |
| 对照 | [`domain_literals_scan.md`](./domain_literals_scan.md) |
| 扫描人 | Auto（仓库初扫） |
| 复核人 | Oliver Zhu |

---

## 0. 问题

`no_hardcoded_action_branch` 现为 **warning**，升 **error** 需「硬违规清零」。本报告量化 `if action == "accept_order"` 类旁路，避免 Phase 2 迁移时才发现分叉面。

**原则：先量化，再决定升级；先分类，再决定清理顺序。**

---

## 1. 扫描范围与方法

| 项 | 值 |
|----|-----|
| Include | `aiPlat-core/core/harness/**/*.py`、`aiPlat-core/core/engine/**/*.py` |
| Exclude | `**/tests/**` |
| 日期 | 2026-09-14 |
| 工具 | ripgrep + 人工抽查；规则 id `fde_no_hardcoded_action_branch` |

### 1.1 检测模式

| 模式 ID | 模式 | 严重性 |
|---------|------|--------|
| P1 | `action == "literal"` / `action_id == "…"` | error（硬违规） |
| P2 | `action_name == "literal"` | error |
| P3 | `action in [literals]` | error |
| P4 | `action != "literal"` | warn |
| P5 | dict 以 action 名为键的分发表 | warn / 待定 |
| P6 | `match action: case "…"` | error |
| P7 | 字符串拼接构造 action 名 | info |
| P8 | 其他 | 人工 |

---

## 2. 初扫结果（2026-09-14）

### 2.1 汇总

| 模式 | 命中数（初判） | 说明 |
|------|----------------|------|
| P1–P3、P6 | **0** | harness/engine 未见 `== "accept_order"` / `match case` 业务分叉 |
| P4 | 0 | — |
| P5 | 0（未见 HANDLERS 字面量表） | 注册走 `ActionContractModel` / builtin 列表，非 harness 内 if 分叉 |
| P7 | 0 | — |
| 相关符号 | **1** | `builtin_handlers.accept_order` **函数定义**（合法 handler，非分叉） |
| **硬违规合计** | **≈ 0** | 升 error 的阻塞面目前很小 |

**一句话结论：**  
硬编码 `if action == "accept_order"` 类旁路在 harness/engine **初扫未见**；`accept_order` 以 **handler 实现**形式存在于 `builtin_handlers.py`，属 Registry 合法落点，归 **可保留**，不阻塞规则升 error。Phase 2 风险在 **命名空间迁移与别名**，不在清理大量 if 分支。

**对 D4 的影响：** 硬违规 ≈0，Phase 2 压测**无**分支清理前置依赖。唯一前置是 **D3 命名空间迁移**，与本文档硬违规清零无关。

### 2.2 明细

| # | 文件 | 行号 | 模式 | 片段 | 分类 | 处理建议 |
|---|------|------|------|------|------|----------|
| 1 | `ontology_engine/builtin_handlers.py` | ~46 | 实现（非 P1） | `async def accept_order(...)` | **可保留** | 保持为 handler；Phase 2 随 D3 改注册 id / 别名 |

### 2.3 分布（按模块）

| 模块 | 硬违规 | 备注 |
|------|--------|------|
| harness/ontology_engine | 0 | handler 定义 1 |
| harness 其余 | 0 | — |
| engine | 0 | — |

### 2.4 P8 人工抽查记录

| 抽查项 | 结论 |
|--------|------|
| `getattr(registry, action)` 动态分派 | 初扫未发现（待复核人确认） |
| 字符串拼接构造 action 名后 if 分叉 | 初扫未发现 |
| `**kwargs` 透传后按字面量分派 | 初扫未发现 |
| 其他动态 dispatch | 初扫未发现 |

抽查人：**Oliver Zhu** · 抽查日期：**2026-09-14** · ☑ 已签字确认（自动化初扫未见；人工抽查确认无动态分派旁路）

---

## 3. 分类标准（评审确认用）

同决策记录精神：必须清理 / 可保留 / 待定。  
**本轮：** 无「必须清理」硬违规；`accept_order` 实现 → **可保留**。  
**Phase 0 结束前：** 复核人确认无遗漏动态分派（`getattr` / 字符串 dispatch）；待定归零。

---

## 4. 清理计划

| Phase | 目标 | 验收 |
|-------|------|------|
| Phase 0 | 复核人签字；待定=0 | 本文档「分类完成」 |
| Phase 1 | 硬违规保持 0；规则可维持 warning 或提前升 error（建议 Phase 1 末观察一周） | CI 无新增 P1–P3 |
| Phase 2 | 随 D3 迁移注册 id；清理若出现的兼容 if | accept_order 走 namespace 路径 |
| Phase 3 | 别名废弃后回扫 | 无残留旁路 |

**升 error：** 建议条件 = 连续两周 CI 无新增硬违规 + 复核人确认。**不阻塞 Phase 1**；与 domain_literals（阻塞 Phase 5）不同。

---

## 5. 与 domain_literals 对照

| 维度 | domain_literals | action_branch（本文） |
|------|-----------------|------------------------|
| 初扫量级 | ~10（多为示例/prompt） | **硬违规 ~0** |
| 阻塞 | Phase 5 前升 error | 不阻塞 Phase 1 |
| 与决策 | D2 | D3 |

**联合评审时点：** 评审周后半。

---

## 6. 复扫命令

```bash
rg -n 'accept_order|complete_order' aiPlat-core/core/harness aiPlat-core/core/engine \
  --glob '*.py' -g '!**/tests/**'

# 规则（随主守卫）
python3 scripts/architecture_guard.py   # 含 §98 fde_no_hardcoded_action_branch
```

---

## 7. 修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v0 | 2026-09-14 | 模板 |
| v0.1 | 2026-09-14 | 初扫：硬违规≈0；accept_order 仅 handler 定义 |
| v0.2 | 2026-09-14 | 补 D4 影响说明；§2.4 P8 抽查表 |
