# FDE Phase 5 — 新客户接入清单（配置驱动，不改 harness）

| 字段 | 值 |
|------|-----|
| 版本 | v1.0 |
| 日期 | 2026-09-14 |
| 状态 | Phase 5 生效 |
| 关联 | `FDE_WORKBENCH_CONTRACT.md` · `domain_literals_scan.md` · D2 |
| Owner | Oliver Zhu |

---

## 0. 原则

| 做 | 不做 |
|----|------|
| DomainRouter 注册 + 域本体 YAML + Action YAML | 改 `core/harness` 硬编码客户域名 |
| Ontology Editor / Action `from-yaml` / FDE 客户 Profile | 新建平行 ActionRegistry / architecture_guard |
| 单域竖切稳定后再谈 Agent Fleet | 工作台内嵌 Agent 拓扑 / Fleet 编排 |

**前置（已满足）：** `fde_domain_literals` = **error**；AST issues=0；行为分叉 Compare=0（见 `domain_literals_scan.md` v1.1）。

---

## 1. 接入步骤（操作员）

| # | 步骤 | 落点 | 验收 |
|---|------|------|------|
| 1 | 创建域本体 | Ontology Editor → `POST /domains` 或 `~/.aiplat/ontologies/{domain_id}.yaml` | `DomainRouter.list_domains()` 可见 |
| 2 | 热注册（若未自动） | `DomainRouter.register_domain(domain_id, config)` | `require_known_domain(domain_id)` 通过 |
| 3 | 注册客户运营 Action | Action YAML（`action_namespace: customer_action`）→ `POST …/fde/actions/from-yaml` 或 workspace_seeds | Registry `get(canonical_id)` 非空 |
| 4 | FDE 客户 Profile | 工作台 ① 业务认知 → 创建/选择客户；绑定域 | 后续 Tab 带 `domain_id` |
| 5 | （可选）交付链接工厂 | Tab⑤ 填 Builder `project_id` | Phase 3 observe/eval |
| 6 | （可选）上线前检查 | Tab ⑥b | Phase 4A dry-run |

**诚实说明：** Ontology 创建路径可能直接写 `registry.json`；热路径以 `DomainRouter.register_domain` 为准。二者并存时以 Router 列表为运行时权威，发现不一致先 `register_domain` / 重建索引，**不要**在 harness 加第三套注册表。

---

## 2. 非目标（Phase 5 仍不做）

1. Agent Fleet / 动态多 Agent 拓扑 UI（`AgentNetworkPanel` 保持隔离）
2. 为每个客户改 PipelineEngine / 硬编码 stage
3. 废弃 `accept_order` 别名（仍属 Phase 3→D3 收尾，可另 PR）

---

## 3. 验证命令

```bash
# 守卫已为 error 且无新增行为分叉
PYTHONPATH=aiPlat-core python3 -c "
from pathlib import Path
from core.management.arch_guard_rules.fde_workbench import FdeDomainLiteralsAstCheck
c = FdeDomainLiteralsAstCheck()
assert c.level == 'error'
assert c.check(Path('.')) == []
print('OK fde_domain_literals error + clean')
"

# 域列表（运行时）
PYTHONPATH=aiPlat-core python3 -c "
from core.harness.knowledge.domain_router import DomainRouter
print(DomainRouter().list_domains()[:20])
"
```

---

## 4. 修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-14 | Phase 5 接入清单；无 Fleet |
