# AI Platform UI 设计规范（Design System & UX Patterns）

> 系统级 UI 设计规范（**To‑Be**）：统一整个 aiPlatform 的前端设计语言、交互模式与工程落地标准。  
> **重要**：本规范不记录“已实现/已修复/Phase X”等进度信息；实现状态请见 `UI_IMPLEMENTATION_STATUS.md`。
>
> **主题**：深色主题（Black Background / Light Text）  
> **风格参考**：GitHub Dark / Tokyo Night  

---

## 目录

- [1. 设计原则](#1-设计原则)
- [2. 视觉设计系统（Tokens）](#2-视觉设计系统tokens)
- [3. 组件体系（UI Kit）](#3-组件体系ui-kit)
- [4. 通用交互模式（UX Patterns）](#4-通用交互模式ux-patterns)
- [5. 布局与页面模板（App Shell）](#5-布局与页面模板app-shell)
- [6. 可观测性体验规范（Observability UX）](#6-可观测性体验规范observability-ux)
- [7. 无障碍（Accessibility）](#7-无障碍accessibility)
- [8. 前端工程规范（Engineering）](#8-前端工程规范engineering)
- [9. 文档治理与版本](#9-文档治理与版本)

---

## 1. 设计原则

### 1.1 核心原则

| 原则 | 定义 | UI 层落地要点 |
|------|------|--------------|
| 一致性 | 全系统统一视觉与交互语言 | 统一 Tokens、组件库、页面模板、状态语义（success/warn/error） |
| 可用性 | 用户能快速完成任务 | 清晰层级、可预期导航、默认值合理、可撤销/可恢复 |
| 可观测性优先 | 任何“自动化/执行”都必须可追踪 | trace/span、graph runs/checkpoints、联动跳转、可复制 ID |
| 可访问性 | 覆盖键盘与读屏 | WCAG 2.1 AA、对比度、焦点状态、ARIA |
| 可维护性 | 组件化与文档化 | UI Kit 单一来源、变体收敛、props 语义化、示例齐全 |
| 性能 | 大列表/大 payload 可用 | 分页、按需加载（lazy）、虚拟滚动、payload 裁剪策略 |

### 1.2 信息架构（IA）总纲

平台级管理 UI 的导航必须围绕“**发现问题 → 定位问题 → 采取行动 → 验证恢复**”闭环：

- Overview/Dashboard：全局健康度与关键 KPI
- Monitoring：指标与趋势（资源/吞吐/延迟）
- Alerting：告警列表、确认/关闭、规则配置
- Diagnostics/Observability：traces、graph runs、checkpoints、联动查询（links）
- Config/Settings：配置治理（查看/修改/审计）

---

## 2. 视觉设计系统（Tokens）

### 2.1 颜色系统

#### 2.1.1 品牌色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-primary` | `#3B82F6` | Primary actions / links / active states |
| `--color-primary-hover` | `#2563EB` | Primary hover |
| `--color-primary-active` | `#1D4ED8` | Primary pressed |

#### 2.1.2 语义色（状态必须一贯）

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-success` | `#10B981` | 成功、健康、已完成 |
| `--color-warning` | `#F59E0B` | 警告、降级、需要关注 |
| `--color-error` | `#EF4444` | 错误、失败、不可用、破坏性操作 |
| `--color-info` | `#3B82F6` | 信息提示 |

#### 2.1.3 中性色（深色主题）

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-bg` | `#0D1117` | 页面背景 |
| `--color-surface-1` | `#161B22` | 卡片/容器背景 |
| `--color-surface-2` | `#1C2128` | 悬浮/二级表面 |
| `--color-border` | `#30363D` | 边框/分割线 |
| `--color-text-strong` | `#E6EDF3` | 标题/强调 |
| `--color-text` | `#C9D1D9` | 正文 |
| `--color-text-muted` | `#8B949E` | 次要说明/占位 |

### 2.2 排版系统

```css
--font-sans: 'Geist Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
```

| Token | Size | Line Height | 用途 |
|-------|------|------------|------|
| `--font-size-xs` | 12px | 16px | caption、badge |
| `--font-size-sm` | 13px | 20px | 表格/次级信息 |
| `--font-size-base` | 14px | 22px | 正文 |
| `--font-size-lg` | 16px | 24px | 小标题 |
| `--font-size-xl` | 18px | 28px | 区块标题 |
| `--font-size-2xl` | 20px | 28px | 页面标题 |

### 2.3 间距系统（4px 网格）

| Token | Value |
|-------|-------|
| `--spacing-1` | 4px |
| `--spacing-2` | 8px |
| `--spacing-3` | 12px |
| `--spacing-4` | 16px |
| `--spacing-6` | 24px |
| `--spacing-8` | 32px |
| `--spacing-12` | 48px |

### 2.4 圆角与阴影

| Token | Value | 用途 |
|------|-------|------|
| `--radius-sm` | 6px | button/input |
| `--radius-md` | 8px | card/modal |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.08)` | card/dropdown |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.08)` | modal/popover |

---

## 3. 组件体系（UI Kit）

### 3.1 技术栈口径

- React 18 + TypeScript
- Tailwind CSS（以 tokens 驱动主题）
- Framer Motion（页面/弹层动效）
- Lucide React（图标）

> 组件库口径：**统一使用项目内 `/src/components/ui/` 组件**。不要在“规范”里引入与现状不一致的第三方组件名（如 Ant Design），以免误导落地。

### 3.2 组件分层

1) **Primitive**：Button/Input/Badge/Modal/Tabs/Switch/Progress/Tooltip/Dropdown  
2) **Pattern**：FilterBar、DataTable、DetailDrawer、ConfirmDialog、InlineEditor、KeyValueList  
3) **Domain**：TraceViewer、GraphRunViewer、AlertList、LayerHealthPanel

### 3.3 状态与变体规范（所有组件必须一致）

#### Button
- `variant`: `primary | secondary | danger | ghost`
- `state`: `default | hover | pressed | disabled | loading`
- `danger` 必须与二次确认策略联动（见 4.3）

#### Badge/Status
必须统一映射：
- `healthy/success` → success
- `degraded/warn` → warning
- `unhealthy/error/failed` → error
- `running` → info

#### Table（大数据）
- 默认分页（limit/offset）
- 支持列级排序/筛选（优先服务端）
- 需要长字段（id/trace_id）时必须提供：复制按钮、截断展示（mono）

### 3.4 Toast & Notification Center（替代 alert）

禁止在产品体验中使用浏览器原生 `alert()`。

- **Toast**：短暂、非阻塞、用于“操作反馈”（成功/失败/警告/信息）
- **Notification Center**：可追溯、可查看历史、用于“任务/执行/告警”类长生命周期事件

建议组件：
- `ToastProvider` + `useToast()`
- `NotificationCenter`（右上角铃铛 + drawer）

---

## 4. 通用交互模式（UX Patterns）

### 4.1 Loading / Empty / Error

- 页面级：骨架屏（Skeleton）
- 组件级：Button loading / Table loading
- 网络错误：提供“重试”与“复制错误详情”
- 空状态：告诉用户“为什么为空” + “下一步可做什么”

### 4.2 表单与编辑

推荐：详情 Drawer + 内联编辑（InlineEdit），重编辑用 Modal。

规则：
- 保存后给 toast，失败给 error toast + 详情可展开（stack trace 可复制）
- JSON 配置编辑必须提供：格式化/校验/示例/一键复制

### 4.3 危险操作确认（两级策略）

| 风险等级 | 示例 | 交互 |
|---------|------|------|
| 高 | delete / disable critical | ConfirmDialog + 二次确认 |
| 中 | restart / scale down | ConfirmDialog |
| 低 | toggle UI only | 无需确认 |

### 4.4 深链接（Deep Link）规范

任何“执行/诊断/告警”页面必须支持通过 URL 直达：
- `trace_id`
- `execution_id`
- `graph_run_id`
- `checkpoint_id`

---

## 5. 布局与页面模板（App Shell）

### 5.1 App Shell

- Header：60px（全局搜索/环境切换/通知中心入口/用户）
- Sidebar：240px（collapsed 64px）
- Content：PageHeader + Filters + ContentCard

### 5.2 Page Header 模板

包含：
- Title（2xl）
- Description（muted）
- Actions（右侧，primary 仅一个）
- Optional: Breadcrumb / last updated

---

## 6. 可观测性体验规范（Observability UX）

本章对应“定位问题”的核心路径，必须覆盖：
- trace/span（链路）
- graph runs/checkpoints（可恢复执行）
- links（联动查询入口）

### 6.1 Diagnostics 主页（入口与导航）

建议布局：
- 顶部：Layer Health（infra/core/platform/app）
- 中部：Recent Alerts（最近告警）
- 下部：Observability Shortcuts（Trace / Graph / Links 快捷入口）

#### 6.1.1 推荐路由与页面（信息架构落地）

> 路由口径：前端统一访问 management 网关 `/api/...`，页面路由不体现端口与层内服务地址。

| 页面 | 路由（建议） | 目标用户任务 | 关键 Deep Link 参数 |
|------|--------------|--------------|---------------------|
| Diagnostics Home | `/diagnostics` | 从“健康/告警”进入定位 | - |
| Trace List | `/diagnostics/traces` | 查找/筛选 trace | `trace_id`（可选，用于高亮选中） |
| Trace Detail | `/diagnostics/traces/:traceId` | 查看 spans、定位慢点 | `include_spans` |
| Graph Runs List | `/diagnostics/graphs` | 查看 run、筛选状态 | `run_id`（可选） |
| Graph Run Detail | `/diagnostics/graphs/:runId` | 查看 checkpoints、恢复 | `checkpoint_id`（可选） |
| Links（联动查询） | `/diagnostics/links` | 输入任意 ID 联动定位 | `execution_id` / `trace_id` / `graph_run_id` |

页面状态与 URL 同步规则：
- 列表筛选（status、graph_name 等）应落到 query string，支持分享链接复现视图
- 详情页必须提供“复制 ID / 一键跳转 Links / 返回上级列表并保留筛选”

### 6.2 Trace Viewer

#### Trace List（列表）
字段建议：
- trace_id（mono + copy）
- name
- status（badge）
- start_time / duration

交互：
- 默认不加载 spans（payload 大）：点击进入详情时再加载或通过 `include_spans=true` 显式请求

#### 6.2.1 API 契约（UI 侧调用 management 聚合）

Trace 列表与详情必须通过 management 的 diagnostics 聚合 API 获取（避免前端直连 core）：

- 列表：`GET /api/diagnostics/trace/core?limit=50&offset=0`
- 详情：`GET /api/diagnostics/trace/core?trace_id=...&include_spans=true`
- 通过 execution_id 反查：`GET /api/diagnostics/trace/core?execution_id=...&include_spans=true`

性能建议：
- 默认 `include_spans=false`（或不传）用于列表/联动查询；仅在 Trace Detail 需要展开 spans 时打开

#### Trace Detail（详情）
至少包含：
- Summary：trace_id、status、duration、attributes
- Spans：表格（可折叠）+ 过滤（name/status）
- Actions：复制 trace_id、跳转 Links（见 6.4）

### 6.3 Graph Run Viewer（Runs / Checkpoints / Resume）

#### Graph Runs List
字段建议：
- run_id（mono + copy）
- graph_name
- status
- start_time / duration
- parent_run_id（可为空，若有则提供跳转）
- trace_id（若存在，提供跳转 Trace）

#### Run Detail
至少包含：
- Run Summary：run_id、status、trace_id、lineage（父链）
- Checkpoints：按 step/created_at 倒序，提供“查看 state”“从此恢复”
- Actions：
  - Resume（仅建档）
  - Resume & Execute（闭环执行，需二次确认：会产生新 run）

#### 6.3.1 API 契约（UI 侧调用 management 聚合）

- runs 列表：`GET /api/diagnostics/graphs/core?limit=50&offset=0&graph_name=&status=`
- run 详情 + checkpoints：`GET /api/diagnostics/graphs/core/{run_id}?include_checkpoints=true`
- resume（仅建档）：`POST /api/diagnostics/graphs/core/{run_id}/resume` body: `{checkpoint_id? | step? | user_id?}`
- resume + execute（闭环执行）：`POST /api/diagnostics/graphs/core/{run_id}/resume/execute` body: `{checkpoint_id? | step? | max_steps? | checkpoint_interval? | user_id?}`

交互安全建议：
- `resume/execute` 属于“会产生新 run 的执行动作”，至少需要 ConfirmDialog（见 4.3）
- 成功后自动跳转到新 `run_id` 的详情页，并在页面中展示 lineage（parent_run_id/resumed_from_checkpoint_id）

### 6.4 Links（联动查询入口）

目标：用户输入任意一个 ID，都能看到“相关的一切”。

支持输入：
- `execution_id`
- `trace_id`
- `graph_run_id`

输出：
- Summary（counts、可执行动作）
- trace（可选 spans）
- executions
- graph_runs（同 trace_id 过滤）
- lineage（父链）

#### 6.4.1 UI 版本与 payload 策略

推荐 UI 默认使用“面板化输出”：
- `GET /api/diagnostics/links/core/ui?...`

并仅在用户明确展开 spans 时才请求：
- `GET /api/diagnostics/links/core/ui?trace_id=...&include_spans=true`

#### 6.4.2 Links 输入框与联动跳转规则

输入框允许粘贴任意 ID，推荐策略：
- 若输入以 `exec-` 开头或命中 execution_id 格式 → 走 `execution_id`
- 若输入形如 UUID（trace_id 常见） → 先尝试 trace_id；失败再提示用户选择
- 若输入形如 run_id（UUID 或自定义） → 走 `graph_run_id`

联动跳转：
- Trace Detail 页面必须提供“跳转 Links（带 trace_id）”
- Graph Run Detail 页面必须提供“跳转 Links（带 graph_run_id/run_id）”

### 6.5 Domain 组件规范（面向落地的 props/行为）

> 本节约束“可观测性组件”的最小接口，确保可复用、可测试、可组合。

#### 6.5.1 TraceList

```ts
export interface TraceListQuery {
  limit: number
  offset: number
  status?: string
}

export interface TraceListProps {
  query: TraceListQuery
  onQueryChange: (q: TraceListQuery) => void
  onSelectTrace: (traceId: string) => void
}
```

行为要求：
- 表格列必须包含 trace_id（mono + copy）
- 默认不拉 spans

#### 6.5.2 TraceDetail

```ts
export interface TraceDetailProps {
  traceId: string
  includeSpans: boolean
  onToggleIncludeSpans: (v: boolean) => void
  onOpenLinks: (params: { trace_id: string }) => void
}
```

#### 6.5.3 GraphRunList / GraphRunDetail

```ts
export interface GraphRunListQuery {
  limit: number
  offset: number
  graph_name?: string
  status?: string
  trace_id?: string
}

export interface GraphRunListProps {
  query: GraphRunListQuery
  onQueryChange: (q: GraphRunListQuery) => void
  onSelectRun: (runId: string) => void
}

export interface GraphRunDetailProps {
  runId: string
  includeCheckpoints: boolean
  onResume: (params: { checkpoint_id?: string; step?: number; user_id?: string }) => Promise<void>
  onResumeExecute: (params: { checkpoint_id?: string; step?: number; max_steps?: number; checkpoint_interval?: number; user_id?: string }) => Promise<void>
  onOpenLinks: (params: { graph_run_id: string }) => void
}
```

#### 6.5.4 LinksPanel（联动面板）

```ts
export type LinksInput =
  | { trace_id: string }
  | { execution_id: string }
  | { graph_run_id: string }

export interface LinksPanelProps {
  input: LinksInput
  includeSpans: boolean
  onToggleIncludeSpans: (v: boolean) => void
  onNavigateToTrace: (traceId: string) => void
  onNavigateToRun: (runId: string) => void
}
```

### 6.6 页面规范（线框级落地）

> 目标：前端可以“照着做”。本节描述页面信息结构、筛选项、表格列、关键操作与状态处理。

#### 6.6.1 Diagnostics Home（/diagnostics）

页面结构（从上到下）：
1) **Layer Health Row**：infra/core/platform/app 四个状态卡片  
   - 展示：status badge、last updated、关键指标（可选）  
   - 操作：点击进入对应 Layer 的详情/Diagnostics（优先跳转到 links 或 graphs）
2) **Recent Alerts**（若有）：近 24h（或近 N 条）告警摘要列表  
   - 操作：跳转到 Alerting 列表并带筛选（status=active）
3) **Observability Shortcuts**：3 个入口卡片  
   - Traces（最近 traces/搜索）  
   - Graph Runs（最近 runs/恢复）  
   - Links（输入任意 ID 联动）

空/错误状态：
- 若 infra/core 不可达：在卡片中显示 `error` badge + “查看原因（打开 Links）”

#### 6.6.2 Trace List（/diagnostics/traces）

筛选区（FilterBar）：
- `status`（running/completed/failed 可选）
- 时间范围（可选，若后端暂不支持则先做前端筛选或隐藏）
- 搜索框（trace_id 精确匹配优先）

表格列（建议）：
- `trace_id`（mono + copy + 点击进入详情）
- `name`
- `status`（badge）
- `start_time`
- `duration_ms`
- `actions`：Open Links（带 trace_id）

交互：
- 默认 `include_spans=false`，进入详情页时再请求 spans
- 列表分页：limit/offset（与 URL query 同步）

#### 6.6.3 Trace Detail（/diagnostics/traces/:traceId）

Page Header：
- Title：`Trace <short(trace_id)>`
- Actions：Copy trace_id / Open Links / Toggle spans（默认 off）

内容区（Tabs 推荐）：
1) **Summary**：name、status、duration、attributes（key-value）
2) **Spans**：表格 + 过滤（name/status）  
   - spans 表格列：span_id（copy）、name、status、duration、parent_span_id（可选）、attributes（折叠）

错误状态：
- trace 不存在：Empty + “返回列表”
- spans 过大：提示“已折叠 attributes，建议按 name/status 过滤”

#### 6.6.4 Graph Runs List（/diagnostics/graphs）

筛选区：
- `graph_name`（输入或下拉，视后端数据形态）
- `status`（running/completed/failed）
- `trace_id`（可选，用于与 Trace 联动）

表格列（建议）：
- `run_id`（mono + copy + 点击进入详情）
- `graph_name`
- `status`（badge）
- `start_time` / `duration_ms`
- `parent_run_id`（若有：显示 short + 跳转）
- `trace_id`（若有：显示 short + 跳转 Trace / Links）

#### 6.6.5 Graph Run Detail（/diagnostics/graphs/:runId）

Page Header：
- Title：`Run <short(run_id)>`
- Actions：Copy run_id / Open Links / Resume / Resume & Execute

内容区（推荐分块）：
1) **Run Summary**：status、graph_name、trace_id、parent_run_id、resumed_from_checkpoint_id
2) **Lineage**（若有）：以面包屑或纵向链路展示 parent 链（点击跳转）
3) **Checkpoints**：
   - 列：checkpoint_id（copy）、step、created_at、actions（View State / Resume from here / Resume&Execute）
   - View State：Drawer 展示 JSON（支持格式化/复制）

Resume 安全规范：
- Resume（仅建档）：中风险确认（ConfirmDialog）
- Resume&Execute：高风险确认（ConfirmDialog + 提示“会创建新 run 并继续执行”）
- 成功后：toast + 自动跳转到新 run_id 详情页（并在页面显示 lineage 关系）

#### 6.6.6 Links（/diagnostics/links）

页面结构：
1) **输入区**：一个输入框 + “解析/查询”按钮（可回车触发）
2) **Summary 卡片**：counts、可执行动作（can_resume/has_trace）
3) **联动结果 Tabs**（推荐）：
   - Trace（默认不含 spans；可开 include_spans）
   - Executions（agent/skill 执行列表）
   - Graph Runs（同 trace_id 过滤结果）
   - Lineage（父链）

输入识别：
- 支持粘贴 execution_id / trace_id / graph_run_id
- 若无法识别：给出提示并提供手动选择类型（execution/trace/run）

---

## 7. 无障碍（Accessibility）

- WCAG 2.1 AA：对比度 >= 4.5:1
- 所有交互元素支持键盘（Tab/Enter/Esc）
- focus-visible 必须可见
- Modal/Drawer 必须 trap focus

---

## 8. 前端工程规范（Engineering）

### 8.1 目录结构建议

```
frontend/
  src/
    components/
      ui/              # UI Kit
      patterns/        # FilterBar/DataTable/Drawer
      observability/   # TraceViewer/GraphRunViewer/LinksPanel
    pages/
      Diagnostics/     # 可观测性页面（traces/graphs/links）
    services/          # API clients（统一 /api 前缀）
    styles/
      tokens.css
      theme.ts
```

### 8.4 路由配置规范（React Router）

#### 8.4.1 路由命名与分组

原则：
- 路由路径按“业务域”分组：`overview / alerts / infra/* / core/* / platform/* / app/* / diagnostics/*`
- 可观测性统一挂在 `diagnostics/*` 下，避免散落在各层页面里造成“定位入口不一致”
- 列表页与详情页使用固定约定：`/diagnostics/traces` 与 `/diagnostics/traces/:traceId`

建议新增的路由（页面）：

| Path | 页面文件（建议） |
|------|------------------|
| `diagnostics` | `src/pages/Diagnostics/Diagnostics.tsx` |
| `diagnostics/traces` | `src/pages/Diagnostics/Traces/Traces.tsx` |
| `diagnostics/traces/:traceId` | `src/pages/Diagnostics/Traces/TraceDetail.tsx` |
| `diagnostics/graphs` | `src/pages/Diagnostics/Graphs/Graphs.tsx` |
| `diagnostics/graphs/:runId` | `src/pages/Diagnostics/Graphs/GraphRunDetail.tsx` |
| `diagnostics/links` | `src/pages/Diagnostics/Links/Links.tsx` |

#### 8.4.2 路由注册示例（createBrowserRouter）

```tsx
// App.tsx（示例片段）
const DiagnosticsHome = lazy(() => import('./pages/Diagnostics/Diagnostics'))
const DiagnosticsTraces = lazy(() => import('./pages/Diagnostics/Traces/Traces'))
const DiagnosticsTraceDetail = lazy(() => import('./pages/Diagnostics/Traces/TraceDetail'))
const DiagnosticsGraphs = lazy(() => import('./pages/Diagnostics/Graphs/Graphs'))
const DiagnosticsGraphRunDetail = lazy(() => import('./pages/Diagnostics/Graphs/GraphRunDetail'))
const DiagnosticsLinks = lazy(() => import('./pages/Diagnostics/Links/Links'))

children: [
  // ...
  { path: 'diagnostics', element: withSuspense(DiagnosticsHome) },
  { path: 'diagnostics/traces', element: withSuspense(DiagnosticsTraces) },
  { path: 'diagnostics/traces/:traceId', element: withSuspense(DiagnosticsTraceDetail) },
  { path: 'diagnostics/graphs', element: withSuspense(DiagnosticsGraphs) },
  { path: 'diagnostics/graphs/:runId', element: withSuspense(DiagnosticsGraphRunDetail) },
  { path: 'diagnostics/links', element: withSuspense(DiagnosticsLinks) },
]
```

#### 8.4.3 URL 与状态同步

- 列表页筛选项必须同步到 query string：`?status=&limit=&offset=`
- Links 页输入也应同步（方便分享）：`?trace_id=` / `?execution_id=` / `?graph_run_id=`

### 8.2 API 口径

- 前端默认只访问 **management 网关**：`/api/...`
- 不直接访问 infra/core 的裸端口（除非明确是开发调试模式）
- 所有列表请求必须支持：`limit/offset`（或 page/pageSize），并在 UI 中保持一致

### 8.3 错误处理

- 所有 API 错误必须标准化为：`{message, detail?, requestId?, traceId?}`
- UI 统一展示：toast + detail expandable

---

## 9. 文档治理与版本

- 文档版本：v4.0
- 最后更新：2026-04-16
- 维护团队：AI Platform 前端团队
- 实现状态请见：`UI_IMPLEMENTATION_STATUS.md`

### 9.1 规范与实现的协作流程（推荐）

1) 任何 UI 改动先改 `UI_DESIGN.md`（To‑Be），明确交互与组件口径  
2) 进入开发后，在 `UI_IMPLEMENTATION_STATUS.md` 记录 As‑Is 进度与差异  
3) 合并后定期收敛差异：实现稳定后把“差异项”从状态文档移除（或标记已完成）
