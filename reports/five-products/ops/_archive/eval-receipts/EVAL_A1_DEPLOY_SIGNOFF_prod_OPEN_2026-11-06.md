# A1 部署签认 — 生产（OPEN · 2026-11-06）

> **状态**：⏸ **Parked** — 产品决定本地签认足够（[决策](../../EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md)）；未签生产 pass

> **母版**：[EVAL_A1_DEPLOY_SIGNOFF.md](./EVAL_A1_DEPLOY_SIGNOFF.md)
> **unfreeze**：ENGINEERING_UNFREEZE_EVAL_A1_PROD.md（历史链接失效）
> **硬切**：旧 URL 须 **404**（无 302）；`npm run build` ≠ 本签认；**禁止** localhost/隧道顶生产

---

## 0. 元数据

| 项 | 填写 |
|---|---|
| 目标环境名 / base URL | ⏳ **待填**（非 localhost） |
| 部署日期（时区） | ⏳ |
| 构建 ID / commit SHA | 预填工程侧 HEAD=`3a8c2256fed9da126e4d83bf4b2b033f5e9c83ce`（部署后以环境实际为准） |
| 前端 bundle / chunk 标识（CDN 可见） | ⏳ |
| 发布负责人 | 朱向群 |
| 基础设施 owner | 朱莹 |
| QA 留证人 | 朱鸿林 |
| 结论 | ☐ pass · ☐ **blocked_not_released** · ☐ fail |

---

## 1. 入口与菜单

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 1.1 | 主入口 `/eval` | ⏳ |  |
| 1.2 | 无第二套旧评测菜单 | ⏳ |  |
| 1.3 | `/eval` 加载 EvalCenter | ⏳ |  |

---

## 2. Tab 集合（源码 2026-11-06 · 15 项）

以部署日 `EvalCenter.tsx` `TABS` 为准；当前源码：

```
overview, sets, review, gates, reports, g2b, preference, scorecard, evidence, worksheets, agents, knowledge, prompts, code-review, settings
```

| # | Tab id | 可见 | 证据 |
|---|---|---|---|
| 2.1–2.15 | （上表） | ⏳ |  |

实际可见 tab 列表（粘贴）：

```
（待 UI）
```

---

## 3. 硬切：旧 URL 须 404

```bash
BASE='https://<formal-host>'   # 填入后执行
curl -sI "$BASE/diagnostics/eval" | head -1
curl -sI "$BASE/platform/kb/eval" | head -1
# 期望：404（不是 200/302）；响应体不是整页 EvalCenter
```

| # | URL | 期望 | 实际 | 证据 |
|---|---|---|---|---|
| 3.1 | `/diagnostics/eval` | 404 | ⏳ |  |
| 3.2 | `/platform/kb/eval` | 404 | ⏳ |  |
| 3.3 | 网关前缀变体（若有） | 404 | ⏳ |  |

---

## 4. 构建产物 / CDN

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 4.1 | 无 `DiagnosticsEvalEntry` chunk | ⏳ |  |
| 4.2 | Eval chunk 与构建 ID 一致 | ⏳ |  |
| 4.3 | CDN purge/强刷后仍成立 | ⏳ |  |
| 4.4 | `EvalCenter-*.js` 文件名 | ⏳ |  |

---

## 5. 状态文案

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| 5.1 | 无「G2b 前不计算 / 仍 defer」旧文案 | ⏳ |  |
| 5.2 | n=30 closeout / 31–100 口径诚实（或更新后的 scoped 文案） | ⏳ |  |
| 5.3 | 未展示 `accuracy_claim=true` / 已认证准确率 | ⏳ |  |

---

## 6. 签认栏

| 角色 | 姓名 | 日期 | 确认 |
|---|---|---|---|
| 发布负责人 | 朱向群 |  | ⏳ |
| 基础设施 owner | 朱莹 |  | ⏳ |
| QA 留证 | 朱鸿林 |  | ⏳ |

### 结论摘录

```
环境：
构建 ID：
A1 结论：pass | blocked_not_released | fail
旧 URL：diagnostics/eval=____  kb/eval=____
CDN purge：是/否
备注：等待正式 BASE 后继续
```

---

## 阻塞说明

在提供**正式 BASE** 之前，本轨不得勾 pass。本地联调签认仍有效，范围仅联调。
