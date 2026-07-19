> ⚠️ **已归档** — 本文档为历史版本，API 引用可能已过期。最新文档请参见 [FDE 交付手册](../fde-delivery-manual.md)。

# Workflow 创建指南 — {{PROJECT_NAME}}

> **配套交付手册**：`fde-delivery-manual.md` | **适用阶段**：行前准备 / Phase 2
> **FDE 常用节点**：start / agent / condition / end（4 种），其余 12 种为开发域。

---

## 1. 创建 Workflow

| 步骤 | 操作 | 路径 |
|:---:|------|------|
| 1 | 进入 Workflow 库 | 应用能力层 → Workflow 库 |
| 2 | 点击新建 | 进入画布页面 |
| 3 | 命名 | `{{PROJECT_NAME}} 工作流` |
| 4 | 拖拽节点到画布 | 从左侧面板拖拽对应节点类型到画布 |
| 5 | 配置 Agent 节点 | 双击 agent 节点 → 选择 "{{AGENT_NAME}}" |
| 6 | 连线 | 从节点底部 Handle 拖线到目标节点顶部 Handle |
| 7 | 保存 | Ctrl+S 或点击「保存」按钮 |
| 8 | 测试 | 点击「运行」→ 确认各节点产出正确 |

---

## 2. FDE 常用节点

| 节点 | 图标 | 用途 | FDE 操作 |
|------|:--:|------|------|
| **start** | ▶️ | 工作流入口 | 直接拖拽，无需配置 |
| **agent** | 🤖 | AI Agent 执行 | 双击 → 选择 "{{AGENT_NAME}}" → 配置 model/skills |
| **condition** | 🔀 | 条件分支 True/False | 双击 → 设置判断表达式 |
| **end** | 🏁 | 工作流出口 | 直接拖拽，无需配置 |

> **其余节点**（llm / code / http / template / knowledge / tool / loop / human / list / aggregator / assigner / extractor）属于开发域，FDE 通常不需要。

---

## 3. 典型拓扑示例

```
{{NODE_EXAMPLES}}
```

### 连线规则

| 规则 | 说明 |
|------|------|
| 每条连线方向：源节点 Handle（底部）→ 目标节点 Handle（顶部） | 不可反向、不可自连 |
| 同一对节点之间只能有一条线 | 不可重复连线 |
| condition 节点最多 2 条出线 | True（绿色）/ False（红色）|
| 保存前执行前，所有节点必须是 idle 状态 | 灰色边框 = 未开始 |

---

## 4. 与交付手册的对照

| 交付手册章节 | 对应操作 |
|------|------|
| 0.5 Workflow 可用 | 按本指南创建后，节点拓扑应完整、无断连 |
| 2.3 Workflow 复核 | 核查节点绑定 → 测试执行 → 确认产出 |

---

## 5. 常见问题

| 问题 | 处理 |
|------|------|
| 运行按钮灰色 | 先保存（Ctrl+S），运行按钮变为可用 |
| Agent 节点无法选择 Agent | 确认 Agent 已创建且状态为 ready（见 Agent 创建指南） |
| Condition 节点无法连线第 3 条 | 设计限制：最多 2 条出线（True/False）。使用多个 Condition 组合 |
| 运行报错"节点未找到" | 检查绑定的 Agent/Skill 是否已启用 |
| 运行后无输出 | 双击节点查看 `_output` 字段；检查执行日志 |

---
*由 aiPlat FDE 工作台自动生成 — {{GENERATED_AT}}*
