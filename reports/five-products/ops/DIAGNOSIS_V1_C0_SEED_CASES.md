# DIAGNOSIS_V1 C0 — Seed cases（已知根因 ground truth）

- **charter**: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md) D9  
- **unfreeze**: [`ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md)  
- **用途**：诊断准确度评测的标签集；**不是**生产诊断结论  
- **数量**：25（≥20；预留扩展到 30）  
- **场景**：S1 = run 失败；S2 = 版本回归  
- **规则**：每个 case 有且仅有一个 **gold_root_cause**；允许 `secondary_causes`；无证据路径必须标 `expect_unknown` 或 `expect_stale`

## 标签约定

| 字段 | 说明 |
|---|---|
| `case_id` | 稳定 ID |
| `scenario` | `run_failure` \| `version_regression` |
| `gold_root_cause` | 一级根因标签（枚举见下） |
| `required_evidence` | 缺任一则应 `unknown`（不得硬猜） |
| `recommended_action` | 建议类（不自动执行） |

### 根因枚举（v0）

`tool_error` · `wrong_model_route` · `sop_gap` · `context_missing` · `policy_deny` · `timeout` · `cost_anomaly` · `prompt_regression` · `config_drift` · `deploy_break` · `eval_score_drop` · `fde_evidence_gap` · `data_stale` · `insufficient_evidence`

---

## Seed table

| # | case_id | scenario | gold_root_cause | 简述 | required_evidence | recommended_action |
|---:|---|---|---|---|---|---|
| 1 | `dx.s1.tool_timeout` | run_failure | `timeout` | Agent run 工具调用超时后整 run fail | run + syscall(tool) + duration | 调大工具超时 / 拆长调用 |
| 2 | `dx.s1.tool_wrong_args` | run_failure | `tool_error` | 工具参数 schema 不匹配返回 4xx | run + syscall + tool result | 修 skill/tool schema 绑定 |
| 3 | `dx.s1.model_route_cheap` | run_failure | `wrong_model_route` | 复杂推理任务被路由到弱模型导致胡答 | run + model id + routing decision | 锁 purpose→model / 升路由档 |
| 4 | `dx.s1.sop_skip_review` | run_failure | `sop_gap` | SOP 要求 peer-review，stage 跳过 | run + stage config + skill call log | 修 PipelineStageConfig / skill 绑定 |
| 5 | `dx.s1.context_trunc` | run_failure | `context_missing` | 关键材料被压缩掉导致答非所问 | run + context assemble + token budget | 调预算 / 保护关键层 |
| 6 | `dx.s1.policy_tool_deny` | run_failure | `policy_deny` | PolicyGate 拒绝危险工具，表现为失败 | run + policy decision + audit | 改策略或换安全路径 |
| 7 | `dx.s1.cost_spike_abort` | run_failure | `cost_anomaly` | 单 run token 超阈值触发中止 | run + usage + cost gate | 限步数 / 换模型 / 拆任务 |
| 8 | `dx.s1.syscall_crash` | run_failure | `tool_error` | syscall 进程崩溃无结构化结果 | run + syscall + stderr | 修工具实现 / 加重试 |
| 9 | `dx.s1.auth_scope` | run_failure | `policy_deny` | tenant scope 不足导致 KB 检索空失败 | run + auth scopes + retrieve log | 补 scope / 换只读路径 |
| 10 | `dx.s1.no_trace` | run_failure | `insufficient_evidence` | 只有失败状态无 trace | run status only | 返回 `unknown`；要求开 trace |
| 11 | `dx.s1.fde_missing_field` | run_failure | `fde_evidence_gap` | FDE 现场证据未回传，无法判交付失败因 | fde project + evidence envelope | 补现场证据采集 |
| 12 | `dx.s1.pi_offline_log` | run_failure | `deploy_break` | Pi 边缘执行失败但控制面只有 disconnect | pi healthz + local log ref | 查边缘部署/连通 |
| 13 | `dx.s1.rag_empty` | run_failure | `context_missing` | RAG 零召回导致 grounded 失败 | retrieve log + kb version | 修索引/查询/过滤 |
| 14 | `dx.s1.stale_kb` | run_failure | `data_stale` | 命中过期 wiki，证据时间戳过期 | evidence time + doc version | 返回 `stale`；刷新知识 |
| 15 | `dx.s1.prompt_injection_block` | run_failure | `policy_deny` | 安全扫描拦截用户输入 | safety scan + policy | 提示改写 / 人工复核 |
| 16 | `dx.s2.prompt_edit` | version_regression | `prompt_regression` | v2 改 system prompt 后评测分骤降 | version diff + eval report A/B | 回滚 prompt / 差分评审 |
| 17 | `dx.s2.model_swap` | version_regression | `wrong_model_route` | Bundle 默认模型从强改弱 | version snapshot + model id + eval | 恢复模型 / 分 purpose |
| 18 | `dx.s2.skill_remove` | version_regression | `sop_gap` | 移除必选 skill 导致阶段质量下降 | team yaml diff + eval | 恢复 skill / 补替代 |
| 19 | `dx.s2.config_temp` | version_regression | `config_drift` | temperature/阈值漂移导致不稳定 | config snapshot + k-repeat | 锁配置基线 |
| 20 | `dx.s2.tool_perm` | version_regression | `policy_deny` | 新策略收紧工具白名单 | policy diff + deny logs + eval | 白名单回滚或改 SOP |
| 21 | `dx.s2.context_budget` | version_regression | `context_missing` | 上下文预算下调后召回变差 | budget diff + retrieve + eval | 恢复预算 / 分层压缩 |
| 22 | `dx.s2.eval_gate_fail` | version_regression | `eval_score_drop` | nightly gate pass_rate 低于阈值 | eval gate report + baseline | 查失败 taxonomy；阻断发布 |
| 23 | `dx.s2.pi_image` | version_regression | `deploy_break` | Pi 镜像升级后本地 skill 不可用 | pi deploy record + healthz | 回滚镜像 / 修兼容 |
| 24 | `dx.s2.fde_checklist` | version_regression | `fde_evidence_gap` | 新版本验收项增加但无证据模板 | fde checklist diff | 补证据模板；暂标 unknown |
| 25 | `dx.s2.no_baseline` | version_regression | `insufficient_evidence` | 声称回归但无 v1 基线报告 | （缺 baseline） | 返回 `unknown`；先建基线 |

---

## 分布

| scenario | count |
|---|---:|
| run_failure | 15 |
| version_regression | 10 |
| **total** | **25** |

| gold_root_cause | count |
|---|---:|
| tool_error | 2 |
| timeout | 1 |
| wrong_model_route | 2 |
| sop_gap | 2 |
| context_missing | 3 |
| policy_deny | 4 |
| cost_anomaly | 1 |
| deploy_break | 2 |
| prompt_regression | 1 |
| config_drift | 1 |
| eval_score_drop | 1 |
| fde_evidence_gap | 2 |
| data_stale | 1 |
| insufficient_evidence | 2 |

---

## 使用方式（C1+）

1. 每个 case 配一份最小证据 fixture（或指向现有 traces/eval reports）；  
2. 诊断引擎输出 Top-K 假设；与 `gold_root_cause` 比对算 Top-1/Top-3；  
3. `insufficient_evidence` / `data_stale` case 必须分别产出 `unknown` / `stale`，否则计错；  
4. **禁止**在无 seed 时宣称诊断准确率。

## 扩展到 30

预留 5 个槽位：跨产品链路断点、Ontology 冲突、外部 connector（后置）、业务 telemetry（后置）、并发竞态。C0 不强制填满。
