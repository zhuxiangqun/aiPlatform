# Leading Words — 工程术语表

这些词汇不是装饰。它们会调用模型已有的工程先验，让不同技能用同一套语言协作。在 SOP 中引用时无需解释——词本身自带先验。

## 核心术语

| 词汇 | 含义 | 模型先验 | 适用场景 |
|------|------|---------|---------|
| **tight loop** | 快速反馈回路 | 每个改动后立即验证，不积压 | debugging / TDD / root_cause_analysis |
| **tracer bullet** | 端到端垂直切片 | 每步可独立验证，不按层级拆 | task_decomposition / task_planning |
| **deep module** | 小接口大实现 | 重构时优先找 leverage 点 | code_review / code-hygiene |
| **seam** | 行为可替换的位置 | 找注入点而非硬改逻辑 | code_review / code_generation |
| **shallow module** | 接口大实现小 | 耦合度高，需拆分 | code-hygiene |
| **vertical slice** | 按功能而非按层拆任务 | 每个 slice 独立可交付 | task_decomposition |
| **red-capable command** | 能稳定复现失败的测试命令 | 没红不修，先建信号 | e2e_test / root_cause_analysis |
| **low information gain** | 新增分析不改变判断 | 停止填表 | data_analysis / information_search |
| **progressive disclosure** | 渐进式加载上下文 | 每步只加载当前需要的规则 | 所有 skill 设计 |

## 使用方式

在 SOP 正文中直接引用，不解释：

```
Use tight loop: every change must be verified by a test before proceeding.
Apply tracer bullet: split into vertical slices, each independently deliverable.
Stop if low information gain: if this analysis won't change the decision, stop.
```

## 设计原则

- **词比解释便宜**：`tight loop` 比"建立一个快速验证的循环"省 5 倍 token
- **先验比指令准**：模型对 `seam` 有工程直觉，比每次重新描述"找可替换的边界"更稳
- **一致性靠复用**：PRD、issue、测试、code review 都用同一套词，模型在不同上下文理解一致
