# Agent 评估计划

> 生成时间: {timestamp}
> 目标 Agent: {agent_id}

## 1. Agent 规格

| 属性 | 值 |
|------|-----|
| agent_type | {agent_type} |
| 工具 | {tools} |
| 技能 | {skills} |
| 输入 artifact | {input_artifacts} |
| 输出 artifact | {output_artifact} |

## 2. 执行轨迹摘要

| 指标 | 值 |
|------|-----|
| 分析轨迹数 | {trace_count} |
| 平均工具调用次数/次 | {avg_tool_calls} |
| 最常见工具 | {top_tools} |
| HITL 触发频率 | {hitl_rate} |
| 典型执行耗时 | {avg_duration} |

## 3. 评估指标定义

每个指标包含：
- **名称**：简短唯一标识
- **权重**：0-1，总和为 1
- **评分标准**：0-10 分刻度，每个分数档有明确描述
- **计算公式**：如何从轨迹数据自动计算

### 指标 1: {name}
- 权重: {weight}
- 阈值: {threshold}
- 描述: {description}
- 评分标准:
  - 9-10: {excellent}
  - 7-8: {good}
  - 5-6: {acceptable}
  - 3-4: {poor}
  - 0-2: {failed}
- 计算公式: `if len(tool_calls) == expected: score += 2; if output_valid: score += 2; ...`

### 指标 2-5: (同上格式)

## 4. 测试场景

| 场景 | 输入 | 预期 | 评分重点 |
|------|------|------|---------|
| 正常流程 | {normal_input} | {expected} | 全部指标 |
| 边界情况 | {edge_input} | {expected} | 错误恢复 |
| 对抗场景 | {adversarial} | {expected} | 权限边界 |

## 5. 文件清单

- `eval_metric.py` — 指标实现（{estimated_lines} 行）
- `eval_runner.py` — 执行入口（{estimated_lines} 行）
- 禁止超过 2 个文件
