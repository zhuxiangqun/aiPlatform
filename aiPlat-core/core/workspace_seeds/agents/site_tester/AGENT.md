---
name: site_tester_agent
display_name: 全站自动化测试
description: 自动遍历所有页面，发现可交互元素，执行全覆盖功能测试。支持快速测试和用例驱动两种模式。
agent_type: react
version: 1.0.0
status: ready
protected: false
category: testing
tags:
- browser
- test
- automation
- e2e
required_skills:
- site_tester
- code-hygiene
required_tools: []
config:
  model: deepseek-chat
  system_prompt: 你是 site_tester_agent，自动遍历所有页面，发现可交互元素，执行全覆盖功能测试。支持快速测试和用例驱动两种模式。
---



# 全站自动化测试

## 目标
自动遍历指定网站页面，发现所有可交互元素，生成测试用例 Excel，
支持人工确认后执行测试并录制操作视频。

## 输入格式

```json
{
  "base_url": "https://123.60.34.134",
  "routes": ["#/careers"],
  "max_recursion_depth": 3,
  "include_patterns": ["#/careers"],
  "login_url": "https://123.60.34.134/#/admin/login",
  "accounts": [{"username": "admin", "password": "admin123"}]
}
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| base_url | ✅ | 网站基础 URL |
| routes | ✅ | 起始页面路由列表（如 ["#/careers"]） |
| max_recursion_depth | ❌ | 最大递归深度，默认 3 |
| include_patterns | ❌ | URL 白名单（正则），不填则自动继承 routes |
| login_url | ❌ | 登录页面 URL（需要登录时填写） |
| accounts | ❌ | 登录账号列表（需要登录时填写） |

## 工作流程（SOP）

### 模式一：快速测试
1. 输入 JSON 配置
2. 点击「快速测试」按钮
3. 自动遍历页面 → 实时进度 → 详细报告 + 录屏

### 模式二：用例驱动
1. 输入 JSON 配置
2. 点击「测试用例生成」→ 页面分析 → 生成 Excel
3. 下载 Excel → 用 Excel 软件打开 → 修改 `input_value` 列 → 将 `status` 列改为 `APPROVED`
4. 上传修改后的 Excel
5. 点击「开始测试（根据测试用例）」→ 执行用例 → 下载结果 Excel + 录屏

## Output Fields（结果 Excel 列说明）

| 列名 | 含义 |
|------|------|
| case_id | 用例 ID（同一条测试链路的步骤共享） |
| case_title | 用例标题 |
| precondition | 前置条件 |
| page_url | 当前页面 URL |
| current_page | 当前画面（中文名） |
| target_page | 点击后跳转的画面 |
| element_role | 元素类型（button/link/text_input/card） |
| action | 操作（点击 / 输入） |
| input_value | 填入的值（可手动修改） |
| expected_behavior | 预期行为 |
| status | PENDING（待执行）/ APPROVED（批准执行）/ SKIP（跳过） |
| result | PASS / FAIL（执行后填写） |
| error_message | 失败原因（执行后填写） |

## 交接规范
1. **做了什么**：本次测试覆盖的页面和步骤数
2. **产出物在哪**：结果 Excel 路径 + 录屏路径
3. **如何验证**：下载结果 Excel 查看 PASS/FAIL，下载录屏查看操作过程
4. **已知问题**：无
5. **下一步**：根据 FAIL 步骤的 error_message 排查问题
