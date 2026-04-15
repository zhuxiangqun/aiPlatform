# AI Platform UI 设计规范

> 系统级 UI 设计规范 - 统一整个 aiPlatform 系统的前端设计语言和编程标准
> **主题**: 深色主题 (Black Background / White Text)
> **配色参考**: GitHub Dark, Tokyo Night

---

## 目录

- [一、设计原则](#一设计原则)
- [二、视觉设计系统](#二视觉设计系统)
- [三、组件库规范](#三组件库规范)
- [四、交互模式](#四交互模式)
- [五、响应式设计](#五响应式设计)
- [六、动画规范](#六动画规范)
- [七、无障碍标准](#七无障碍标准)
- [八、前端工程规范](#八前端工程规范)
- [九、模块级 UI 设计参考](#九模块级-ui-设计参考)

---

## 一、设计原则

### 1.1 核心原则

| 原则 | 定义 | 实施方法 |
|------|------|----------|
| **一致性** | 整个系统保持统一的视觉和交互语言 | 统一设计系统、组件库、交互模式 |
| **可用性** | 用户能够高效完成任务 | 清晰的视觉层次、直观的操作流程 |
| **性能** | 页面加载和交互响应迅速 | 懒加载、代码分割、缓存策略 |
| **可访问性** | 支持所有用户（包括残障用户） | WCAG 2.1 AA 标准、语义化 markup |
| **可维护性** | 代码结构清晰，易于维护 | 模块化、组件化、文档化 |
| **可扩展性** | 能够方便地添加新功能 | 插件化设计、配置驱动 |

### 1.2 设计目标

1. **效率** - 用户能在最短时间内完成任务
2. **学习成本** - 新用户能快速上手系统
3. **错误恢复** - 错误操作后能轻松恢复
4. **满意度** - 使用过程流畅、愉快

---

## 二、视觉设计系统

### 2.1 颜色系统

#### 2.1.1 品牌色

| Token | Hex | OKLCH | 用途 |
|-------|-----|-------|------|
| `--color-primary` | `#3B82F6` | oklch(62.3% 0.214 259.815) | Primary actions, links, active states |
| `--color-primary-hover` | `#2563EB` | oklch(56.5% 0.245 259.598) | Hover state for primary |
| `--color-primary-active` | `#1D4ED8` | oklch(51.4% 0.261 259.051) | Active/pressed state |
| `--color-primary-light` | `#EFF6FF` | oklch(97.2% 0.026 259.116) | Light backgrounds, badges |

#### 2.1.2 语义色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-success` | `#10B981` | Success states, positive indicators |
| `--color-success-light` | `#ECFDF5` | Success backgrounds |
| `--color-warning` | `#F59E0B` | Warning states |
| `--color-warning-light` | `#FFFBEB` | Warning backgrounds |
| `--color-error` | `#EF4444` | Error states, destructive actions |
| `--color-error-light` | `#FEF2F2` | Error backgrounds |
| `--color-info` | `#3B82F6` | Informational states |

#### 2.1.3 中性色（深色主题）

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-gray-50` | `#161B22` | Hover backgrounds, subtle elements |
| `--color-gray-100` | `#1C2128` | Card backgrounds, elevated surfaces |
| `--color-gray-200` | `#22272E` | Input backgrounds |
| `--color-gray-300` | `#30363D` | Borders, dividers |
| `--color-gray-400` | `#484F58` | Disabled borders, placeholders |
| `--color-gray-500` | `#6E7681` | Muted text, icons |
| `--color-gray-600` | `#8B949E` | Secondary text |
| `--color-gray-700` | `#B1BAC4` | Body text |
| `--color-gray-800` | `#C9D1D9` | Primary text |
| `--color-gray-900` | `#E6EDF3` | Headings, emphasis |

### 2.2 排版系统

#### 2.2.1 字体规范

```css
--font-sans: 'Geist Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
```

#### 2.2.2 字号系统

| Token | Size | Line Height | 用途 |
|-------|------|------------|------|
| `--font-size-xs` | 12px | 16px | Captions, badges |
| `--font-size-sm` | 13px | 20px | Small text, table cells |
| `--font-size-base` | 14px | 22px | Body text |
| `--font-size-lg` | 16px | 24px | Subheadings |
| `--font-size-xl` | 18px | 28px | Section titles |
| `--font-size-2xl` | 20px | 28px | Page titles |
| `--font-size-3xl` | 24px | 32px | Large headings |

#### 2.2.3 字重

| Token | Value | 用途 |
|-------|-------|------|
| `--font-weight-normal` | 400 | Body text |
| `--font-weight-medium` | 500 | Emphasized body |
| `--font-weight-semibold` | 600 | Subheadings |
| `--font-weight-bold` | 700 | Headings |

### 2.3 间距系统

基于 4px 网格。

| Token | Value | 用途 |
|-------|-------|------|
| `--spacing-0` | 0px | None |
| `--spacing-1` | 4px | Tight gaps |
| `--spacing-2` | 8px | Small gaps |
| `--spacing-3` | 12px | Medium gaps |
| `--spacing-4` | 16px | Default padding |
| `--spacing-5` | 20px | Card padding |
| `--spacing-6` | 24px | Section spacing |
| `--spacing-8` | 32px | Large spacing |
| `--spacing-10` | 40px | Page sections |
| `--spacing-12` | 48px | Major sections |

### 2.4 阴影系统

| Token | Value | 用途 |
|-------|-------|------|
| `--shadow-xs` | `0 1px 2px rgba(0,0,0,0.04)` | Subtle lift |
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)` | Cards, dropdowns |
| `--shadow-md` | `0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.04)` | Elevated elements |
| `--shadow-lg` | `0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)` | Modals, popovers |
| `--shadow-xl` | `0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.04)` | Large dialogs |

### 2.5 圆角系统

| Token | Value | 用途 |
|-------|-------|------|
| `--radius-sm` | 6px | Buttons, inputs |
| `--radius-md` | 8px | Cards, modals |
| `--radius-lg` | 12px | Large cards |
| `--radius-xl` | 16px | Feature cards |
| `--radius-2xl` | 20px | Modal dialogs |
| `--radius-full` | 9999px | Pills, avatars |

---

## 三、组件库规范

### 3.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.x | 核心框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 |
| **Tailwind CSS** | 3.x | 样式框架 |
| **Framer Motion** | 11.x | 动画库 |
| **Lucide React** | - | 图标库 |
| Zustand | 4.x | 状态管理 |
| React Router | 6.x | 路由管理 |

### 3.2 自定义 UI 组件库

位于 `/src/components/ui/`，基于 Tailwind CSS 构建的轻量级组件库：

```typescript
import { Button, Card, Table, Modal, Input, Select, Tabs, Badge, Progress, Switch, Pagination } from '@/components/ui';
```

#### 可用组件

| 组件 | 说明 | 变体 |
|------|------|------|
| `Button` | 按钮 | primary, secondary, danger, ghost |
| `Card` | 动画卡片 | - |
| `Table` | 数据表格 | - |
| `Modal` | 动画弹窗 | - |
| `Input` | 输入框 | - |
| `Textarea` | 多行文本 | - |
| `Select` | 选择器 | - |
| `Tabs` | 标签页 | - |
| `Badge` | 徽章 | default, success, warning, error, info |
| `Tag` | 标签 | - |
| `Progress` | 进度条 | - |
| `Switch` | 开关 | - |
| `Pagination` | 分页 | - |
| `Statistic` | 统计卡片 | - |
| `Empty` | 空状态 | - |
| `Alert` | 提示框 | success, error, warning, info |

### 3.3 按钮规范

```tsx
<Button variant="primary" icon={<Plus size={16} />}>主要操作</Button>
<Button variant="secondary">次要操作</Button>
<Button variant="danger">危险操作</Button>
<Button variant="ghost">幽灵按钮</Button>
<Button loading>加载中</Button>
```

### 3.4 卡片规范

```tsx
<Card hoverable onClick={() => navigate('/detail')}>
  <h3>卡片标题</h3>
  <p>卡片内容</p>
</Card>
```

### 3.5 表格规范

```tsx
const columns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '状态', dataIndex: 'status', key: 'status', 
    render: (val) => <Badge variant="success">{val}</Badge> 
  },
  { title: '操作', key: 'actions',
    render: (_, record) => <Button onClick={() => handleEdit(record)}>编辑</Button>
  },
];

<Table columns={columns} data={list} rowKey="id" loading={loading} />
```

### 3.6 布局规范

#### Header

| Property | Value |
|----------|-------|
| Height | 60px |
| Background | `#0D1117` |
| Border Bottom | `1px solid #30363D` |

#### Sidebar

| Property | Value |
|----------|-------|
| Width (expanded) | 240px |
| Width (collapsed) | 64px |
| Background | `#0D1117` |
| Item Height | 44px |
| Item Active | `background: #1C2128; color: #3B82F6` |

---

## 四、交互模式

### 4.1 Loading 状态

```tsx
// 骨架屏 - 推荐用于内容区域
<Skeleton />

// 加载中 - 用于按钮等小型区域
<Button loading>提交</Button>

// 进度条 - 用于文件上传等长时间操作
<Progress value={percent} />
```

### 4.2 空状态

```tsx
<Empty description="暂无数据" />
```

### 4.3 确认流程

```tsx
// 危险操作确认
<Modal
  open={deleteConfirm.open}
  onClose={() => setDeleteConfirm({ open: false })}
  title="确认删除"
  footer={
    <>
      <Button onClick={onCancel}>取消</Button>
      <Button variant="danger" onClick={onConfirm}>确认删除</Button>
    </>
  }
>
  <p>确定要删除吗？此操作不可撤销。</p>
</Modal>
```

### 4.4 Toast 提示

使用浏览器原生 `alert()` 或自定义 toast 组件：

```tsx
alert('操作成功');
alert('操作失败');
```

---

## 五、响应式设计

### 5.1 断点定义

| Breakpoint | Min Width | 设备 |
|------------|-----------|------|
| sm | 640px | Small tablets |
| md | 768px | Tablets |
| lg | 1024px | Laptops |
| xl | 1280px | Desktops |
| 2xl | 1536px | Large screens |

### 5.2 网格系统

```tsx
// 移动端：单列
<div className="grid grid-cols-1">

// 平板：2列
<div className="grid grid-cols-2">

// 小桌面：3列
<div className="grid grid-cols-3">

// 大桌面：4列
<div className="grid grid-cols-4">
```

---

## 六、动画规范

### 6.1 动画时长

| Token | Value | 用途 |
|-------|-------|------|
| `--duration-fast` | 100ms | Micro-interactions |
| `--duration-normal` | 150ms | Default transitions |
| `--duration-slow` | 200ms | Page transitions |
| `--duration-slower` | 300ms | Modal, drawer |

### 6.2 缓动函数

| Token | Value | 用途 |
|-------|-------|------|
| `--ease-default` | cubic-bezier(0.4, 0, 0.2, 1) | Default |
| `--ease-in` | cubic-bezier(0.4, 0, 1, 1) | Enter |
| `--ease-out` | cubic-bezier(0, 0, 0.2, 1) | Exit |
| `--ease-bounce` | cubic-bezier(0.34, 1.56, 0.64, 1) | Bounce |

### 6.3 Framer Motion 使用

```tsx
import { motion } from 'framer-motion';

// 淡入上移动画
<motion.div
  initial={{ opacity: 0, y: 8 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.15 }}
>
  {children}
</motion.div>

// 弹窗动画
<motion.div
  initial={{ opacity: 0, scale: 0.95 }}
  animate={{ opacity: 1, scale: 1 }}
  exit={{ opacity: 0, scale: 0.95 }}
>
  {children}
</motion.div>
```

---

## 七、无障碍标准

### 7.1 WCAG 2.1 AA 合规

- 文本对比度 >= 4.5:1
- 所有功能可通过键盘操作
- 所有交互元素有焦点可见状态
- 使用语义化 HTML

### 7.2 焦点状态

```css
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

### 7.3 ARIA 属性

```tsx
<button aria-label="关闭" />
<div role="dialog" aria-modal="true" />
```

---

## 八、前端工程规范

### 8.1 项目结构

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # UI 组件库
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Table.tsx
│   │   │   └── ...
│   │   ├── layout/         # 布局组件
│   │   │   └── AppLayout.tsx
│   │   └── core/           # 业务组件
│   │
│   ├── pages/              # 页面组件
│   │   ├── Overview/
│   │   ├── Core/
│   │   ├── Platform/
│   │   ├── App/
│   │   └── Infra/
│   │
│   ├── services/           # API 服务
│   ├── stores/             # 状态管理
│   ├── styles/             # 样式
│   │   ├── tokens.css
│   │   └── theme.ts
│   │
│   ├── App.tsx
│   └── main.tsx
│
├── tailwind.config.js
├── postcss.config.js
├── SPEC.md
└── package.json
```

### 8.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 组件文件 | PascalCase | `Button.tsx`, `UserProfile.tsx` |
| 工具函数 | camelCase | `formatDate.ts`, `usePagination.ts` |
| 样式文件 | kebab-case | `button-styles.css` |
| 常量 | UPPER_CASE | `API_BASE_URL` |
| 接口/类型 | PascalCase | `interface UserInfo {}` |

### 8.3 图标规范

使用 `lucide-react` 图标库：

```tsx
import { Plus, RotateCw, Trash2, Settings } from 'lucide-react';

// 图标尺寸
<Plus size={14} />  // inline with text
<Plus size={16} />  // buttons
<Plus size={20} />  // default
<Plus size={24} />  // headers, prominent
```

---

## 九、模块级 UI 设计参考

### 9.1 页面层级

```
┌─────────────────────────────────────────────────────────────┐
│ Header (60px)                                               │
├──────────────┬────────────────────────────────────────────┤
│              │                                            │
│  Sidebar     │  Page Header                              │
│  (240px)     │  - Title (20px, bold)                    │
│              │  - Description (14px, gray)                │
│              │  - Actions (right aligned)                 │
│              │                                            │
│              │  Stats Row (optional)                      │
│              │  ┌────┐ ┌────┐ ┌────┐ ┌────┐            │
│              │  │Card│ │Card│ │Card│ │Card│            │
│              │  └────┘ └────┘ └────┘ └────┘            │
│              │                                            │
│              │  Content Card                             │
│              │                                            │
│              │                                            │
└──────────────┴────────────────────────────────────────────┘
```

### 9.2 颜色使用指南（深色主题）

| 场景 | 颜色 |
|------|------|
| 页面背景 | `#0D1117` |
| 卡片背景 | `#161B22` |
| 边框色 | `#30363D` |
| 文本主色 | `#E6EDF3` |
| 文本次色 | `#8B949E` |
| 主要按钮 | `#3B82F6` |
| 成功状态 | `#10B981` |
| 警告状态 | `#F59E0B` |
| 错误状态 | `#EF4444` |

---

## 十、CRUD 交互规范

### 10.1 通用 CRUD 模式

所有管理页面应遵循统一的 CRUD（创建、读取、更新、删除）交互模式：

| 操作 | 触发方式 | 交互组件 | 确认方式 |
|------|----------|----------|----------|
| **创建** | 顶部"创建"按钮 | Modal 表单（Ant Design） | 无需二次确认 |
| **查看详情** | 列表名称点击 | Modal / Drawer | 无需确认 |
| **编辑** | 操作列编辑按钮 | Modal 表单（Ant Design） | 无需二次确认 |
| **删除** | 操作列删除按钮 | 确认弹窗 | 需二次确认 |

### 10.2 Agent 管理交互规范

#### 列表页 `pages/Core/Agents/Agents.tsx`

- 操作列包含：**编辑**、启动、停止、执行、删除
- 点击 Agent 名称可查看详情
- 编辑操作弹出 `EditAgentModal`

#### 创建 Agent `components/core/AddAgentModal.tsx`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | Input | 是 | Agent 名称 |
| agent_type | Select | 是 | 类型：base/react/plan/tool |
| config | TextArea | 否 | JSON 格式配置 |
| skills | MultiSelect | 否 | 绑定的 Skill 列表 |
| tools | MultiSelect | 否 | 绑定的 Tool 列表 |

> **Agent-Skill-Tool 绑定关系**：Agent 通过 skills 和 tools 字段关联到 Skill 和 Tool。这些绑定关系存储在 `AgentInfo.tools` 和 `AgentInfo.skills` 中，需要后端 API 完整返回。

#### API 数据完整性问题

**已修复**：后端 API 现在完整返回 Agent 的 skills 和 tools 绑定数据。

| 接口 | 问题 | 状态 |
|------|------|------|
| `GET /agents` | 列表不返回 `skills` 和 `tools` 字段 | ✅ 已修复 |
| `GET /agents/{id}` | 详情不返回 `skills` 和 `tools` | ✅ 已修复 |
| `GET /agents/{id}/tools` | 返回硬编码空数组 `[]` | ✅ 已修复：从 `AgentInfo.tools` 读取 |
| `GET /agents/{id}/skills` | 不存在 | ✅ 已修复：返回 `AgentInfo.skills` |
| `POST /agents/{id}/skills` | 不存储绑定 | ✅ 已修复：调用 `AgentManager.bind_skills()` |
| `POST /agents/{id}/tools` | 不存储绑定 | ✅ 已修复：调用 `AgentManager.bind_tools()` |
| `DELETE /agents/{id}/skills/{skill_id}` | 不执行解绑 | ✅ 已修复：调用 `AgentManager.unbind_skill()` |
| `DELETE /agents/{id}/tools/{tool_id}` | 不执行解绑 | ✅ 已修复：调用 `AgentManager.unbind_tool()` |

**Agent 种子数据 Tool ID 已统一**：种子数据现在使用 `search`、`calculator` 等与 ToolRegistry 一致的 ID。

#### 编辑 Agent `components/core/EditAgentModal.tsx`（新增）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | Input | 是 | Agent 名称（预填当前值） |
| agent_type | Select | 是 | 类型（预填当前值，不可修改） |
| config | TextArea | 否 | JSON 格式配置（预填当前值） |

交互流程：
1. 用户点击编辑按钮 → 打开 `EditAgentModal`
2. Modal 预填当前 Agent 数据
3. 用户修改字段后点击"保存"
4. 调用 `agentApi.update(agentId, { config })` 提交修改
5. 成功后关闭 Modal 并刷新列表
6. 失败时显示错误提示

> **注意**：Agent 的 `agent_type` 创建后不可修改，编辑时该字段置灰（disabled）。

### 10.3 Skill 管理交互规范

#### 列表页 `pages/Core/Skills/Skills.tsx`

- 操作列包含：**编辑**、启用/禁用（Switch）、删除
- 编辑操作弹出 `EditSkillModal`

| 列 | 宽度 | 说明 |
|------|------|------|
| 名称 | - | Skill 名称，font-medium |
| 描述 | - | Skill 功能描述，text-gray-500 |
| 分类 | 100px | 标签形式显示 |
| 状态 | 100px | Switch 组件 |
| ID | 100px | 截断显示前8位 |
| 操作 | 140px | 执行、编辑、删除 |

#### 创建 Skill `components/core/AddSkillModal.tsx`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | Input | 是 | Skill 名称 |
| category | Select | 是 | 分类：general/reasoning/coding/search/tool/communication |
| description | TextArea | 否 | 描述 |
| config | TextArea | 否 | JSON 格式配置 |

#### 编辑 Skill `components/core/EditSkillModal.tsx`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | Input | 是 | Skill 名称（预填当前值） |
| category | Select | 是 | 分类（预填当前值） |
| description | TextArea | 否 | 描述（预填当前值） |
| config | TextArea | 否 | JSON 格式配置（预填当前值） |

> **数据加载**：编辑弹窗打开时，先调用 `skillApi.get(skillId)` 获取详情并预填。
> 详情接口 `/core/skills/{id}` 当前仅返回 `id, name, type, description, status, enabled`，缺少 `config` 字段。
> **后端已修改**：详情接口和列表接口现在都返回 `config`、`input_schema`、`output_schema` 字段。
> 字段映射：`detail.category || detail.type` 兼容处理。

交互流程：
1. 用户点击编辑按钮 → 打开 `EditSkillModal`
2. Modal 打开时调用 `skillApi.get(skillId)` 获取详情
3. 加载中显示 Spin loading 状态
4. 数据返回后预填 name、category、description、config 字段
5. 用户修改字段后点击"保存"
6. 调用 `skillApi.update(skillId, data)` 提交修改
7. 成功后关闭 Modal 并刷新列表
8. 失败时显示错误提示

#### Agent 详情弹窗 `components/core/AgentDetailModal.tsx`（Phase 5 新增）

点击 Agent 列表中的名称时打开，显示 Agent 完整信息。

| 字段 | 说明 |
|------|------|
| ID | Agent ID，mono 字体 |
| 类型 | Agent 类型，中文标签 |
| 状态 | 运行状态，带颜色标识 |
| 绑定技能 | 蓝色徽章显示绑定的 Skill ID |
| 绑定工具 | 紫色徽章显示绑定的 Tool ID |
| 配置 | JSON 格式展示 |

### 10.4 编辑弹窗设计规范

#### 布局规范

```
┌──────────────────────────────────┐
│  编辑 Agent / Skill      ✕      │  ← 标题 + 关闭按钮
├──────────────────────────────────┤
│                                  │
│  名称 *                          │
│  ┌──────────────────────────┐   │
│  │ 预填当前值                  │   │
│  └──────────────────────────┘   │
│                                  │
│  类型 *                          │
│  ┌──────────────────────────┐   │
│  │ 预填当前值  ▼              │   │  ← Agent: disabled
│  └──────────────────────────┘   │
│                                  │
│  配置 / 描述                     │
│  ┌──────────────────────────┐   │
│  │ 预填当前值                  │   │
│  │                            │   │
│  └──────────────────────────┘   │
│                                  │
├──────────────────────────────────┤
│              取消      保存      │  ← 底部按钮
└──────────────────────────────────┘
```

#### 深色主题样式

| 元素 | 样式 |
|------|------|
| Modal 背景 | `bg-dark-card` (#161B22) |
| Modal 边框 | `border-dark-border` (#30363D) |
| 表单标签 | `text-gray-300` |
| 输入框背景 | `bg-dark-card` + `border-dark-border` |
| 输入框文字 | `text-gray-100` |
| 次要按钮 | `bg-dark-card text-gray-300 border-dark-border` |
| 主要按钮 | `bg-primary text-white` |

### 10.5 文件变更清单

| 变更 | 文件 | 说明 |
|------|------|------|
| 新增 | `components/core/EditAgentModal.tsx` | Agent 编辑弹窗 |
| 新增 | `components/core/EditSkillModal.tsx` | Skill 编辑弹窗 |
| 修改 | `components/core/index.ts` | 导出新组件 |
| 修改 | `pages/Core/Agents/Agents.tsx` | 添加编辑按钮，接入 EditAgentModal |
| 修改 | `pages/Core/Skills/Skills.tsx` | 添加编辑按钮，接入 EditSkillModal |

### 10.6 Tool 管理交互规范

#### 列表页 `pages/Core/Tools/Tools.tsx`（新增）

- 操作列包含：**执行**、**编辑配置**、**查看详情**
- 支持按分类筛选
- 显示 Tool 的名称、描述、分类、调用统计

| 列 | 宽度 | 说明 |
|------|------|------|
| 名称 | - | Tool 名称，可点击查看详情 |
| 描述 | - | Tool 功能描述 |
| 分类 | 100px | 标签形式显示 |
| 调用次数 | 100px | 累计调用次数 |
| 成功率 | 100px | 成功百分比 |
| 操作 | 140px | 执行、编辑配置、详情 |

#### Tool 详情弹窗 `components/core/ToolDetailModal.tsx`（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| name | 文本 | Tool 名称 |
| description | 文本 | Tool 功能描述 |
| category | 文本 | 分类 |
| parameters | JSON | 输入参数 Schema |
| config | JSON | Tool 配置（超时、并发数等） |
| stats | 文本 | 调用次数、成功率、平均延迟 |

> **编辑范围**：Tool 的核心定义（名称、描述、参数 Schema）由系统注册，不可修改。**只有 config 配置参数可编辑**，如超时时间、最大并发数等运行时参数。

#### Tool 配置编辑弹窗 `components/core/EditToolConfigModal.tsx`（新增）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 超时时间(秒) | InputNumber | 否 | config.timeout_seconds |
| 最大并发数 | InputNumber | 否 | config.max_concurrent |
| 重试次数 | InputNumber | 否 | config.retry_count |

交互流程：
1. 用户点击"编辑配置"按钮 → 打开 `EditToolConfigModal`
2. 弹窗从 `toolApi.get(toolName)` 获取当前 config 并预填
3. 用户修改配置参数后点击"保存"
4. 调用 `PUT /core/tools/{name}` 提交 config 修改
5. 成功后关闭弹窗并刷新列表

#### 数据来源

| API | 方法 | 路径 | 说明 |
|-----|------|------|------|
| toolApi.list | GET | `/core/tools` | 列出所有 Tool |
| toolApi.get | GET | `/core/tools/{name}` | 获取 Tool 详情 |
| toolApi.getStats | GET | `/core/tools/stats` | 获取 Tool 调用统计 |
| toolApi.execute | POST | `/core/tools/{name}/execute` | 执行 Tool |
| toolApi.update | PUT | `/core/tools/{name}` | 更新 Tool 配置 |

### 10.7 执行测试交互规范

各核心能力层模块应支持在线测试执行，方便开发者快速验证功能。

#### Skkill 执行 `components/core/ExecuteSkillModal.tsx`（新增）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| skill_id | 隐藏 | - | 当前 Skill ID |
| input | TextArea | 否 | JSON 或文本输入 |

交互流程：
1. 用户在 Skill 列表点击"执行"按钮 → 打开 `ExecuteSkillModal`
2. 填入输入参数（JSON 或纯文本）
3. 点击"执行" → 调用 `skillApi.execute(skillId, input)`
4. 在弹窗内显示执行结果（成功/失败、输出内容、耗时）

#### Tool 执行 `components/core/ExecuteToolModal.tsx`（新增）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tool_name | 隐藏 | - | 当前 Tool 名称 |
| parameters | 动态表单 | 视Schema | 根据 Tool 参数 Schema 自动生成输入字段 |

> **重要**：Tool 的 `parameters` 字段是 JSON Schema 格式，包含每个参数的 `type`、`description`、`required`、`default` 等信息。**执行弹窗应根据 Schema 自动生成表单字段**，而非让用户手写 JSON。
> - `type: string` → 文本输入框
> - `type: integer` / `type: number` → 数字输入框
> - `type: string, enum: [...]` → 下拉选择框
> - `required: true` 的字段标记必填
> - `default` 值自动填入

交互流程：
1. 用户在 Tool 列表点击"执行"按钮 → 打开 `ExecuteToolModal`
2. 弹窗自动从 Tool 的 `parameters` Schema 解析字段，生成表单
3. 用户填写参数后点击"执行"
4. 前端根据表单值自动组装为 JSON 对象，调用 `toolApi.execute(toolName, params)`
5. 在弹窗内显示执行结果

> **搜索工具真实性**：`SearchTool` 已接入 DuckDuckGo Lite 真实搜索，返回真实搜索结果（标题、URL、摘要）。如果搜索服务不可用，自动降级为 mock 数据。

#### 搜索工具搜索结果字段

| 字段 | 说明 |
|------|------|
| title | 搜索结果标题 |
| url | 搜索结果链接 |
| snippet | 搜索结果摘要（前200字） |
| source | 来源标识（duckduckgo / mock） |

### 10.8 文件变更清单（Tool管理 + 执行测试）

| 变更 | 文件 | 说明 |
|------|------|------|
| 新增 | `pages/Core/Tools/Tools.tsx` | Tool 列表页 |
| 新增 | `components/core/ToolDetailModal.tsx` | Tool 详情弹窗 |
| 新增 | `components/core/ExecuteSkillModal.tsx` | Skill 执行弹窗 |
| 新增 | `components/core/ExecuteToolModal.tsx` | Tool 执行弹窗 |
| 新增 | `components/core/EditToolConfigModal.tsx` | Tool 配置编辑弹窗 |
| 修改 | `components/core/index.ts` | 导出新组件 |
| 修改 | `pages/Core/Skills/Skills.tsx` | 添加执行按钮，接入 ExecuteSkillModal |
| 修改 | `pages/Core/Tools/Tools.tsx` | 添加执行、编辑配置、详情按钮 |
| 修改 | `components/layout/AppLayout.tsx` | 侧边栏添加 Tool 管理入口 |
| 修改 | `App.tsx` | 添加 `/core/tools` 路由 |
| 修改 | `services/coreApi.ts` | 添加 toolApi、skillApi.execute 方法 |

---

## 附录

### A. 参考资源

- [Tailwind CSS](https://tailwindcss.com/) - Utility-first CSS framework
- [Framer Motion](https://www.framer.com/motion/) - Animation library
- [Lucide](https://lucide.dev/) - Beautiful open source icons
- [Google AI Studio](http://106.38.198.112:81/) - Design reference

### B. 技术决策记录 (ADR)

#### ADR-001: 迁移到 Tailwind CSS

**决策**: 采用 Tailwind CSS + 自定义组件库替代 Ant Design

**背景**:
- 参考网站使用 Tailwind CSS 风格
- 需要更灵活的样式控制
- Ant Design 样式难以完全定制

**备选方案**:
| 方案 | 优点 | 缺点 |
|------|------|------|
| Tailwind CSS | 灵活、构建时优化、无运行时 | 需要学习成本 |
| Ant Design | 组件完整、文档丰富 | 定制困难、包体积大 |
| CSS Modules | 简单、无依赖 | 无设计系统 |

---

**文档版本**: v3.5  
**最后更新**: 2026-04-15  
**维护团队**: AI Platform 前端团队  
**适用范围**: aiPlatform 全系统前端开发  
**主题**: 深色主题 (Black Background / White Text)
