---
name: evaluator-webapp-qa
description: 对 Web 应用进行自动/半自动验收（Playwright/Browser 驱动），输出结构化评分与问题清单，用于 generator 迭代闭环
version: 0.1.0
executable: false
category: qa
capabilities:
  - evaluation
  - ui-testing
  - acceptance
---

# Evaluator：WebApp QA 评估与验收（SOP）

## 目标
对 generator 交付的 Web 应用进行“像真实用户一样”的验证，并输出：
- 评分（按维度）
- 是否通过（pass/fail）
- 可复现的问题清单（含证据）
- 下一轮 generator 的可操作修复建议

强调：**避免自我评估偏差**。evaluator 必须“挑剔”，宁可严格，不要放水。

## 输入（你需要向我提供）
1) 应用访问方式：URL（本地或远程）  
2) 目标 spec 或至少提供：关键用户路径（Top flows）与验收点（acceptance）  
3) 如有账号/权限：测试账号（或说明无登录）  

## 验收维度与权重（可调，默认）
> 参考文章的思路：显式惩罚“看起来像但不可用”的情况。

1) **Functionality（功能完整性）** 40%  
   - 核心路径是否可完成？是否存在“按钮有反应但功能是 stub”的情况？
2) **Product Depth（产品深度）** 20%  
   - 是否只停留在展示层？是否有真实数据流/状态管理/错误处理？
3) **Design & UX（体验与一致性）** 20%  
   - 交互是否清晰？信息层级/布局是否合理？是否明显模板化？
4) **Code/Architecture Signals（代码/架构信号）** 20%（若可见）  
   - API 设计是否一致？模块边界是否清楚？是否存在明显不安全/不可靠做法？

### 硬阈值（必须）
- Functionality < 7/10 → **直接 fail**
- 存在“关键路径不可用”或“数据不一致/丢失” → **直接 fail**

## 操作步骤（推荐）

### Step 1：建立测试计划（基于 spec）
输出一个简短的测试清单（checklist），至少包括：
- P0：必须通过的关键路径（3~8 条）
- P1：常见边界/错误处理（2~6 条）
- P2：一致性/易用性（2~6 条）

### Step 2：执行自动化验证（Browser/Playwright）
如果系统提供 Browser/Playwright 工具：
- 打开 URL
- 按 P0 流程点击/输入
- 记录截图、关键页面状态、关键交互结果
- 必要时检查 Network 请求是否成功（状态码/错误）

> 若无法自动化（例如缺工具或环境限制），改为“人工可执行的复现步骤”清单，但仍需给出 pass/fail 结论。

### Step 3：输出结构化评估报告（必须按 JSON）
```json
{
  "pass": false,
  "score": {
    "functionality": 0,
    "product_depth": 0,
    "design_ux": 0,
    "code_architecture": 0,
    "overall": 0
  },
  "thresholds": {
    "functionality_min": 7
  },
  "issues": [
    {
      "severity": "P0",
      "title": "关键路径失败：无法保存",
      "repro_steps": ["...", "..."],
      "expected": "...",
      "actual": "...",
      "evidence": {
        "screenshot": "path-or-url-if-available",
        "network": ["POST /api/save -> 500 ..."]
      },
      "suggested_fix": "..."
    }
  ],
  "positive_notes": ["..."],
  "next_actions_for_generator": [
    "先修复所有 P0，再跑一轮评估",
    "补齐缺失的交互深度（拖拽/编辑/验证）"
  ]
}
```

## 输出风格要求（强制）
- 结论要明确：**pass 或 fail**
- 每个问题必须可复现：必须有 repro_steps
- 不要只说“可以更好看/更完善”，必须给出“怎么改、改到什么算通过”
- 对“看起来有但实际上没有”的 stub 功能要严厉扣分并标为 P0/P1

## 与 aiPlat 的最佳实践集成建议
- 将本报告作为 artifact 保存（例如 `evaluator_report.json`）
- generator 下一轮必须逐条关闭 issues，并在提交中引用 issue id
- 若启用审批/治理：当 evaluator 涉及外网访问/写文件/执行脚本时，走 ask/approval

