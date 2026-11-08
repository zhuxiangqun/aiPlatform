# Ollaya 决策层 · 阶段 0 证据草稿（非 Go）

> **状态**：局部离线证据 · **≠ 阶段 0 完成 · ≠ Go 阶段 1 · ≠ 已立项**  
> **依据**：[ollaya-decision-layer-implementation-plan.md](./ollaya-decision-layer-implementation-plan.md) §4  
> **日期**：2026-11-08

## 已完成（可离线）

### 0.5 意图路由 `classify_with_llm` 调用链

| 项 | 结论 |
|----|------|
| 定义位置 | `aiPlat-core/core/harness/routing/classifier.py`（`async def classify_with_llm`） |
| 生产调用方 | **未发现**：全仓 `classify_with_llm(` 仅命中定义行 |
| 宣讲约束 | **禁止**「引入 Ollaya / 决策层即可省线上意图 LLM fallback」——当前无该生产路径可省 |

验证：

```bash
rg -n 'classify_with_llm\(' --glob '*.py'
# 预期：仅 classifier.py 定义
```

## 未完成（需现网/立项）

| ID | 工作项 | 阻塞 |
|----|--------|------|
| 0.1 | 观测窗口与环境说明 | 需运维约定窗口 |
| 0.2–0.4 | DomainRouter 现网埋点与 T1/T2/T3 计数、T3 延迟 | 需现网日志/指标 |
| 0.6 | 阶段 1 工程约束评审通过 | 需评审会 |
| 0.7 | Go/No-Go | 需书面基线报告齐全 |

## 明确不交付（本文件）

影子延迟、Ollaya 准确率、线上替换、`decision_shadow` 代码接线。

## 下一步

按实施方案召开阶段 0 基线会；在未 Go 前 **禁止** 合并影子主路径接线。
