# AI Platform UI 实现状态（As‑Is / Progress）

> 本文档用于记录“当前实现状态”，避免污染 `UI_DESIGN.md`（To‑Be 规范）。  
> 更新时间：2026-04-16

---

## 1. 当前前端技术栈（As‑Is）

- React 18 + TypeScript
- Vite + Tailwind CSS
- 自研 UI Kit：`aiPlat-management/frontend/src/components/ui/*`
- 现有入口使用 Ant Design 的 `ConfigProvider` / `App` 作为全局容器（主要用于主题 token 注入与 message/notification 能力）

> 备注：如后续引入第三方组件库（例如 headless UI 或图可视化库），应在此文档记录，并在 `UI_DESIGN.md` 只保留“口径”。

---

## 2. 可观测性能力闭环（As‑Is）

管理面（aiPlat-management）已具备以下聚合 API，可用于 UI 落地：

### 2.1 Trace
- 列表/详情/按 execution_id 查询（含 spans 可选返回）
- 典型入口：
  - `/api/diagnostics/trace/core`
  - `/api/diagnostics/trace/core?trace_id=...`
  - `/api/diagnostics/trace/core?execution_id=...`

### 2.2 Graph Runs / Checkpoints
- runs 列表、run 详情 + checkpoints
- resume / resume+execute
- 典型入口：
  - `/api/diagnostics/graphs/core`
  - `/api/diagnostics/graphs/core/{run_id}?include_checkpoints=true`
  - `/api/diagnostics/graphs/core/{run_id}/resume`
  - `/api/diagnostics/graphs/core/{run_id}/resume/execute`

### 2.3 Links（联动查询）
可通过任意 ID 联动展示 trace/executions/graph_runs：
- `/api/diagnostics/links/core?...`
- UI 友好版本：`/api/diagnostics/links/core/ui?...`
  - 支持 `include_spans=true`
  - 支持 `graph_run_id` 作为 `run_id` 别名

---

## 3. 设计规范与实现的已知差异（待补齐）

### 3.1 Toast / Notification Center
- 规范要求：toast + notification center（可追溯）
- 当前状态：UI Kit 里已有 `Alert`，但 toast/notification center 需要补齐或统一实现

### 3.2 Observability 组件（UI 层）
- 后端聚合能力已闭环
- 前端需要补齐：TraceViewer / GraphRunViewer / LinksPanel 等 domain 组件与页面路由

---

## 4. 变更记录（简要）

- 2026-04-16：新增 links/ui 输出与 spans 控制；graph_runs 与 trace_id 建立强关联；management 支持 graph resume/execute 聚合入口
