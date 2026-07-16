# 核心层应用路由迁移计划 v1.0

## 一、现状

`aiPlat-core/core/api/routers/` 下有 103 个 router 文件（47,188 行），其中：

| 类别 | 文件数 | 行数 | 应迁出 |
|------|:---:|:---:|:---:|
| **Core 能力** | 26 | 17,027 | 否 |
| **管理/诊断** | 9 | 6,485 | 否 |
| **Wiki/本体** | 17 | 7,150 | 否（边界模糊） |
| **应用模块** | **46** | **16,526** | **是** |
| **其他** | 5 | — | — |

### 分类快照

#### ✅ Core 能力（保留，26 文件）
```
agents, tools, workspace_agents, workspace_skills, workspace_tools,
workspace_hooks, workspace_packages, engine_skills, memory, knowledge,
harness, harness_admin, jobs, runs, runs_eval, syscalls, variables,
credentials, models_route, adapters, packages_registry, plugins,
skill_packs, evaluation, evaluation_policies, routing_observability
```

#### ✅ 管理/诊断（保留，9 文件）
```
diagnostics, diagnostics_capability, diagnostics_repo, health,
mcp_admin, system, entropy, observation, audit_ops_export
```

#### ⚠️ Wiki/本体（保留但需审计，17 文件）
```
wiki, wiki_ontology_engine, wiki_ontology_domains, wiki_ontology_export,
wiki_ontology_patterns, wiki_ontology_sql, wiki_evidence, wiki_field_security,
wiki_health_quality, wiki_learning, wiki_loop_triggers, wiki_markings,
wiki_proposals, wiki_scenes, wiki_semantic_suggestions, wiki_writeback,
knowledge_graph
```

#### ❌ 应用模块（迁移，46 文件）

| 批次 | 模块 | 文件数 | 行数 | 目标位置 | 预估人天 |
|:---:|------|:---:|:---:|------|:---:|
| **A** | FDE | 20 | 6,442 | `platform/apps/fde/api/` | 5 |
| **B** | Builder | 2 | — | `platform/builder/` (已在) | — |
| **C** | Workbench/Overview/Kanban | 3 | 1,778 | `platform/apps/workbench/api/` | 2 |
| **D** | Value/Roles/Safety | 3 | 562 | `platform/apps/value/api/` | 1 |
| **E** | Learning (releases/autocapture/misc) | 3 | 1,414 | `platform/apps/learning/api/` | 2 |
| **F** | Prompt管理 | 3 | 1,930 | `platform/apps/prompt/api/` | 2 |
| **G** | Evaluations | 4 | 1,406 | `platform/apps/eval/api/` | 2 |
| **H** | Others (finetune/browser/code_intel等) | 7 | 2,452 | 各模块目录 | 4 |

---

## 二、迁移步骤（通用模板）

### 按批次执行，每批独立迁移+验收

```
Step 1: 创建目标目录
  mkdir -p aiPlat-platform/apps/{module}/api/

Step 2: 移动 router 文件
  git mv aiPlat-core/core/api/routers/{module}.py \
        aiPlat-platform/apps/{module}/api/routers.py

Step 3: 更新导入路径
  全局搜索 `from core.api.routers.{module} import` →
  替换为 `from platform.apps.{module}.api.routers import`

Step 4: Server 注册
  删除 core/server.py 中的 router include
  在 platform 的 routes.py 中注册新路由

Step 5: 向后兼容 (301 Redirect)
  core/server.py 原有路径 → 301 Redirect to 新路径

Step 6: 验证
  py_compile 全量通过
  boundary_guard 无新增违规
  前端 API 路径无断裂
```

### 每批验收清单

- [ ] 目标目录中 router 文件存在
- [ ] core/api/routers/ 中原文件已删除（或保留 redirect stub）
- [ ] 所有导入方已更新
- [ ] Server 注册正确
- [ ] 301 redirect 生效
- [ ] 全量 py_compile 通过
- [ ] 前端 build 通过
- [ ] boundary guard 无新增 ERROR

---

## 三、批次详细计划

### 批次 A：FDE 模块（5 天）

**文件清单**（20 个）：
```
fde.py (2,738), fde_sessions_v2.py (537), fde_diagnostics_v2.py (511),
fde_manuals.py (421), fde_handover_v2.py (256), fde_reports.py (237),
fde_validate.py (193), fde_bootstrap.py (164), fde_acceptance.py (148),
fde_domain_ops.py (97), fde_ask.py (155), fde_delivery.py (138),
fde_governance.py (123), fde_sessions_compare.py (111),
fde_maintenance.py (108), fde_trends.py (107),
fde_dashboard_v2.py (104), fde_quality_summary.py (103),
fde_pipeline.py (72), fde_overview.py (37)
```

**依赖分析**（需同步修改的调用方）：

| 调用方 | 当前导入 | 改为 |
|------|------|------|
| `builder/builder_workflow_service.py` | `from core.api.routers.fde import` | `from core.apps.fde.agent import` ✅ 已完成 |
| `fde_acceptance.py` | `from core.api.routers.fde import` | `from core.apps.fde.agent import` ✅ 已完成 |
| `core/server.py` | `include_router(fde_router)` | `RedirectRoute` (301) |

**迁移步骤**：

1. `core/apps/fde/agent.py` — 已创建 ✅
2. `core/apps/fde/prompts.py` — 已创建 ✅
3. 创建 `aiPlat-platform/apps/fde/api/` 目录
4. 移动 20 个 fde_*.py → `platform/apps/fde/api/`
5. 更新 `core/server.py`：FDE router → 301 Redirect
6. 在 `platform/api/rest/routes.py` 注册新路由
7. 验证

**风险**：FDE 是改动最频繁的模块，迁移后需通知所有 FDE 相关人员

---

### 批次 C：Workbench/Overview/Kanban（2 天）

**文件清单**（3 个）：
```
workbench.py (845), overview.py (850), kanban.py (83)
```

**依赖分析**：
- `workbench.py` 中有 `/fde-dashboard` 端点 → 涉及 FDE 路径变更
- `overview.py` 被前端多个页面调用

**迁移步骤**：
1. 创建 `aiPlat-platform/apps/workbench/api/`
2. 移动 3 个文件
3. 注册新路由 + 301 redirect

---

### 批次 D：Value/Roles/Safety（1 天）

**文件清单**（3 个）：
```
value.py (194), roles.py (202), safety.py (166)
```

**依赖分析**：
- `roles.py` 被管理端调用
- 无模块间交叉依赖

---

### 批次 E-G：学习+Prompt+Evaluations（6 天）

**批次 E**：`learning_releases.py (650), learning_autocapture.py (471), learning_misc.py (293)`
**批次 F**：`prompt_templates.py (1,117), prompt_app.py (732), prompt_optimize.py (81)`
**批次 G**：`skill_evals.py (962), runs_eval.py (432), kb_eval.py (280), prompt_eval.py (282)`

这些模块内聚性低，迁移风险较小。

---

### 批次 H：其他（4 天）

**文件清单**（7 个）：
```
code_intel.py (788), browser_test.py (331), finetune.py (389),
personas.py (252), catalog.py (126), playbook.py (109),
autosmoke.py (147)
```

各自独立，无交叉依赖。

---

## 四、时间线

```
Week 1:  批次 A (FDE) — 最复杂，建立迁移样板
Week 2:  批次 C + D (Workbench + Value) — 验证样板复用
Week 3:  批次 E + F (Learning + Prompt) — 批量迁移
Week 4:  批次 G + H (Eval + Others) — 收尾
```

**总计**：4 周，每批独立验收。

---

## 五、依赖关系图

```
Server 注册链:
  core/server.py:2045  → api_router.include_router(fde_router)
  core/server.py:2060  → api_router.include_router(workbench_router)
  ... 每个模块在 core/server.py 有 1 个 include 行

需要同步变更的:
  core/server.py         → 每个迁移的 include_router → RedirectRoute
  platform/api/rest/routes.py  → 新增 include_router
```

---

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 前端 API 路径断裂 | 301 Redirect 保留 1 版本周期 |
| 批间依赖导致迁移顺序死锁 | 每批独立，先迁移无外部依赖的模块 |
| 迁移过程中代码冲突 | 每批单独 branch + rebase |
| CoreFacade 导入路径在迁移中断裂 | 先完成 CoreFacade 导出封装（Phase 3）再迁移 |

---

## 七、不迁移的文件

以下文件永久留在 `core/api/routers/`：

| 文件 | 原因 |
|------|------|
| `wiki*.py` (17 个) | 核心知识管理，非应用层 |
| `agents.py`, `tools.py`, `memory.py` 等(26 个) | Core 能力端点 |
| `diagnostics*.py`, `mcp_admin.py` 等(9 个) | 管理/诊断，横切关注点 |

---

## 八、验收标准

```bash
# 1. 应用模块不在 core/api/routers/
ls aiPlat-core/core/api/routers/fde*.py aiPlat-core/core/api/routers/workbench.py 2>/dev/null
# → 空

# 2. 应用模块在正确位置
ls aiPlat-platform/apps/fde/api/routers.py aiPlat-platform/apps/workbench/api/routers.py
# → 文件存在

# 3. 301 Redirect 生效
curl -I http://localhost:8000/api/core/fde/assess/dialog
# → HTTP/1.1 301 → Location: /api/platform/apps/fde/assess/dialog

# 4. 无新增违规
bash scripts/architecture_guard_rules.sh
# → TOTAL: X issues (0 errors, only pre-existing warnings)
```
