---
name: planner-product-spec
description: 将用户 1-4 句需求扩展为可交付产品 spec（含里程碑/任务分解/验收标准），用于长程工作与多 agent handoff
version: 0.1.0
executable: false
category: planning
capabilities:
  - spec
  - decomposition
  - handoff
---

# Planner：产品 Spec 扩展与任务分解（SOP）

## 目标
把“简短需求”扩展成**可执行、可验收、可交接**的产品规格说明（Spec），并输出结构化 artifacts，便于：
- generator 按任务逐步实现
- evaluator 依据验收标准自动/半自动验证
- 支持 context reset（通过 artifacts handoff，而不是长对话堆叠）

## 输入（你需要向我提供）
1) 用户原始需求（1~4 句即可）  
2) 约束（可选）：技术栈/部署环境/权限限制/截止时间/必须不做的事情  
3) 目标用户与场景（可选）：谁用？在什么环境用？  

## 输出（必须按此结构输出）

### A. Product Spec（Markdown）
至少包含：
1. 背景与目标（Goals / Non-goals）
2. 用户画像与核心场景（User stories）
3. 关键功能清单（MVP → vNext）
4. 数据模型/接口概览（如适用）
5. 关键交互与页面/流程（如适用）
6. 风险与假设（Risks / Assumptions）

### B. Sprint / Milestones（结构化）
输出一个任务列表，每个任务必须包含：
- `id`：稳定编号（如 `M1-T03`）
- `title`：任务标题
- `type`：`frontend|backend|db|infra|docs|test`
- `acceptance`：验收点（可测试/可观察）
- `dependencies`：依赖任务 id（可空）
- `risk_level`：`low|medium|high`（用于审批/治理）

建议用 JSON 输出：
```json
{
  "milestones": [
    {
      "id": "M1",
      "title": "MVP",
      "tasks": [
        {
          "id": "M1-T01",
          "title": "初始化项目骨架",
          "type": "infra",
          "acceptance": ["项目可启动", "基础路由可访问"],
          "dependencies": [],
          "risk_level": "low"
        }
      ]
    }
  ]
}
```

### C. Handoff Artifact（给 generator / evaluator）
输出一个**可直接复制保存为文件**的 handoff（建议命名 `handoff.json`）：
```json
{
  "spec_version": "0.1.0",
  "context": {
    "target_users": "",
    "constraints": [],
    "tech_stack": [],
    "out_of_scope": []
  },
  "milestone_order": ["M1", "M2"],
  "tasks": [
    {
      "id": "M1-T01",
      "title": "",
      "acceptance": [],
      "notes": ""
    }
  ],
  "definition_of_done": [
    "核心路径可用",
    "至少一轮 evaluator 通过",
    "关键风险已记录"
  ]
}
```

## 质量标准（强制）
- **不要**在 spec 中写“实现细节微观到代码层面的逐行设计”，保持在可交付的系统级别
- **必须**把“主观目标”改写为“可评分/可验收”的维度（例如：交互一致性、关键路径完成率、错误处理）
- 对于不确定项：明确写为假设 + 如何验证（不要隐式猜测）

## 推荐协作流程（与 aiPlat 对齐）
1) Planner（本 SOP）输出 spec + tasks + handoff.json  
2) Generator 按 tasks 实现（每次提交一个可运行增量）  
3) Evaluator 根据 acceptance 自动验证并出具评分与问题列表  
4) 如失败：generator 修复 → evaluator 再评估  
5) 必要时执行 context reset：只携带 `handoff.json` + evaluator 报告进入新 session

