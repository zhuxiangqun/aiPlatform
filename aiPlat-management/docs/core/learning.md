# Learning / Runs / Artifacts（As-Is）

> 本文档用于同步 management 前端的“Runs 评估工作流 + Learning Artifacts 浏览能力”的**当前实现**，避免 To‑Be 文档与真实系统脱节。

---

## 1. Runs → 评估（As-Is）

入口页面：`Diagnostics / Runs`

支持能力：

1) **自动评估（auto-eval）**
- 可选输入：`url`（启用 integrated_browser 后采集 snapshot/screenshot/console/network）
- 可选输入：`project_id`（选择项目级 evaluation_policy）
- 可选输入：`expected_tags / steps(tag) / tag_expectations / tag_template`

2) **策略编辑**
- 全局策略（system/default）：查看/编辑/保存
- 项目策略（project/<project_id>）：加载/保存（merge）+ 合并后策略预览
- 若启用变更控制（autosmoke enforce），保存项目策略可能返回 change-control 链接并要求审批

3) **评估结果阅读**
- PASS/FAIL、functionality 分数、Regression 标记
- Issues 列表（P0/P1 Badge + suggested_fix）
- 原始 JSON 折叠，避免刷屏

4) **快捷跳转**
- 从评估结果区可一键跳转到：
  - 当前 run 对应的 Learning Artifacts 列表（带 `run_id` 参数）
  - 仅评估报告 / 仅证据包（带 `kind` 参数）

---

## 1.1 Diagnostics → Workflows（一键流水线入口，As-Is）

入口页面：`Diagnostics / Workflows`

当前提供两条最小可用流水线：
- **QA-only**：触发 `evaluate/auto` 生成 `evaluation_report`（可选 url 取证），完成后自动跳转到 artifact
- **QA + Gate**：同上，但开启硬门控（Coverage Gate / Tag Assertions / Regression Gate 等）
- **Investigate**：聚合 run/evaluation/evidence/diff/syscalls 生成 `investigate_report`，用于一键排障

输入建议：
- 若要启用 Coverage Gate（缺关键 tag 直接 P0），建议在 `steps[]` 中为关键步骤标注 `tag`。

---

## 2. Learning Artifacts 列表（As-Is）

入口页面：`Core / Learning / Artifacts`

支持能力：

- target_type：支持 `system / project / agent / skill / run / prompt / policy`
- 过滤条件：
  - `target_id`（可选）
  - `run_id`（可选）
  - `trace_id`（可选）
  - `kind/status`
- 列表增强：
  - kind/status 以 Badge 展示
  - summary 列按 kind 提取关键信息（evaluation/evidence/policy/run_state）
  - run/trace 快捷跳转到 Runs/Links
- URL 同步：
  - 支持从 URL querystring 初始化过滤条件
  - 支持“固定到 URL”用于分享/复现查询

---

## 3. Artifact 详情（As-Is）

入口页面：`Core / Learning / Artifacts / <artifact_id>`

增强阅读视图：
- evaluation_report：摘要 + Issues 专用 Tab（折叠 expected/actual/evidence）
- evidence_pack：url/error 摘要
- evidence_diff：summary + metrics 摘要
- run_state：locked/todo/next_step 摘要
- evaluation_policy：默认模板/阈值/模板列表摘要
