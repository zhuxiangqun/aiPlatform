---
name: architecture_design
display_name: 系统架构设计
description: 根据PRD需求设计完整、详细、可落地的系统架构，输出结构化JSON。触发条件：pipeline architecture阶段。跳过条件：纯文本需求（无技术约束）。
category: design
version: 1.0.0
status: enabled
execution_type: prompt
triggers:
  - 架构设计
  - architecture design
  - 系统设计
  - system design
permissions:
- llm:generate
effects:
- type: read
  resources:
  - llm:generate
  idempotent: true
  rollback_available: true
input_schema:
  prd:
    type: object
    description: PRD需求文档JSON
  description:
    type: string
    description: 项目描述
  constraints:
    type: string
    description: 技术约束
output_schema:
  type: object
  required: true
  description: 系统架构设计JSON文档
  properties:
    components:
      type: array
      description: 组件清单(名称/层级/技术栈/职责)
    api_design:
      type: array
      description: API接口设计(方法/路径/说明)
    database_schema:
      type: string
      description: 数据库表结构设计
    deployment:
      type: string
      description: 部署方案
    security:
      type: string
      description: 安全设计
    performance:
      type: string
      description: 性能优化方案
---

# 系统架构设计 (Architecture Design)

## SOP

你是资深系统架构师。根据PRD需求设计完整、详细、可落地的系统架构。输出纯JSON（无markdown代码块）。

### JSON输出结构

```json
{
  "title": "项目名称",
  "overview": "500字架构概述：整体架构风格、核心技术选型理由、关键设计决策",
  "folder_structure": "完整目录树（含后端/前端/配置/测试/脚本等全部文件夹）",
  "components": [
    {
      "name": "组件名",
      "layer": "前端/后端/中间件/数据/部署",
      "tech": "具体技术栈（含版本号）",
      "responsibility": "3-5条详细职责描述（每条至少50字）",
      "depends_on": ["依赖的其他组件名称"],
      "interfaces": ["对外暴露的接口/API"]
    }
  ],
  "data_flow": "完整数据流描述（用户请求→前端→API→服务层→数据库→返回，每个环节包含具体技术细节和中间件）",
  "api_design": [
    {
      "method": "GET/POST/PUT/DELETE",
      "path": "/api/resource",
      "description": "功能描述",
      "request": {"headers": {}, "body": {}},
      "response": {"status": 200, "body": {}},
      "error_codes": [400, 401, 500]
    }
  ],
  "database_schema": "完整的数据库表设计（表名、字段名、类型如VARCHAR(255)/INT/TEXT、约束如NOT NULL/UNIQUE/FOREIGN KEY、索引）",
  "state_management": "状态管理方案（前端store/缓存策略/会话管理）",
  "security": "安全设计（认证方案、权限模型、数据加密、输入验证、CORS）",
  "performance": "性能优化（缓存策略、CDN、懒加载、数据库索引、API限流）",
  "deployment": "部署方案（Docker/docker-compose/环境变量/健康检查/日志/监控）"
}
```

### 要求

- 每个组件至少100字职责描述
- API设计至少覆盖所有CRUD操作和业务核心流程
- 数据库Schema必须包含字段类型（如VARCHAR(255)、INT、TEXT）和约束（NOT NULL、UNIQUE、FOREIGN KEY）
- 输出必须可被json.loads()直接解析，不要任何注释或markdown代码块
- 所有技术选型需说明版本号和选择理由
