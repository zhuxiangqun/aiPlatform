---
name: site_tester
display_name: 全站自动化测试
description: 自动遍历所有页面，发现可交互元素，执行全覆盖功能测试。支持多账号、弹窗递归、截图对比、视频录制。不经过LLM推理，确定性执行。 涉及站点相关操作。 主要进行测试。
version: 1.0.0
category: testing
status: enabled
effects:
- type: read
  resources:
  - browser:page
  - filesystem:write
  idempotent: false
  rollback_available: false
output_schema:
  result:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 全站测试
  - 全量测试
  - 回归测试
  - 完整测试
  - 功能验证
  - 站点遍历
  - 全站扫描
  keywords:
    objects:
    - 站点
    - 页面
    - 功能
    actions:
    - 测试
    - 遍历
    - 验证
    - 截图
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 全自动遍历站点执行功能验证
input_schema:
  url:
    type: string
    required: true
    description: 测试站点URL
---

# 全站自动化测试 (Site Tester)

## 功能

自动遍历系统所有路由页面，对每个页面的可交互元素（按钮/输入框/链接/弹窗）执行全覆盖功能测试。

## 核心能力

- **全覆盖遍历**：BFS 广度优先，按路由表逐页测试，弹窗无限递归
- **智能操作**：自动识别元素 role（search_input / submit_button / link / text_input …），生成对应操作
- **安全策略**：默认跳过删除/清空等危险操作，需显式开启
- **多账号**：支持账号池轮换，登录态自动管理
- **输出**：通过/失败布尔报告 + 每步前后截图 + 详细日志

## 使用方式

1. 在 Agent 的 ExecuteAgentModal 中输入测试配置：
   ```json
   {
     "base_url": "https://8.216.36.35",
     "accounts": [{"username": "admin", "password": "admin"}],
     "routes": ["/core/agents", "/workspace/skills"],
     "allow_writes": false,
     "max_recursion_depth": 2
   }
   ```
2. 执行 → Events 流式返回每步结果 → 完成

## 工作流程

1. 登录 → 遍历路由 → 每页 goto → list_elements → 生成操作 → 执行 → 截图 → 检测弹窗 → 递归
2. 所有操作完成后输出测试报告

## 禁止事项

- 禁止凭记忆回答 → 所有操作必须实际执行
- 禁止跳过操作 → 除非标记为危险操作

## 目标
全自动遍历站点执行功能验证

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注