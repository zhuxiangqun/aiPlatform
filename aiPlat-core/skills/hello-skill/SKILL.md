---
name: hello-skill
display_name: Hello Skill
description: 当用户要求“测试 skill 系统”“hello skill”“演示技能目录结构”时，触发该技能。
category: general
version: 0.1.0
trigger_conditions:
  - "hello skill"
  - "测试 skill"
execution_mode: inline
---

# Hello Skill（演示）

## 目标
输出一段固定文本，用于验证：
- 目录化 skill 是否能被发现（discover）
- trigger_conditions 是否能匹配（match）
- 未来若引入 L2 注入/执行，可用本 skill 做最小回归

## 输出
当执行该 skill 时，请输出：`hello-skill: ok`

