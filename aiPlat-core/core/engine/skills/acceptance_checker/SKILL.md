---
name: acceptance_checker
display_name: 验收检查器
description: 根据部署包和客户画像，生成验收报告，包含验收清单、KPI结果、SLA检查、培训检查和签收。
version: 2.0.0
category: fde
status: enabled
execution_type: prompt
effects:
  - type: read
    resources: ["filesystem:/tmp"]
    idempotent: true
    rollback_available: false
input_schema:
  type: object
  properties:
    deployment_package:
      type: object
      description: 部署包
    customer_profile:
      type: object
      description: 客户画像（含合规要求）
  required:
    - deployment_package
output_schema:
  type: object
  properties:
    markdown:
      type: string
    acceptance_report:
      type: object
  required:
    - markdown
---

### SOP 执行指引
1. KPI检查：验证功能完整性、golden_query通过率(≥85%)、响应时间。
2. 数据一致性：验证实体/关系数量、Wiki页面数、GraphIndex节点数。
3. SLA检查：验证金丝雀发布状态、回滚方案完整性、监控配置。
4. 培训检查：验证沙箱环境、交付手册、Agent创建指南、工作流指南。
5. 输出签收信息：客户签字、管理员交接、30天护航承诺。

### 输出格式
```json
{
  "acceptance_report": {
    "acceptance_checklist": [{"item": "...", "status": "pass|fail|pending", "notes": "..."}],
    "kpi_results": {"feature_completeness": 0.95, "golden_query_pass_rate": 0.88, "avg_response_time_ms": 450},
    "sla_check": {"canary_result": "pass", "rollback_verified": true, "monitoring_configured": true},
    "training_check": {"sandbox_ready": true, "delivery_manual_complete": true, "agent_guide_complete": true},
    "signoff": {"accepted": true, "signoff_by": "", "escort_days": 30, "remarks": ""}
  }
}
```

### 反模式
- 不要跳过数据一致性检查
- 不要省略SLA验证
- 不要生成空签收信息
