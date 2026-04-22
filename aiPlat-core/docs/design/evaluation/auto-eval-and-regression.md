# 自动评估与回归门控（As-Is）

> 本文档用于把近期落地的“自动评估（auto-eval）/证据包（evidence）/回归对比（diff）/策略（policy）/项目级继承（project policy）/治理（change-control）”整理成可追溯的工程口径，避免实现与文档脱节。

---

## 1. 一句话定义

- **auto-eval**：对某次 `run` 生成结构化 `evaluation_report`（支持可选浏览器取证）。
- **evidence_pack**：浏览器取证采集的证据快照（snapshot/screenshot/console/network + 分阶段 by_tag）。
- **evidence_diff**：对两份 evidence_pack 做回归对比，输出可门控指标与摘要。
- **evaluation_policy**：评估与回归门控的策略（阈值、权重、required_tags、tag_templates 等），支持 system/default 与 project/<id> 继承覆盖。
- **tag_assertions**：对关键路径标签（tag）做断言（文本/错误数/耗时等），失败直接 P0 阻断。

---

## 2. 数据对象与 Artifact 种类（As-Is）

所有对象均以 `learning_artifacts` 形式落库，并可在 management 的 Learning Artifacts 页面检索与查看。

| kind | target_type | target_id | 说明 |
|---|---|---|---|
| `evaluation_report` | `run` | `<run_id>` | 评估报告（pass/score/issues/regression/assertions…） |
| `evidence_pack` | `run` | `<run_id>` | 浏览器取证证据包（一次评估一次保存） |
| `evidence_diff` | `run` | `<run_id>` | 证据对比结果（默认与上一份 evidence_pack 对比） |
| `evaluation_policy` | `system` | `default` | 全局默认策略 |
| `evaluation_policy` | `project` | `<project_id>` | 项目级策略（深度合并覆盖全局策略） |
| `run_state` | `run` | `<run_id>` | 长任务 restatement（用于 prompt 注入与 todo 控制） |

---

## 3. auto-eval 执行流程（As-Is）

1) `POST /runs/{run_id}/evaluate/auto`
2) 可选：若提供 `url`，则使用 integrated_browser 采集证据（best-effort，失败不应导致整个评估崩溃）
3) evidence_pack 落库，并回填 `evidence_pack_id`
4) 自动选择“上一份 evidence_pack”（同 run）生成 evidence_diff，并回填 `evidence_diff_id`
5) 应用门控：
   - **tag_assertions**：基于 `tag_expectations` 与 `evidence_pack.by_tag` 的硬门控（失败插入 P0 issue）
   - **regression_gate**：基于 evidence_diff.metrics 的硬门控（失败插入 P0 issue）
   - **threshold_gate**：基于 evaluator score 的阈值门控（保留原有）
6) 生成并落库 `evaluation_report`，并在 run_state 中合并/生成 todo（若启用）

---

## 4. 关键能力细节（As-Is）

### 4.1 by_tag 证据采集（Coverage）

当 `steps[].tag` 发生切换时，会采集该 tag 的阶段证据：

- `snapshot`
- `screenshot`
- `console_messages`
- `network_requests`
- `duration_ms`

输出位置：`evidence_pack.by_tag[tag]`，以及 `evidence_pack.coverage.executed_tags / expected_tags`。

### 4.2 tag_assertions（关键路径断言）

请求体支持 `tag_expectations`（按 tag 配置）：

- `text_contains: string[]`
- `max_console_errors: number`
- `max_network_5xx: number`
- `max_network_4xx: number`
- `max_duration_ms: number`

失败时：
- `report.pass=false`
- `report.assertions.tag_failures` 写入失败明细
- `report.issues` 前置 P0

### 4.3 evidence_diff（回归对比）

对比维度：
- console 新增条目（并统计新增 error/warn 数）
- network 新增请求（并统计新增 4xx/5xx）
- 页面标题变化（若可提取）
- by_tag 截图 hash 变化（输出 changed_screenshot_tags 指标）

### 4.4 evaluation_policy（策略、模板、继承）

policy 主要字段：
- `thresholds`：阈值门控（如 functionality_min）
- `weights`：评估权重（用于口径一致性/提示注入）
- `regression_gate`：回归门控（max_new_console_errors / max_new_network_5xx / max_new_network_4xx / required_tags / max_changed_screenshot_tags…）
- `tag_templates` + `default_tag_template`：可复用的关键路径模板（expected_tags + tag_expectations）

继承顺序（As-Is）：
1. system/default
2. project/<project_id>（深度合并覆盖）
3. request.policy（请求级 override，深度合并覆盖）

---

## 5. API 清单（As-Is）

### 5.1 评估与证据

- `POST /runs/{run_id}/evaluate/auto`
  - body 增量字段：`project_id`、`url`、`steps[]`（支持 `tag`）、`expected_tags`、`tag_expectations`、`tag_template`
- `GET /runs/{run_id}/evaluation/latest`
- `GET /runs/{run_id}/evidence_pack/latest`
- `POST /runs/{run_id}/evidence/diff`

### 5.2 策略

- `GET /evaluation/policy/latest`
- `POST /evaluation/policy`
- `GET /projects/{project_id}/evaluation/policy/latest`（返回 project item + merged 预览）
- `POST /projects/{project_id}/evaluation/policy`（支持 mode=merge|replace；可接入 change-control gate）

<!-- OPENAPI_EVAL_BEGIN -->

### 5.X OpenAPI 生成的接口面（防脱节｜As-Is）

> 本段落由 `docs/design/evaluation/openapi-eval.snapshot.json` 自动生成，请勿手工编辑。

| Endpoint | 请求字段（JSON body） | 必填 |
|---|---|---|
| `GET /api/core/evaluation/policy/latest` | - | - |
| `GET /api/core/projects/{project_id}/evaluation/policy/latest` | - | - |
| `GET /api/core/runs/{run_id}/evaluation/latest` | - | - |
| `GET /api/core/runs/{run_id}/evidence_pack/latest` | - | - |
| `POST /api/core/evaluation/policy` | `policy` | - |
| `POST /api/core/projects/{project_id}/evaluation/policy` | `mode`, `policy` | - |
| `POST /api/core/runs/{run_id}/evaluate/auto` | `enforce_gate`, `evaluator`, `expected_tags`, `extra`, `policy`, `project_id`, `steps`, `tag_expectations`, `tag_template`, `thresholds`, `url` | - |
| `POST /api/core/runs/{run_id}/evidence/diff` | `base_evidence_pack_id`, `new_evidence_pack_id` | `base_evidence_pack_id`, `new_evidence_pack_id` |

更新方式：

1) 更新快照：`python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json`
2) 同步文档：`python -m core.tools.sync_eval_docs`

<!-- OPENAPI_EVAL_END -->

### 5.Y OpenAPI 快照护栏（防脱节）

仓库内维护一份“最小 OpenAPI 快照”，由 CI 强制校验，以避免接口字段变更后文档未更新：

- 快照文件：`docs/design/evaluation/openapi-eval.snapshot.json`
- 更新命令：
  - `python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json`
  - `python -m core.tools.sync_eval_docs`

---

## 6. Evidence Index（证据索引）

### 代码入口

- auto-eval / policy / project policy API：
  - `core/server.py: auto_run_evaluation()`
  - `core/server.py: get_latest_evaluation_policy()/upsert_evaluation_policy()`
  - `core/server.py: get_latest_project_evaluation_policy()/upsert_project_evaluation_policy()`
- evidence_diff：
  - `core/harness/evaluation/evidence_diff.py: compute_evidence_diff()/evaluate_regression()`
- tag_assertions：
  - `core/harness/evaluation/tag_assertions.py: evaluate_tag_assertions()`
- policy schema + merge：
  - `core/harness/evaluation/policy.py: EvaluationPolicy/merge_policy`
- learning artifacts kinds：
  - `core/learning/types.py: LearningArtifactKind`

### 测试用例

- `core/tests/unit/test_harness/test_evidence_diff.py`
- `core/tests/unit/test_harness/test_regression_gate_required_tags.py`
- `core/tests/unit/test_harness/test_tag_assertions.py`
- `core/tests/unit/test_harness/test_evaluation_policy_parse.py`
- `core/tests/unit/test_harness/test_evaluation_policy_merge.py`
