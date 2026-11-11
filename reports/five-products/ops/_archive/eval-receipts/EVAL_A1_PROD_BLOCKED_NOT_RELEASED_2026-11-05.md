# A1 生产部署 — blocked_not_released（2026-11-05）

> **结论**：☐ pass · ☑ **blocked_not_released**（仍有效，直至正式 BASE 验收） · ☐ fail
> **原因**：无正式环境 BASE URL / CDN；本地联调已另签，**不得**复用为生产 pass
> **本地已签**：[EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md](./EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md)
> **母版**：[EVAL_A1_DEPLOY_SIGNOFF.md](./EVAL_A1_DEPLOY_SIGNOFF.md)
> **2026-11-06**：曾重开生产轨；同日产品决定**本地签认足够** → [决策](../../EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md)；生产轨 **Parked**。本单仍表示「生产未签」，不阻塞以本地为准的迭代。

## 解除条件

| # | 项 | 状态 |
|---|---|---|
| 1 | 正式 UI / API BASE（非 localhost） | ❌ **不可得** — 负责人确认**暂无公网资源**（无域名/主机/CDN） |
| 2 | 该环境构建 SHA 与 CDN/反向代理是否存在 | ❌ 随 #1 搁置 |
| 3 | 发布 / 基建 / QA 三人 | ✅ **已确认**（2026-11-05）：发布=朱向群 · 基建=朱莹 · QA=朱鸿林 |

**处置（2026-11-05）**：A1 生产轨保持 `blocked_not_released`；**不以隧道/本机冒充生产 pass**。有公网资源后再开解除。本地签认仍有效，范围仅联调。

**再确认（2026-11-06）**：负责人确认**仍无公网** → 继续长期搁置；本轮 P1b 人侧不再等待 A1 生产。

解除后副本命名：`EVAL_A1_DEPLOY_SIGNOFF_<env>_<date>.md`。

## 登记

| 项 | 值 |
|---|---|
| 登记人（工程） | agent |
| 日期 | 2026-11-05（再确认 2026-11-06） |
| 阻塞 owner | 发布负责人：**朱向群** |
| 基建 owner | **朱莹** |
| QA 留证 | **朱鸿林** |
| 资源结论 | **无公网 → 生产 A1 搁置** |
