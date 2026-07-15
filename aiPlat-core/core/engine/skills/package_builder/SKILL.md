---
name: package_builder
display_name: 部署包构建器
description: 根据方案设计和客户画像，生成完整的部署包，包含组件清单、可执行部署脚本、集成测试计划、回滚方案和风险矩阵。
version: 2.0.0
category: fde
status: enabled
execution_type: prompt
effects:
  - type: write
    resources: ["filesystem:/tmp"]
    idempotent: false
    rollback_available: true
input_schema:
  type: object
  properties:
    solution_design:
      type: object
      description: 方案设计
    customer_profile:
      type: object
      description: 客户画像（含deployment_mode）
  required:
    - solution_design
output_schema:
  type: object
  properties:
    markdown:
      type: string
    deployment_package:
      type: object
  required:
    - markdown
---

### SOP 执行指引
1. 读取 customer_profile.deployment_mode 确定部署模式(online/airgap/hybrid)。
2. 收集包清单：本体YAML、Wiki页面、GraphIndex JSON、Skill定义。
3. 生成6大模块输出：
   - components: [{name, version, description, dependencies}]
   - deployment_steps: [{step_number, action, command, expected_result, rollback_command}] (每步含可执行命令)
   - test_plan: [{test_id, description, preconditions, steps, expected_outcome}] (≥3条)
   - rollback_plan: [{step, trigger_condition, command, verification}]
   - risk_matrix: [{risk, probability(0-1), impact(high|medium|low), mitigation, contingency}] (≥5项)
   - config_checklist: [{item, current_value, expected_value, action, verified}]

### 部署模式说明
- online: YAML + Wiki + Skills（最小部署包）
- airgap: 全量文件 + 模型checkpoints（离线包）
- hybrid: 模型文件 + 代理配置（混合部署）

### 反模式
- 不要生成空命令字符串
- 不要遗漏回滚步骤
- 不要跳过测试计划
- 风险矩阵必须≥5项
