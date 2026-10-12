---
authorized: false
kind: illustrative
customer: 内部示意
industry: （不适用）
engagement: Illustrative
source: 基于 value_calculator.py 五维口径构造
period: 示意月度
---

> **非客户授权案例**  
> 本案例为内部示意，不涉及任何真实客户名称、授权数据或收益承诺。仅用于说明 `value_calculator.py` 五维算法与 CEO/CFO/PM 翻译口径。

## 业务问题（示意）

某交付团队希望缩短诊断→签收周期，并降低知识检索幻觉风险。本段为角色扮演场景，**非真实客户访谈记录**。

## 采用前成本/风险（占位，非审计数字）

| 项 | 占位说明 |
|----|----------|
| 人天 | `baseline_person_days`（由商务/客户填写，此处不填数） |
| 返工 | 无结构化通过率基线 |
| 合规 | 审计证据分散 |

## 采用后指标口径（映射平台字段）

假设试点月跑通 FDE + 知识检索后，价值系统可导出：

| 五维 | 示意字段 | 说明 |
|------|----------|------|
| 效率 | `efficiency_saved` | 相对基线节省的等价量（占位） |
| 质量 | `quality_value` / `skill_pass_rate` | 技能通过率驱动 |
| 安全 | `safety_value` | 拦截/策略拒绝（若有） |
| 创新 | `innovation_value` | 新任务类型覆盖 |
| 体验 | `experience_value` | 满意度代理指标 |

三受众翻译：`translate_for(report, "CEO"|"CFO"|"PM")`。

## 平台能力映射

勿抄能力表。查阅 `AIPLAT_CAPABILITIES.md` 中 FDE / 知识检索 / Gate 相关行的 ✅/⚠️。

## 限制与未包含项

- 本文件 `authorized: false`，禁止当作对外客户 ROI 引用。
- 未包含真实合同金额、分成、人天单价。
- 真实案例须走 [`README.md`](./README.md) 授权流程并设 `authorized: true`。
