---
name: site_tester
display_name: 全站自动化测试
description: 自动遍历所有页面，发现可交互元素，执行全覆盖功能测试。支持多账号、弹窗递归、截图对比、视频录制。不经过LLM推理，确定性执行。
version: 1.0.0
category: testing
effects:
  - type: read
    resources: ["browser:page", "filesystem:write"]
    idempotent: false
    rollback_available: false
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
