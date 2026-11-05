# A1 部署签认 — 本地联调（已签认 · 2026-11-05）

> **状态**：✅ **A1 pass（仅本地联调）** — §6 三人已签 · §0 已勾 pass  
> **母版**：[EVAL_A1_DEPLOY_SIGNOFF.md](./EVAL_A1_DEPLOY_SIGNOFF.md)  
> **起草稿**：[EVAL_A1_DEPLOY_SIGNOFF_PARTIAL_2026-11-05.md](./EVAL_A1_DEPLOY_SIGNOFF_PARTIAL_2026-11-05.md)  
> **范围**：**仅本地联调**（非生产 / 无 CDN）。正式环境须换 BASE 另签一版。  
> **图例**：`[已核]` 命令或截图已过 · `[已签]` 签字人已确认

---

## 0. 元数据


| 项                    | 填写                                                                                                    |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| 目标环境名 / base URL     | `[已核]` **本地联调** · UI=`http://localhost:5173` · API/网关=`http://localhost:8000`                         |
| 部署日期（时区）             | `[已核]` 2026-11-05（UTC+8）                                                                              |
| 构建 ID / commit SHA   | `[已核]` `068be63e40c40193f1a4d0c379833627ff81826b`（与 `git rev-parse HEAD` 一致）                          |
| 前端 bundle / chunk 标识 | `[已核]` 本地无 CDN；`proxy_server.py` 托管 `frontend/dist`；产物含 `EvalCenter-*.js`（如 `EvalCenter-B8S0hMnb.js`） |
| 发布负责人                | `[已签]` 朱向群                                                                                            |
| 基础设施 owner           | `[已签]` 朱莹                                                                                             |
| QA 留证人               | `[已签]` 朱鸿林                                                                                            |
| 结论                   | ☑ **pass（本地联调）** · ☐ blocked_not_released · ☐ fail                                                   |


**服务存活（同日）：**

```
curl -sI http://127.0.0.1:5173/ | head -1   → HTTP/1.0 200 OK
curl -sI http://127.0.0.1:8000/docs | head -1 → HTTP/1.1 200 OK
git rev-parse HEAD → 068be63e40c40193f1a4d0c379833627ff81826b
```

---

## 1. 入口与菜单


| #   | 检查                     | 结果       | 证据                                                      |
| --- | ---------------------- | -------- | ------------------------------------------------------- |
| 1.1 | 主入口为 `/eval`           | `[已核]` ✅ | 浏览器 `localhost:5173/eval?tab=overview`；侧栏「📈 评测」→「评测中心」 |
| 1.2 | 无第二套旧评测菜单              | `[已核]` ✅ | 侧栏仅一级「评测」；无独立旧诊断评测菜单                                    |
| 1.3 | `/eval` 可加载 EvalCenter | `[已核]` ✅ | 页标题「评测中心」· EVAL_V1 E6 · tenant=eval-v1                  |


---

## 2. Tab 集合

截图可见 tab（与源码 15 项一致）：

```
overview, sets, review, gates, reports, g2b, preference, scorecard, evidence, worksheets, agents, knowledge, prompts, code-review, settings
```


| #        | Tab id | Tab label | `[已核]` |
| -------- | ------ | --------- | ------ |
| 2.1–2.15 | （同上列表） | （截图顶栏齐全）  | ✅      |


---

## 3. 硬切：旧 URL 须 404

**API 网关 `8000`（操作者 curl）：**

```
curl -sI http://127.0.0.1:8000/diagnostics/eval | head -1  → HTTP/1.1 404 Not Found
curl -sI http://127.0.0.1:8000/platform/kb/eval | head -1   → HTTP/1.1 404 Not Found
```

**前端 SPA `5173`（浏览器）：**


| URL                                      | 结果                                                              |
| ---------------------------------------- | --------------------------------------------------------------- |
| `http://localhost:5173/diagnostics/eval` | Unexpected Application Error! **404 Not Found**（非整页 EvalCenter） |
| `http://localhost:5173/platform/kb/eval` | 同上 **404 Not Found**                                            |



| #   | 检查                  | 结果                      |
| --- | ------------------- | ----------------------- |
| 3.1 | `/diagnostics/eval` | `[已核]` 404（8000 + 5173） |
| 3.2 | `/platform/kb/eval` | `[已核]` 404（8000 + 5173） |
| 3.3 | 网关前缀版               | N/A（本地无额外前缀）            |


☑ 响应体不是整页 EvalCenter  
☐ 正式环境非 localhost 时须对正式 BASE 重跑（本版不覆盖）

---

## 4. 构建产物 / CDN


| #   | 检查                            | 结果                                                               |
| --- | ----------------------------- | ---------------------------------------------------------------- |
| 4.1 | 无 `DiagnosticsEvalEntry` 独立入口 | `[已核]` 旧路由 404；评测仅 `/eval`                                       |
| 4.2 | 构建与 SHA 一致                    | `[已核]` HEAD=`068be63e…`；dist 含 `EvalCenter-*.js`                 |
| 4.3 | CDN purge                     | `[已核]` **不适用**（本地无 CDN）                                          |
| 4.4 | 命中 JS                         | `[已核]` 模式 `EvalCenter-*.js`（本次 build 例：`EvalCenter-B8S0hMnb.js`） |


---

## 5. 状态文案


| #   | 检查                | 结果                                                                              |
| --- | ----------------- | ------------------------------------------------------------------------------- |
| 5.1 | 无「仍 defer」旧文案     | `[已核]` 总览诚实约束区无该文案                                                              |
| 5.2 | n=30 / 31–100 口径  | `[已核]` Settings 源码 + UI：`accuracy_claim=false`；G2a 总览展示 engineering calibration |
| 5.3 | 未把 accuracy 标为已认证 | `[已核]` 横幅：`accuracy_claim` 必须为 false（当前：**false**）                              |


---

## 6. 签认栏（已签）


| 角色         | 姓名  | 日期         | 签字/确认              |
| ---------- | --- | ---------- | ------------------ |
| 发布负责人      | 朱向群 | 2026/11/05 | ☑ **pass（本地联调）**   |
| 基础设施 owner | 朱莹  | 2026/11/05 | ☑ **pass（本地联调）**   |
| QA 留证      | 朱鸿林 | 2026/11/05 | ☑ **pass（本地联调）**   |


### 结论摘录

```
环境：本地联调 UI=http://localhost:5173 API=http://localhost:8000
构建 ID：068be63e40c40193f1a4d0c379833627ff81826b
A1 结论：pass（仅本地联调；非生产 / 无 CDN）— §6 三人已签 · §0 已勾 pass
旧 URL：diagnostics/eval=404  kb/eval=404（8000 curl + 5173 SPA 404 @ 2026-11-05）
CDN purge：不适用
备注：侧栏「📈 评测」与 AI 应用工厂平级；/eval?tab=overview 正常；accuracy_claim=false；
     ROLE_MENUS 已含 eval + dist 已 rebuild
签认留存：EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md
```

---

**说明**：本文件为本地环境 A1 签认留存。生产发布勿复用本结论；正式环境须换 BASE 按母版另签。
