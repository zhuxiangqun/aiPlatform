# A1 部署签认检查表（可勾选）

> **门**：P0 A1 发布完整性 — **阻塞正式发 UI**  
> **依据**：[改善执行计划](./EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §3 · [产品评审](./EVALUATION_PRODUCT_REVIEW_2026-11-04.md)  
> **硬切**：旧 URL **须 404**（无 302）；本机 `npm run build` **≠** 本签认  
> **不阻塞本门**：对象卡、G2B 三方签、Arena/G2b 双标  

---

## 0. 元数据（必填）

| 项 | 填写 |
|---|---|
| 目标环境名 / base URL |  |
| 部署日期（时区） |  |
| 构建 ID / commit SHA |  |
| 前端 bundle / chunk 标识（CDN 可见） |  |
| 发布负责人 |  |
| 基础设施 owner |  |
| QA 留证人 |  |
| 结论 | ☐ **pass** · ☐ **blocked_not_released** · ☐ **fail** |

**blocked_not_released**：环境不可达 / 无法刷 CDN → 不得宣称「已发布」。  
**fail**：可达但验收项未过 → 修后重签，不降级为本机通过。

---

## 1. 入口与菜单

| # | 检查 | 方法 | 结果 | 证据（截图/日志路径） |
|---|---|---|---|---|
| 1.1 | 管理端主入口为 **`/eval`**（评测中心） | 登录 → 侧栏/路由 | ☐ |  |
| 1.2 | 无第二套「诊断评测 / KB 评测」独立菜单进旧页 | 扫侧栏 | ☐ |  |
| 1.3 | 直接打开 `/eval` 可加载 EvalCenter | 浏览器 | ☐ |  |

---

## 2. Tab 集合（与源码 manifest 一致）

以部署当日 `EvalCenter.tsx` `TABS` 为准；下列为 2026-11-05 源码 **15** 项，若源码已变，以源码为准并改本表。

| # | Tab id | Tab label | 可见 | 证据 |
|---|---|---|---|---|
| 2.1 | overview | 总览 | ☐ |  |
| 2.2 | sets | 评测集 | ☐ |  |
| 2.3 | review | 复核 | ☐ |  |
| 2.4 | gates | 门禁 | ☐ |  |
| 2.5 | reports | 报告 | ☐ |  |
| 2.6 | g2b | G2b | ☐ |  |
| 2.7 | preference | Preference | ☐ |  |
| 2.8 | scorecard | Scorecard | ☐ |  |
| 2.9 | evidence | Evidence | ☐ |  |
| 2.10 | worksheets | Worksheets | ☐ |  |
| 2.11 | agents | Agents | ☐ |  |
| 2.12 | knowledge | Knowledge | ☐ |  |
| 2.13 | prompts | Prompts | ☐ |  |
| 2.14 | code-review | Code-review | ☐ |  |
| 2.15 | settings | 设置 | ☐ |  |

实际可见 tab 列表（粘贴）：

```
（从 UI 抄写）
```

---

## 3. 硬切：旧 URL 须 404

| # | URL（相对站点根或网关前缀按环境改） | 期望 | 实际状态码 | 证据 |
|---|---|---|---|---|
| 3.1 | `/diagnostics/eval` | **404** |  |  |
| 3.2 | `/platform/kb/eval` | **404** |  |  |
| 3.3 | （若有网关前缀，如 `/mgmt/diagnostics/eval`） | **404** |  |  |

命令示例（按环境改 `BASE`）：

```bash
BASE='https://<your-host>'
curl -sI "$BASE/diagnostics/eval" | head -1
curl -sI "$BASE/platform/kb/eval" | head -1
# 期望：HTTP/1.1 404 或 HTTP/2 404（不是 200/302）
```

☐ 确认响应体**不是**整页 EvalCenter（防 SPA fallback 假 200）。

---

## 4. 构建产物 / CDN

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 4.1 | 产物/Network 中 **无** `DiagnosticsEvalEntry` chunk | ☐ |  |
| 4.2 | Eval 相关 chunk 名与本次构建 ID 一致 | ☐ |  |
| 4.3 | 强刷或 purge CDN 后 4.1–4.2 仍成立 | ☐ |  |
| 4.4 | 记录命中的 JS：`EvalCenter-*.js` 或等价 | ☐ | 文件名： |

---

## 5. 状态文案（Settings / G2b 相关）

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 5.1 | **无**「G2b 前不计算 / 仍 defer」类旧文案 | ☐ |  |
| 5.2 | 表述为 **n=30 closeout 已完成**；**31–100 待双标** | ☐ |  |
| 5.3 | **未**把 accuracy 展示为已认证 / `accuracy_claim=true` | ☐ |  |

---

## 6. 签认栏

| 角色 | 姓名 | 日期 | 签字/确认（pass / blocked / fail） |
|---|---|---|---|
| 发布负责人 |  |  |  |
| 基础设施 owner |  |  |  |
| QA 留证 |  |  |  |

### 结论摘录（可复制到 closeout）

```
环境：
构建 ID：
A1 结论：pass | blocked_not_released | fail
旧 URL：diagnostics/eval=____  kb/eval=____
CDN purge：是/否
备注：
```

---

## 7. 与本机验证的边界

| 已做（开发机，**不够 A1**） | 本表要求 |
|---|---|
| `npm run build` 无旧 chunk | 目标部署 + CDN 后再验 |
| 本地路由无旧页 | 公网/内网 **实际 URL** 404 |
| 本地 tab 齐全 | 部署后 UI 再点一遍 |

完成后：把本表填好的副本落到 `reports/five-products/ops/`（如 `EVAL_A1_DEPLOY_SIGNOFF_<env>_<date>.md`）或工单附件，并更新执行计划状态栏。
