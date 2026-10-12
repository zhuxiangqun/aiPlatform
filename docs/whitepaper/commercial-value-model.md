# 商业价值模型（权威专稿）

> 供商业价值白皮书节选。不编造客户授权 ROI%、人天单价或伙伴分成。  
> 算法符号权威：`aiPlat-core/core/harness/finance/value_calculator.py`

## 1. TCO 对照项

| TCO 项 | 说明 | 平台侧可观测/材料 |
|--------|------|-------------------|
| 平台接入成本 | 部署、租户开通、身份集成 | infra 部署手册 · 管理端 |
| 模型调用成本 | Token / 本地推理机时 | ModelManager · 配额/限流 |
| 工具与集成成本 | MCP/API/工具允许列表运维 | PolicyGate · MCP 准入 |
| 运维与治理成本 | 审计、评测、架构守卫、值班 | CAPABILITIES 治理切片 |
| 组织与培训成本 | FDE/ORG 签收、手册上手 | `docs/manuals/` |

自建 Harness+RAG+治理时，上表五项通常由客户自行承担；采用平台时对应项转入订阅/私有化运维账单。**具体单价由商务报价填写，本专稿不预设数字。**

## 2. 五维价值映射（CEO / CFO / PM）

平台 `ValueCalculator` 将运行结果聚合为五维（字段见 `MonthlyValueReport` / `ValueMetrics`）：

| 维度 | 代码字段（示意） | CEO | CFO | PM |
|------|------------------|-----|-----|-----|
| 效率 | `efficiency_saved` / `efficiency` | 战略吞吐 | 人天替代成本 | 交付周期 |
| 质量 | `quality_value` / `skill_pass_rate` | 风险下降 | 返工成本 | 通过率 |
| 安全 | `safety_value` / `attacks_blocked` | 合规可信 | 事故损失规避 | 拦截次数 |
| 创新 | `innovation_value` / `new_task_type` | 新能力覆盖 | 试错成本 | 新任务类型 |
| 体验 | `experience_value` / `user_satisfaction` | NPS/采用 | 支持成本 | 满意度 |

翻译入口：`ValueCalculator.translate_for(report, audience)`（`audience` ∈ CEO/CFO/PM）。

## 3. 示意算法（占位参数，非客户财报）

以下仅说明口径，**参数为占位**：

```text
月度总价值(示意) ≈
  efficiency_saved
  + quality_value
  + safety_value
  + innovation_value
  + experience_value
→ value_breakdown_pct 归一化后供三受众翻译
```

真实租户数字须从运行时 `compute_monthly(tenant_id, month)` 导出，并经 `cases/` 授权流程后方可写入对外案例。

## 4. 分阶段闸门

| 阶段 | 目标 | 闸门 |
|------|------|------|
| 试点 | 能力验证 | PoC 签收 · 关键路径可演示 |
| 扩展 | 成本/价值对照 | TCO 五项有基线 · 价值五维有月报 |
| 规模化 | 治理与合规复核 | PolicyGate/评测/审计绿 · ORG 签收包 |

## 5. 授权边界

- 未授权客户数字 **不得** 写入 `volumes/03-commercial-value.md` 正文作承诺。
- 内部示意见 [`cases/internal-illustrative-fde.md`](./cases/internal-illustrative-fde.md)（`authorized: false`）。
- 授权流程见 [`cases/README.md`](./cases/README.md)。
