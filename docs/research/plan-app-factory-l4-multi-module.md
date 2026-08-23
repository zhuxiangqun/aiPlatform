# L4 设计：多模块编排（从"改单个文件"→"演进模块化系统"——1→100 的架构路径）

> **状态**：设计文档（2026-08-23，待评审）
> **目标**：把应用工厂从"单项目单代码库"升级为"**多模块项目编排**"——真实软件系统是模块化的（auth/billing/order/notification），L4 让 AI 能按模块演进大型系统：变更一个模块时，**分析跨模块影响、按依赖顺序编排流水线、验证模块间契约**。
> **关联**：《plan-app-factory-l3-incremental-engine.md》§7（L4 = "跨模块影响分析 + 模块级项目"）+ L2 的 import-repo / L3 的 merge 审批（模块级复用）。

---

## 1. 背景：为什么需要 L4

### L2/L3 的真实边界

| 能力 | 覆盖 | 边界 |
|---|---|---|
| L2 导入既有代码 | 单项目导入 zip/路径 → imported/ | 一个项目 = 一个代码库 |
| L3 增量合并 | 单项目内逐文件 diff 审批 | 影响面分析只做**项目内** Python 一阶 import |
| L4 需要解决的 | **模块化系统**：一个项目多个模块，模块间有 API/数据/事件契约 | 改 auth 模块，billing 模块的调用是否断裂？ |

### L4 解决什么

1. **模块维度**：项目可声明多个模块（`modules.json`），每模块独立 imported/current/（复用 L2/L3 全套能力）
2. **跨模块影响分析**：变更模块 X → 找出依赖 X 契约（API/数据模型/事件）的模块 Y/Z → 纳入编排
3. **模块编排**：按模块依赖顺序跑流水线（先被依赖模块，后依赖方），跨模块契约验证门禁
4. **与 L2/L3 无缝衔接**：每模块独立走 import-repo → 增量生成 → merge 审批

### L4 不做的事（边界）

- ❌ 不做分布式部署/微服务运行时管理（那是 infra 层职责）
- ❌ 不做数据库迁移编排（可后续 L4.5）
- ❌ 不保证"理解整个系统的业务语义"——只做**结构化的模块边界 + 契约引用分析**

---

## 2. 目标

1. 项目可选"多模块"模式：创建时声明模块列表，`modules.json` 持久化
2. 每模块独立 import-repo（L2 复用，加 `module_id` 参数）
3. 跨模块影响分析：API 契约（路由+方法）、数据模型（entity import）、事件（topic 订阅）三类引用构建模块依赖图
4. 变更触发模块编排：按依赖顺序跑受影响模块的流水线，**未受影响模块不重跑**
5. 跨模块契约验证门禁：依赖方调用的端点/模型在变更后仍存在（AST/文本分析）
6. 每模块独立 L3 merge 审批

---

## 3. 设计方案

### 3.1 模块级项目结构

```
~/.aiplat/apps/{project_id}/
  modules.json                 # 模块注册表（L4 新增）
  modules/
    auth/
      imported/                # 该模块既有代码（L2 import-repo 目标）
      current/                 # 该模块部署产物（L3 merge 目标）
    billing/
      imported/
      current/
```

`modules.json`（L4 数据模型）：

```json
{
  "project_id": "prj_xxx",
  "modules": [
    {
      "module_id": "auth",
      "root": "modules/auth",
      "description": "登录/权限",
      "entry_points": ["src/auth/main.py"],
      "contracts": {"apis": [], "entities": [], "events": []},   // 由分析器填充
      "imported_at": ""
    }
  ],
  "updated_at": "2026-08-23T00:00:00"
}
```

**兼容**：未声明 modules.json 的项目 = 隐式单模块（`module_id: "default"`，root = 现有 imported/ 布局），**L2/L3 完全兼容零迁移**。

### 3.2 API 设计（builder 扩展）

```
POST /projects/{project_id}/modules                 # 创建多模块（body: {modules: [{module_id, description}]}）
GET  /projects/{project_id}/modules                 # 模块列表
POST /projects/{project_id}/modules/{module_id}/import-repo   # L2 复用，导入到指定模块
POST /projects/{project_id}/modules/{module_id}/merge-preview  # L3 复用，模块级预览
POST /projects/{project_id}/cross-module-impact     # 跨模块影响分析
POST /projects/{project_id}/module-orchestrate      # 模块编排（变更模块集 → 依赖顺序流水线）
```

### 3.3 跨模块影响分析：`CrossModuleAnalyzer`（新增）

三类契约引用（v1 范围，全部基于静态分析）：

| 契约类型 | 检测方法 | 示例 |
|---|---|---|
| **API 契约** | 模块 A 的 `@router.post("/orders")` 被模块 B 的 `fetch("/api/orders")` / HTTP client 调用 → A 影响 B | auth 的 `/login` 被 billing 调用 |
| **数据模型** | 模块 B `from auth.models import User` / import 模块 A 的 entity 文件 → A 影响 B | User 模型字段变更 |
| **事件契约** | 模块 A `publish("order.created")` / EventBus topic，模块 B `subscribe("order.created")` → A 影响 B | 事件结构变更 |

```python
def analyze_cross_module(modules: dict, workspace_root: str) -> dict:
    """模块依赖图：{module_id: {depends_on: [...], depended_by: [...]}} + 契约证据。"""
    contracts = {}   # module_id → {apis: [...], entities: [...], events: [...]}
    for mid, mod in modules.items():
        contracts[mid] = _scan_module_contracts(mod["root"])       # 本模块声明
    graph = {}
    for mid, mod in modules.items():
        uses = set()
        for target, tmod in modules.items():
            if target == mid:
                continue
            if _module_calls_target(mod, tmod, contracts):         # API/模型/事件引用
                uses.add(target)
        graph[mid] = {"depends_on": sorted(uses), "depended_by": _reverse(graph)}
    return {"graph": graph, "contracts": contracts, "evidence": ...}
```

**影响闭包**：变更模块 X → `X ∪ {Y | Y depends_on X}`（直接 + 传递）。

### 3.4 模块编排：`ModuleOrchestrator`（新增）

```
用户: 变更 auth 模块（勾选 auth/login.py + 意图）
  → CrossModuleAnalyzer: auth 被 billing 依赖（billing fetch /api/auth/login）
  → 编排集 = {auth, billing}
  → 依赖顺序：先 auth（被依赖），后 billing（依赖方）
  → 对每个模块跑 L3 流程：
       auth: import-repo → 增量生成 → merge 审批
       billing: 只做"契约验证 + 受影响文件重生成"（不重跑无关代码）
  → 跨模块契约门禁：billing 调用的 /api/auth/login 在 auth 新版本中仍存在？
       缺失 → 阻断 billing 合并，提示修复
```

**编排原则**：
- 只重生成受影响模块（未受影响模块的 current/ 不动）
- 依赖顺序：拓扑排序（先被依赖后依赖方）
- 每模块独立 merge 审批（复用 L3 `merge_engine`，按模块 previews/decisions）

### 3.5 跨模块契约验证门禁（`CrossModuleContractGate`）

在模块 merge-apply 前执行：
- 对依赖方模块引用的**端点路径**，在变更模块的新版本中搜索（`@router.post("/x")` / `@app.get("/y")` 文本/AST）
- 对引用的**entity 字段**，在变更模块新版本 AST 中对比（类名 + 字段名，v1 只查类名）
- 缺失 → 阻断 + 前端标红（复用 L3 的 blocked 横幅模式）

### 3.6 安全与回滚

- 模块目录隔离：`modules/{mid}/` 独立，跨模块路径校验（防 `../billing/` 越界）
- 回滚：模块级 `deploy.prev`（复用 L3）+ modules.json 快照
- 影响分析是**建议**：编排集前端可调整（勾掉某模块 → 该模块不跑，标注风险）

---

## 4. 前端改动

| 元素 | 位置 | 说明 |
|---|---|---|
| 模块 Tab | 项目详情 | 多模块项目显示模块列表（module_id/描述/状态），每模块独立"导入/合并"入口 |
| 创建多模块 | 新建项目 | 可选"多模块模式"（模块名列表），单模块默认 |
| 跨模块影响展示 | 模块详情 | 变更模块时显示"影响分析：billing 依赖 auth 的 /api/auth/login" |
| 编排进度 | 项目详情 | 按依赖顺序显示模块执行队列 |
| 契约门禁横幅 | merge 审批 | 依赖方引用的端点缺失 → 红横幅阻断（复用 L3 blocked） |

## 5. 验收标准

| # | 验收 | 方法 |
|---|---|---|
| 1 | modules.json 生成，多模块项目结构正确 | 单测：创建 3 模块 → modules.json 含 3 条 |
| 2 | 单模块项目兼容（隐式 default） | 集成：无 modules.json 项目 → import-repo/merge 走原路径 |
| 3 | 模块级 import-repo | 集成：导入到 auth → auth/imported/ 有文件，billing 不受影响 |
| 4 | API 契约影响分析 | 单测：billing fetch("/api/auth/login") + auth 定义该路由 → 分析出 billing depends_on auth |
| 5 | 数据模型影响分析 | 单测：billing from auth.models import User → 同上 |
| 6 | 事件契约影响分析 | 单测：auth publish("order.created") + billing subscribe → 同上 |
| 7 | 影响闭包 | 单测：A→B→C 链，变更 A → 闭包含 A/B/C |
| 8 | 编排顺序 | 集成：变更 auth → ModuleOrchestrator 先编排 auth 后 billing |
| 9 | 未受影响模块不重跑 | 集成：变更 auth → order 模块 current/ 字节不变 |
| 10 | 跨模块契约门禁 | 集成：auth 新版本删除 /api/auth/login → billing 合并被阻断 |
| 11 | 模块级 merge 复用 | 集成：auth 独立 merge 审批，不影响 billing |
| 12 | 前端模块 Tab | 手动验证 + tsc/build |

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| modules.json + 模块 CRUD（含单模块兼容） | 0.5 天 |
| 模块级 import-repo/merge 复用（module_id 参数化） | 0.5 天 |
| CrossModuleAnalyzer（API/数据/事件三类契约） | 1 天 |
| ModuleOrchestrator（拓扑顺序 + 未受影响跳过） | 0.75 天 |
| 跨模块契约门禁 | 0.5 天 |
| 前端（模块 Tab/影响展示/编排进度/门禁横幅） | 0.75 天 |
| 测试（12 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 4.5 天** |

## 7. 与后续层级的关系

- **L4 做完**：应用工厂可演进**模块化系统**（多模块、跨模块影响、依赖顺序编排）——从 1 到 100 可行
- **L4.5（数据迁移编排）**：数据库 schema 变更 + 迁移脚本编排（候选）
- **L5（持续演进）**：模块级 CI/CD、灰度发布（对接 infra）

## 8. 风险与开放问题

1. **静态分析精度**：API/事件契约用文本/AST 匹配，动态注册的路由（变量拼路径）可能漏检 → 影响图标注"仅供参考 + 证据行号"，前端可手动调整编排集。
2. **跨模块重构深度**：只做"契约引用"级影响，不做"共享代码语义"级分析（如两个模块复用同一 util 的内部行为变化）——需要更深的依赖分析（可后续增强）。
3. **编排状态机复杂度**：多模块并行 vs 顺序——v1 顺序（依赖序）保证契约验证；并行是后续优化。
4. **与 L3 merge 的并发**：模块间合并互不干扰（独立 previews/decisions），但依赖方模块的 merge 需在变更模块 merge 之后（编排顺序天然保证）。
5. **monorepo 大仓库**：多模块项目若仍是单 zip 导入，import-repo 按模块拆分——需要 zip 内目录映射（module_dir 参数）。

---

## 9. 与 L2/L3 的衔接清单

| L2/L3 资产 | L4 复用/扩展 |
|---|---|
| `import_repo`（zip/路径→manifest） | 加 `module_id` 参数，目标目录改为 `modules/{mid}/imported/` |
| `merge_engine`（ImpactAnalyzer/DiffMerger） | 模块级复用（每模块独立 previews/decisions）；ImpactAnalyzer 的"项目内一阶 import"升级为"模块间契约引用"（CrossModuleAnalyzer） |
| `merge_strategy`/`inject_imported_context` | 模块级配置（模块 YAML 可覆盖） |
| `deploy.prev` 快照 | 模块级快照 |
| 前端导入面板/合并审批界面 | 模块 Tab 内复用；门禁横幅复用 blocked 模式 |
