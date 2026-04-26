# 自动评估/证据/回归/策略：P0/P1 验收清单（最省钱补齐顺序）

> 目的：把当前已落地的 auto-eval（evaluation_report + evidence_pack/diff + gates + policy）从“能跑的雏形”补齐到“团队可依赖、可治理、可持续迭代”的产品级闭环。  
> 原则：**先可信（P0）→再可治理（P1）→最后体验/自动化（P2）**。  
> 说明：本清单以 As‑Is 代码事实为基础，尽量复用你们现有设施（Artifacts / Change Control / Approvals / Run events）。

---

## 0. 总体验收口径（Definition of Done）

当满足以下条件时，认为“评估闭环可作为默认工程流水线使用”：

1) **可信**：同一条关键路径在同环境连续跑多次，回归判定稳定（误报率可控）。  
2) **可解释**：任何 FAIL/P0，都能在 1–2 次点击内定位到证据（trace/run/syscalls/evidence）。  
3) **可治理**：策略/门槛变更有审批、审计、回滚路径，不依赖口头沟通。  
4) **可持续**：接口与文档不脱节（CI 护栏生效），新增字段/门控不会“暗改线上口径”。

---

## 1) P0（必须先做）：让结果“可信”

### P0-1：Baseline 选择规则（回归对比的地基）

**为什么优先**：没有稳定 baseline，所有 diff/回归门控都不可信，后续 canary/ship 自动化会被噪音淹没。  

**建议默认策略（推荐）**：
- baseline 维度优先：`project_id` → `run` → `manual指定`
- 规则：
  1. 若请求显式传 `base_evidence_pack_id`：使用它（最确定）
  2. 否则若有 `project_id`：选择该 project 的“最新通过（PASS）的基线 evidence_pack”
  3. 否则回退到同 run 的上一份 evidence_pack

**验收标准**：
- 同一 project、同一 URL、同一 steps/tag：连续跑 3 次，baseline 不漂移（除非你显式指定）。
- 任一次回归判定失败，都能明确指出使用了哪个 baseline evidence_pack_id（写入 evaluation_report / metadata）。

**实现接线点（参考）**：
- `core/server.py: auto_run_evaluation()`（baseline 选择逻辑入口）
- `core/server.py: compute_run_evidence_diff()`（允许显式 base/new）
- `core/services/execution_store.py: list_learning_artifacts()`（查询候选基线）

**建议新增测试**：
- baseline 选择的单测（构造多份 artifacts，验证选择顺序与过滤条件）

---

### P0-2：抗波动（flaky）机制（降低误报成本）

**目标**：把“偶发网络/页面抖动”从 P0 级噪音降为可控信号。  

**建议策略**：
- 指标容忍：
  - `max_new_network_4xx / 5xx` 支持小阈值（你们已有）
  - 对 screenshot changes 支持 tag 白名单/阈值（你们已有字段）
- 评估重试（仅对取证环节）：
  - evidence 采集失败或波动过大时：允许最多 N 次重采集（N=1 或 2）
  - 以“中位数/最小值”作为 duration 口径，避免偶发抖动

**验收标准**：
- 在“无真实回归”的场景下：连续 10 次跑，P0 回归误报 ≤ 1 次（可按团队阈值调整）。
- 每次重试都必须记录到 evidence_pack.metadata（可审计，避免静默重试掩盖问题）。

---

### P0-3：取证采样策略（成本与稳定性的平衡）

**目标**：固定采样点，既能覆盖关键路径，又不把执行时间拉爆。  

**建议**：
- 仅在 tag 切换时采样（你们当前 by_tag 的思路），并明确：
  - 每个 tag 的采样必须包括 screenshot + console + network（最小集合）
  - tag 内多 step 不必每步截图（减少噪音）

**验收标准**：
- 典型关键路径（3–5 个 tags）单次评估耗时在可接受范围（例如 < 60s，视环境而定）。
- `expected_tags` 覆盖率输出稳定：缺 tag 必须是硬失败（或按 policy 决定）。

---

### P0-4：关键路径断言（tag_assertions）口径冻结

**目标**：把“关键路径是否真走完/页面是否正确”变成稳定硬门控。  

**验收标准**：
- `tag_expectations` 失败必为 P0，并写入可定位字段（tag、失败原因、证据位置）。
- 模板化（tag_templates）可以一键复用，并可被 project policy 覆盖。

**实现证据**：
- `core/harness/evaluation/tag_assertions.py`
- `core/harness/evaluation/policy.py`（tag_templates）

---

## 2) P1（在可信后做）：让流程“可治理/可规模化”

### P1-1：Canary（定时评估 + 自动决策/升级）

**目标**：把“回归检测”从手工触发变为定时/发布后自动触发。  

**最小落地**：
- 先做“只报告不回滚”：定时跑 auto-eval，生成 `canary_report`（可复用 evaluation_report 也可新 kind）
- 命中 regression_gate / tag_assertions 时：
  - 自动创建 change-control 记录（或关联现有 change_id）
  - 输出建议动作（block/rollback/continue）

**验收标准**：
- canary 每次执行都落库 artifacts，并带 run/trace/evidence 链接。
- 命中 P0 时有统一入口查看“为什么”（Investigate 报告或 Links 联动）。

---

### P1-2：Investigate（调查报告一键聚合）

**目标**：任何 FAIL/P0，1–2 次点击直达证据链（减少人肉翻日志）。  

**最小落地**：
- 新增 `investigate_report` artifact（或在 evaluation_report 中新增 investigation section）
- 聚合内容：
  - trace_id / run_id
  - 关键 syscall_events（tool/llm/skill）
  - evidence_pack（by_tag）
  - evidence_diff summary + metrics

**验收标准**：
- FAIL 后从 Workflows/Runs 页一键进入调查报告。
- 报告中每个证据对象都有可点击跳转（Artifacts/Links/Traces/Syscalls）。

---

### P1-3：Ship Gate（发布前置门控）

**目标**：把 QA+Gate 变成发布/变更的前置条件（默认安全）。  

**最小落地**：
- 在 publish/变更流程前自动触发一次 QA+Gate（或复用 autosmoke）
- 失败则阻断并给出操作建议/证据链接

**验收标准**：
- 默认路径不可绕过（除非显式 override，并记录审计）。
- Gate 的结论与证据可追溯到 artifacts（不是一条临时日志）。

---

### P1-4：策略变更治理（project policy）

**目标**：策略变更不再靠群里喊话，而是可审计、可审批、可回滚。  

**验收标准**：
- project policy 变更进入 change-control（你们已接入 autosmoke gate），并在 UI 可追踪 change_id。
- policy 继承覆盖口径清晰：system/default ⊕ project ⊕ request override。

---

## 3) P2（最后再做）：体验与自动化扩展

- Workflows 扩展更多“一键流水线”（/review、/benchmark、/document-release 等）
- 评估报告的可视化（趋势、对比、按 tag 展开）
- 指标长期趋势与告警（监控闭环）

---

## 4. 证据索引（Evidence Index）

### 已有关键文档

- `docs/design/evaluation/auto-eval-and-regression.md`
- `docs/design/evaluation/openapi-eval.snapshot.json`

### 关键代码入口（抽样）

- `core/server.py: auto_run_evaluation() / compute_run_evidence_diff() / upsert_project_evaluation_policy()`
- `core/harness/evaluation/evidence_diff.py`
- `core/harness/evaluation/tag_assertions.py`
- `core/harness/evaluation/policy.py`

### 已有关联测试（抽样）

- `core/tests/unit/test_harness/test_evidence_diff.py`
- `core/tests/unit/test_harness/test_tag_assertions.py`
- `core/tests/unit/test_harness/test_evaluation_policy_merge.py`
- 文档护栏：
  - `core/tests/unit/test_docs/test_auto_eval_docs_guard.py`
  - `core/tests/unit/test_docs/test_auto_eval_openapi_snapshot_guard.py`
  - `core/tests/unit/test_docs/test_auto_eval_doc_openapi_section_guard.py`

