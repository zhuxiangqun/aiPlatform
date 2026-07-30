---
name: log_analyzer
display_name: 日志分析与回归
description: >
  输入错误日志或异常报告，自动提取异常信息、归类错误类型、
  识别关联模块、评估回归风险，并输出结构化的分析报告。
  适用场景：发布前排查、线上故障分析、回归测试范围建议。
category: analysis
version: 1.0.0
status: enabled
execution_type: prompt
tags:
  - 测试
  - 日志
  - 回归
  - 故障分析
  - 质量
triggers:
  - 帮我分析日志
  - 错误分析
  - 异常归类
  - 回归范围
  - 日志分析
  - 报错日志
  - 故障排查
  - 线上问题
permissions:
  - file:read
  - kb:read
effects:
  - type: read
    resources: ["filesystem:logs"]
    idempotent: true
    rollback_available: false
input_schema:
  log_content:
    type: string
    required: true
    description: 原始日志内容（支持多行）
  log_source:
    type: string
    required: false
    description: 日志来源标识（如 nginx/main/api）
  context:
    type: string
    required: false
    description: 上下文信息（如 "昨天发布后出现" "持续30分钟"）
output_schema:
  analysis_report:
    type: object
    description: 结构化分析报告
  markdown:
    type: string
    required: true
    description: 格式化分析报告（Markdown）
trigger_conditions:
  - 用户消息包含日志/错误/异常/故障等关键词
  - 大段文本中包含 stack trace 或 error 模式
---
# 日志分析与回归

## 触发条件

当用户提交错误日志、异常堆栈、故障描述时调用。适用于：
- 发布后出现错误的根因分析
- 线上故障的快速定位
- 回归测试范围的智能推荐

## SOP

### Step 1: 异常提取
- 从日志中提取所有异常/错误条目
- 识别异常类型：StackOverflow / NullPointer / Timeout / ConnectionRefused / OutOfMemory / IllegalState / 自定义业务异常
- 按时间排序，统计异常频次
- 去重——同一类异常只保留首次和最新一次

### Step 2: 异常归类
- 按异常类型分组
- 按影响模块分组（从堆栈中提取包名/类名/文件名）
- 识别异常之间的因果链——A 异常是否触发了 B 异常
- 标注每个异常组的首次出现时间、频次、最新出现时间

### Step 3: 根因定位
- 对最高频异常组做根因推断
- 检查是否有配置变更、部署变更、流量突增等外部触发
- 标注推断置信度（高/中/低）

### Step 4: 回归范围建议
- 关联代码模块：从异常堆栈反推涉及的代码文件/模块
- 推荐回归测试范围：直接影响模块 + 间接依赖模块
- 给出测试优先级排序（先测直接影响，再测间接依赖）
- 输出可执行的回归测试建议

## 输出格式

```markdown
## 日志分析报告

**日志来源**: {log_source}
**分析时间**: {timestamp}
**总异常数**: {total_errors}
**唯一异常类型**: {unique_types}

### 一、异常统计

| # | 异常类型 | 频次 | 首次出现 | 最后出现 | 影响模块 |
|---|---------|:---:|---------|---------|---------|
| 1 | {type} | {count} | {first} | {last} | {module} |

### 二、根因分析

**最高频异常**: {top_exception}
**推断根因**: {root_cause}（置信度: {confidence}）
**关联变更**: {related_changes}

### 三、异常因果链

```
{exception_A} (首次 {time_a})
  → {exception_B} (首次 {time_b})
    → {exception_C} (首次 {time_c})
```

### 四、回归测试建议

| 优先级 | 测试范围 | 涉及模块 | 建议用例数 |
|:---:|------|------|:---:|
| P0 | 直接影响 | {direct_modules} | {count} |
| P1 | 间接依赖 | {indirect_modules} | {count} |
| P2 | 关联功能 | {related_modules} | {count} |

### 五、修复建议

{recommendations}
```

## 反模式 (Anti-patterns)

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 把所有异常都列出来，不区分优先级 | 按频次排序，最高频的优先分析 |
| 只看堆栈第一行就下结论 | 遍历完整 causal chain |
| 建议"全面回归测试" | 给出精确的回归范围（文件级/模块级） |
| 忽略时间维度 | 标注首次出现时间和频次趋势（上升/下降/稳定） |

## 异常模式库

参见 `references/pattern-library.md`
