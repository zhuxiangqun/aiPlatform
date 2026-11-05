# Context management baseline v0（P2-1）

> **Unfreeze**: [`ENGINEERING_UNFREEZE_EVAL_P2_CONTEXT.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_P2_CONTEXT.md)  
> **Honesty**: `accuracy_claim=false` · ≠ Session v0/v1 短轮次 · ≠ 持久记忆 · ≠ 生产对话质量

## 1. 目的

补齐评测侧对**上下文管理**的工程基准（产品评审缺口）：

| kind | 测什么 |
|---|---|
| `long_context_recall` | 噪声上下文中能否找回针（needle） |
| `summary_fidelity` | 摘要是否保留关键事实、不掺幻觉 |
| `conflict` | 前后矛盾时是否以权威/更新事实为准 |
| `truncation_degradation` | 上下文被截断时是否降级/拒答，而非臆造 |

## 2. 与 Session 的边界

| | Session v0/v1 | Context v0 |
|---|---|---|
| 轮次 | 2–8 短轮 | 单次 query + 受控长上下文 |
| 对象 | turn_success / session_pass | 四类上下文行为 |
| 声明 | 非长程 Agent | 非 accuracy；非记忆子系统 |

## 3. Runner / Pack

| 项 | 值 |
|---|---|
| Runner | `context_mgmt` |
| Pack | [`context_tasks.v0.json`](./context_tasks.v0.json) |
| Schema | `eval.scoring.context_mgmt.v0` |
| Gate | `bash packages/aiplat-evaluation/scripts/context_v0_gate.sh` |

评分：`must_contain` / `must_not_contain` 子串检查（fixture 确定性）；可选 live LLM 填 `actual` 但不作为本门禁默认。

## 4. 验收

- 四类各 ≥1 条；整包 `context_pass=true` 且 `accuracy_claim=false`
- 单元测试覆盖 pass/fail 路径
- **禁止**把本门禁结果写成「长上下文准确率」

## 5. 非目标

≠ 百万 token 压力 · ≠ 工具循环 · ≠ Recall@k 记忆 · ≠ 自学习写回 · ≠ process_split
