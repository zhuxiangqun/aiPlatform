---
title: "aiPlat 商业价值白皮书"
volume_id: commercial-value
type: whitepaper-volume
status: generated
generated_at: "2026-10-19T12:47:52Z"
audience: "CEO、CFO、业务负责人、投资方"
core_question: "投资回报与 TCO 如何？"
priority: P3
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30"
caps_sha256: "d5aec7fa568f6fcd65fee1cbc3ed395a47b1daf9fbe66f26132d206de6ac9962"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=commercial-value suite_sha256=0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30 caps_sha256=d5aec7fa568f6fcd65fee1cbc3ed395a47b1daf9fbe66f26132d206de6ac9962 scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 商业价值白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `commercial-value` |
| 受众 | CEO、CFO、业务负责人、投资方 |
| 核心问题 | 投资回报与 TCO 如何？ |
| 优先级 | P3 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-19T12:47:52Z` |
| CAPABILITIES sha256 | `d5aec7fa568f…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

**备注**：

论证以价值系统 + TCO + 内部示意闭环。真实客户案例走 cases/ 授权流程，不阻塞 ready。 禁止在卷内填写未经客户授权的 ROI 数字。


## 1. 本卷论证目标

本卷面向 **CEO、CFO、业务负责人、投资方**，围绕「**投资回报与 TCO 如何？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`AIPLAT_ROADMAP.md`](../../AIPLAT_ROADMAP.md) | 商业化路线图 / 评分基线 | ✅ |
| [`docs/whitepaper/commercial-value-model.md`](../commercial-value-model.md) | TCO + 五维价值模型（链 value_calculator） | ✅ |
| [`docs/whitepaper/cases/internal-illustrative-fde.md`](../cases/internal-illustrative-fde.md) | 内部示意案例（authorized: false） | ✅ |
| [`docs/whitepaper/cases/README.md`](../cases/README.md) | 客户案例授权流程 | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/strategy/comparison-vs-vendors.md`](../strategy/comparison-vs-vendors.md) | 厂商策略对比（非客户 ROI） | ✅ |
| [`docs/framework/assessment-scores.json`](../framework/assessment-scores.json) | 成熟度评分戳（辅助投资论证，非财务 ROI） | ✅ |
| [`docs/research/aiPlat核心能力对标报告.md`](../research/aiPlat核心能力对标报告.md) | 能力差异（技术侧，非财务） | ✅ |
| [`aiPlat-core/core/harness/finance/value_calculator.py`](../../aiPlat-core/core/harness/finance/value_calculator.py) | 五维价值计量实现 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 商业价值模型

本卷不引用未授权的客户 ROI、人天单价或伙伴分成比例。商业论证以平台已接线的价值系统为准：

- 价值维度与算法符号：[`aiPlat-core/core/harness/finance/value_calculator.py`](../../aiPlat-core/core/harness/finance/value_calculator.py)
- 五维价值映射与 TCO 对照：[`docs/whitepaper/commercial-value-model.md`](../commercial-value-model.md)
- CEO/CFO/PM 翻译口径：见 `commercial-value-model.md` 第 2 节
- 分阶段落地闸门：见 `commercial-value-model.md` 第 4 节
- 示意案例：[`docs/whitepaper/cases/internal-illustrative-fde.md`](../cases/internal-illustrative-fde.md)

---

> **非客户授权案例声明**
>
> `cases/internal-illustrative-fde.md` 为内部示意，`authorized: false`、`kind: illustrative`，仅用于说明算法与口径，不构成任何客户承诺或收益保证。真实客户案例必须走 [`docs/whitepaper/cases/README.md`](../cases/README.md) 授权流程。

---

商业卷 ready 边界：价值系统已接线、TCO 对照清单已闭环、内部示意 worked example 已标注。真实客户数字与商务条款后续只追加 `cases/` 与商务附录，不重做卷骨架。

### 3.1 价值模型专稿（节选）

### 商业价值模型（权威专稿）

> 供商业价值白皮书节选。不编造客户授权 ROI%、人天单价或伙伴分成。  
> 算法符号权威：`aiPlat-core/core/harness/finance/value_calculator.py`

#### 1. TCO 对照项

| TCO 项 | 说明 | 平台侧可观测/材料 |
|--------|------|-------------------|
| 平台接入成本 | 部署、租户开通、身份集成 | infra 部署手册 · 管理端 |
| 模型调用成本 | Token / 本地推理机时 | ModelManager · 配额/限流 |
| 工具与集成成本 | MCP/API/工具允许列表运维 | PolicyGate · MCP 准入 |
| 运维与治理成本 | 审计、评测、架构守卫、值班 | CAPABILITIES 治理切片 |
| 组织与培训成本 | FDE/ORG 签收、手册上手 | `docs/manuals/` |

自建 Harness+RAG+治理时，上表五项通常由客户自行承担；采用平台时对应项转入订阅/私有化运维账单。**具体单价由商务报价填写，本专稿不预设数字。**

#### 2. 五维价值映射（CEO / CFO / PM）

平台 `ValueCalculator` 将运行结果聚合为五维（字段见 `MonthlyValueReport` / `ValueMetrics`）：

| 维度 | 代码字段（示意） | CEO | CFO | PM |
|------|------------------|-----|-----|-----|
| 效率 | `efficiency_saved` / `efficiency` | 战略吞吐 | 人天替代成本 | 交付周期 |
| 质量 | `quality_value` / `skill_pass_rate` | 风险下降 | 返工成本 | 通过率 |
| 安全 | `safety_value` / `attacks_blocked` | 合规可信 | 事故损失规避 | 拦截次数 |
| 创新 | `innovation_value` / `new_task_type` | 新能力覆盖 | 试错成本 | 新任务类型 |
| 体验 | `experience_value` / `user_satisfaction` | NPS/采用 | 支持成本 | 满意度 |

翻译入口：`ValueCalculator.translate_for(report, audience)`（`audience` ∈ CEO/CFO/PM）。

#### 3. 示意算法（占位参数，非客户财报）

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

#### 4. 分阶段闸门

| 阶段 | 目标 | 闸门 |
|------|------|------|
| 试点 | 能力验证 | PoC 签收 · 关键路径可演示 |
| 扩展 | 成本/价值对照 | TCO 五项有基线 · 价值五维有月报 |
| 规模化 | 治理与合规复核 | PolicyGate/评测/审计绿 · ORG 签收包 |

#### 5. 授权边界

- 未授权客户数字 **不得** 写入 `volumes/03-commercial-value.md` 正文作承诺。
- 内部示意见 [`cases/internal-illustrative-fde.md`](./cases/internal-illustrative-fde.md)（`authorized: false`）。
- 授权流程见 [`cases/README.md`](./cases/README.md)。


> generated_at=`2026-07-08T09:51:09` · spec=`1.0.0`

| 框架 | 结果 |
|------|------|
| 8轴自主性成熟度 | **L5** (5.0) |
| 工程落地评估(58项) | **100.0%** |
| 三层企业评估(~110项) | _(见 JSON)_ |

### 3.2 商业化路线图（节选）

> 下列 ROADMAP 是内部作战手册节选，不是对外已审计财报；勿将路线图基线误读为客户授权 ROI。

### aiPlat 商业化演进终极作战手册

> 基线：代码交叉验证 | 能力计数见 AIPLAT_CAPABILITIES.md 统计表 | 6/6 syntax,5/5服务健康,架构守卫0违规,全域诊断14项,路径标准化158条
> 对标：Hermes Agent · Claude Code · OpenClaw · Octo (明略科技)  
> 定位：**企业级 FDE 操作系统**（Agent 协作网络 + Spec 生命周期管理）
> 
> **当前能力全貌**：参见 [`AIPLAT_CAPABILITIES.md`](./AIPLAT_CAPABILITIES.md)（当前计数见该文件）
> 
> **最新更新 (2026-07-19)**：P0-P3 hermès-agent 全量吸收 + L6升级三步 + MoA多模型推理。当前计数见 AIPLAT_CAPABILITIES.md。

---

#### 一、基线诊断（来自 `AIPLAT_CAPABILITIES.md` 代码交叉验证，当前计数见该文件统计表）

| 维度 | 评分 | 关键发现 |
|------|:---:|------|
| **Harness 内核** | **A+** | ReAct循环 + 14 Hook + LangGraph checkpoint/resume + Pipeline引擎 + 5级压缩 + 工具输出预算帽 + PatternCache + EmbeddingBridge |
| **记忆子系统** | **A+** | 四层架构 (Working→Episodic→Semantic→TaskSkills) + 软删除动态续期 + 投毒防御字段 + Episodic预评分 + critical_episodes + 每日后台清理 |
| **知识引擎** | **A+** | 本体13步管线 + GraphIndex/HyperEdge + StateMachine + KnowledgeSynthesizer + Palantir 9项对齐 + 多域本体 |
| **企业治理** | **A** | 172 arch_guard规则 + Skill Lint 10规则 + 三层多租户 + 诊断检查 + ComplianceChecks + CapabilityConvergence |
| **基础设施** | **A** | Multi-backend cache/vector/messaging/database/storage + 模型健康检查/质量验证/延迟追踪 + 本地模型自动发现 |
| **Agent 系统** | **A** | 7种实现类 + DynamicRouter(LLM路由) + SubAgent协调器 + ParallelExecutor + 四角色协作体系 |
| **Skill 系统** | **A** | SkillOpt双通道分析 + Rejected Edit Buffer + edit learning rate + effects副作用声明 + semver回滚 + AutoLearner + EvolutionEngine 12步夜间进化 |
| **MCP 协议** | **A** | JSON-RPC 2.0 + HTTP/SSE服务 + Stdio传输 + ClientManager + Runtime + ProductionPolicy |
| **Gate 系统** | **A** | ContextGate/SchemaGate/ResilienceGate/TraceGate/SandboxGate + PolicyGate + ApprovalGate 双门禁 + CircuitBreaker |
| **评估系统** | **A** | EvaluationRunner + HallucinationTracker + RAG Evaluator + DriftDetector + AB Optimizer + CoverageGate + GraphDiff + CodeTestReward |
| **RAG 检索** | **A** | CRAG 3级回退 + HyDE + RRF三路融合 + Graph Early Exit + SemanticCache版本化 + CircuitBreaker + DomainRouter + DocumentConverter协议化 |
| **产品体验** | **A-** | FDE Dashboard 4卡+时间轴 + SpecDetail 3Tab+Revise+Matter + UserWorkbench增强 + OnboardingWizard→Spec联动 + 训练监控 + VS Code插件(已打包.vsix) |
| **自进化能力** | **A** | SpecLifecycle 版本状态机 + FeedbackRadar 5类信号→Spec建议 + TraceVisualizer 决策痕迹 + EvolutionEngine Step13 SpecHealth + SFT→RL桥接 |
| **可观测性** | **A+** | trace_id/span_id + PipelineTrace + 10项Prometheus + 诊断25类(含14项全域测试) + FDE Dashboard + CoT自动注入 + 内联自纠错 |
| **安全合规** | **A-** | ImmuneMemory三级渐进拦截 + CircuitBreaker熔断 + 注入防护 + 投毒防御 + PII检测 + 对象级/字段级权限 + Ed25519签名 + SecretsManager |
| **成本控制** | **A** | 本地模型Ollama + 零LLM分类 + 5级压缩 + 工具输出预算帽 + 语义缓存版本化 + Multi-backend存储 + RewardTuner多目标EMA调权 |
| **编排层** | **A+** | 5 routing_modes (static/llm/debate/swarm/roundtable) + DynamicRouter + Reducer + DebateState收敛 + Swarm竞选择优 + Roundtable平等讨论 + 业务价值系统 |
| **训练管道** | **A** | SFT→RL完整桥接 + TrajectoryScorer四维评分 + 混合采样 + 可模仿性过滤 + RLOOUpdater + Online Rollout + 训练监控前端 |
| **综合评分** | **99/100** | **FDE 操作系统 (A+) + 5 routing_modes (A+) + Spec 生命周期 (A) + 全域诊断 (A+) + 核心 Skills (A)** |

---

#### 二、执行路线图

```
2026 Q3              Q4                 2027 Q1           Q2
Jul Aug Sep | Oct Nov Dec | Jan Feb Mar | Apr May Jun

Phase 0: 紧急止血 (✅ 已完成)
├─ 0.1 PII脱敏  ✅
├─ 0.2 OTel     ✅  
└─ 0.3 语义缓存  ✅

Phase 1: 铸造利刃 (✅ 已完成)
├─ 1.1 SDK      ✅ (基础就绪, SDK包待完善)
├─ 1.2 FanOut   ✅ (ParallelExecutor + DynamicRouter)
└─ 1.3 VS Code  ✅ (已编译 + .vsix 7.9KB 打包)

Phase 2: 自进化 (✅ 已完成)
├─ 2.1 自学习   ✅ (AutoLearner全接线 + SkillOpt双通道 + PatternAccumulator)
├─ 2.2 溯源     ✅ (ProvenanceTracker + context snapshot)
└─ 2.3 企业网关  ✅ (EnterpriseGateway飞书/企微/Slack)

Phase 3: 企业级 (✅ 已完成)
├─ 3.1 四角色体系  ✅ (员工/保安/顾问/协调员 + KPIAgent + StrategyAgent)
├─ 3.2 SFT→RL管线 ✅ (TrajectoryScorer + 混合采样 + 可模仿性 + RLOO + Online Rollout)
├─ 3.3 实时异常感知  ✅ (ToolDriftDetector + ImmuneMemory + CircuitBreaker 三层闭环)
├─ 3.4 业务价值系统  ✅ (五维ROI + 三受众翻译 + GoalAwareRouter + 月度通知)
└─ 3.5 入驻+终端    ✅ (OnboardingWizard 7步 + UserWorkbench + ValueCenter 8页面)

Phase 4: FDE 操作系统 (✅ 已完成 — 本会话)
├─ 4.1 Spec 生命周期  ✅ (SpecLifecycle DRAFT→PENDING→EXECUTING→REVIEW→STABLE→ARCHIVED)
├─ 4.2 用户反馈翻译  ✅ (FeedbackRadar 5类信号→Spec调整建议)
├─ 4.3 决策痕迹可视化 ✅ (TraceVisualizer 犹豫/重复/异常→Spec 建议)
├─ 4.4 FDE 仪表板      ✅ (4卡聚合+时间轴+筛选联动+种子Demo)
├─ 4.5 全域诊断        ✅ (14项检查: 5条旅程 + 5 routing_modes)
├─ 4.6 核心 Skills      ✅ (CoT模板化注入 + 内联自纠错 + Debate/Swarm/Roundtable)
├─ 4.7 合规审计修复    ✅ (agent list_all + shell agents + env-legacy标记)
└─ 4.8 Matter 验收      ✅ (交付物定义 + 验收标准 + SpecDetail revise 增强)

Phase 5: 竞品借鉴（✅ 已完成 — 本会话）
├─ 5.1  MCP 工具延迟加载   ✅ (启动仅加载名称, Schema按需获取)
├─ 5.2  Prompt Caching      ✅ (cache_control注入 + SHA256跨会话持久化 + 集成测试)
├─ 5.3  Permissions 三层优先级 ✅ (deny>ask>allow + fnmatch参数级匹配)
├─ 5.4  Subagent 上下文隔离    ✅ (isolate_context + read_only_context)
├─ 5.5  File-based Memory      ✅ (Markdown双写 + SQLite索引)
├─ 5.6  工具自发现             ✅ (已有 discovery.py)
├─ 5.7  Plugin Slot 模式       ✅ (slot registry + archive)
├─ 5.8  Auto Memory 自动学习   ✅ (纠正≥2次/10轮交互自动保存到文件)
├─ 5.9  多租户检索隔离修复     ✅ (WikiPageRetriever tenant_id mismatch WARNING→ERROR阻断)
├─ 5.10 文档全部同步至 427✅   ✅ (6个核心文档数字一致, CI校验器通过)
└─ 5.11 平台能力提升 (Palantir碎石路→高速公路) ✅ (promote→approve→SkillRegistry)
├─ 5.12 模型训练(RL) + 知识蒸馏 ✅ (DistillationEngine(PyTorch接线) + RL API + FineTune 4-Tab UI)
├─ 5.13 从零训练引擎 ✅ (FullTrainingEngine, gpt2/pythia-160m/gpt2-medium, FineTune 5-Tab)
└─ 5.14 五角色权限体系 ✅ (SystemRole(5), ROUTE_PERMISSIONS, 侧边栏显隐, 43端点认证)

评分: 90 → 99
```

---

##### Phase 0：紧急止血 — 安全合规基线

> **目标**: 通过企业 IT 安全/运维评审，拿到金融/政务采购入场券  
> **周期**: 6 周（Q3 2026） | **人力**: 2 后端 + 1 运维 | **成本增量**: ~$700/月

---

###### 0.1 PII 自动脱敏（2 周）

**实施位置**:
- `core/services/pii_detector.py` — 新建
- `core/harness/syscalls/llm.py` — `_guard_messages()` 扩展

**技术方案**:

```
Presidio + 自建正则双跑（并行，取并集）:

  输入 Prompt → ┌─ Presidio Analyzer (NER) ─┐
                └─ 自建正则 (手机/身份证) ──┘
                          ↓ 取并集 (宁可误标，不可漏标)
  masked_text + mapping = pii_detector.mask(text)
  存储 mapping → request_context (Redis/内存)
  
  LLM 返回后:
  unmasked_text = pii_detector.unmask(response, mapping)
    └─ unmask 前检查 Context.role (仅 admin/data_owner 可见原文)
        普通用户 → 返回 [MASKED]
```

**RBAC 权限模型**:

```python
### pii_detector.py
ALLOWED_UNMASK_ROLES = {"admin", "data_owner"}

def unmask(text: str, mapping: dict, role: str) -> str:
    """还原 PII。仅 admin 和 data_owner 可看原文。"""
    if role not in ALLOWED_UNMASK_ROLES:
        return text  # 保持 [MASKED]
    return _apply_unmask(text, mapping)
```

**验收 KPI**:
- [x] 输入含手机号/身份证/邮箱 → ✅ 已实现：PII Detector 内置正则 + Presidio 双引擎 `[PHONE_001]` / `[ID_001]` / `[EMAIL_001]`
- [x] LLM 返回 → ✅ 已实现：unmask() RBAC 控制 (admin/data_owner only) `[MASKED]`
- [x] 审计日志 → ✅ 已实现：llm.py:224-230 记录 pii_mask/pii_unmask
- [x] arch_guard → ✅ 已实现：§69 PII脱敏规则
- [x] 安全扫描 → ✅ 已实现：PII检测在sys_llm_generate入口强制拦截

**降级方案**: 若 Presidio 中文支持不足 → 自建 NER + 正则为主（误标率 < 5% 可接受）

---

###### 0.2 OpenTelemetry + Prometheus（2 周）

**实施位置**:
- `core/server.py` — FastAPI middleware
- `core/harness/syscalls/llm.py` — LLM 调用 instrumentation

**技术方案**:

```python
### core/server.py
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)  # /metrics

### core/harness/syscalls/llm.py
@tracer.start_as_current_span("sys_llm_generate")
async def sys_llm_generate(model, messages, **kwargs):
    span = trace.get_current_span()
    span.set_attribute("model", model_name)
    span.set_attribute("tokens", usage.total_tokens)
```

**暴露指标**:
- `llm_calls_total{purpose, model}` — LLM 调用总数
- `llm_latency_seconds{purpose}` — LLM 延迟分布 (P50/P95/P99)
- `rag_retrieval_hits{domain}` — RAG 检索命中数
- `pipeline_stage_duration{stage}` — Pipeline 各阶段延迟
- `circuit_breaker_state{breaker}` — 熔断器状态 (0=CLOSED/1=OPEN/2=HALF_OPEN)
- `memory_compression_level` — 当前压缩级别

**验收 KPI**:
- [x] `/metrics` 端点 → ✅ 已实现：prometheus_fastapi_instrumentator (server.py:1549)
- [x] Grafana 面板 → ✅ prometheus_fastapi_instrumentator 已集成 (/metrics)，面板 JSON 待创建: LLM QPS/latency P95/error rate
- [x] Jaeger/OTEL → ✅ OTEL bridge 已集成 (server.py:1533), OpenTelemetry span 已启用 可追溯
- [x] Pipeline 延迟 → ✅ PipelineTrace 每阶段记录 started/completed/failed (pipeline_engine.py)

---

###### 0.3 语义缓存（2 周）— ⚡ 已部分交付 (2026-06-24)

**状态**：L1/L2 缓存已接线 + INCR 版本号原子切换 + L1 主动清 + 版本窗口上限。
待补：所有入库路径 (`/documents/ingest-directory`, `/kb/watch`) 统一调用 `invalidate()`。
- `core/harness/knowledge/semantic_cache.py` — 新建
- `materials_chat.py` — `execute()` 入口

**技术方案**:

```
三层缓存:
  Layer 1 (L1): 精确匹配
    key = md5(query + domain_id)
    Redis GET → 命中 → 直接返回 (TTFT < 50ms)

  Layer 2 (L2): 语义相似
    embedding = embed(query)
    Redis VECTOR_SIM → cosine ≥ 0.95 → 返回缓存结果 (TTFT < 200ms)

  Layer 3 (L3): 无命中
    → 走正常 RAG Pipeline → 结果写入 L1 + L2

失效策略:
  知识库更新 (wiki_engine.write_page / kb_ingest) →
    → 清空相关 domain 的所有 L1/L2 缓存
    → EventBus.publish("cache_invalidated", domain_id)
```

**集成点** (`materials_chat.py:execute()` 入口):

```python
async def execute(self, context):
    cache_key = md5(query + domain_id)
    
    # L1: 精确匹配
    cached = await redis.get(cache_key)
    if cached:
        return cached  # TTFT < 50ms
    
    # L2: 语义相似
    cached = await semantic_cache.search(query_embedding, domain_id)
    if cached:
        return cached  # TTFT < 200ms
    
    # L3: 正常流程
    result = await self._pipeline(...)
    
    # 写入缓存
    await redis.setex(cache_key, ttl=3600, value=result)
    await semantic_cache.store(query_embedding, result, domain_id)
    
    return result
```

**验收 KPI**:
- [x] L1 命中 → ✅ get_l1() 已实现 (semantic_cache.py:111), TTFT < 50ms
- [x] L2 命中 → ✅ get_l2() 已实现 (cosine ≥ 0.95, semantic_cache.py:148), TTFT < 200ms
- [x] 缓存失效 → ✅ invalidate_domain() 已接线 (wiki.py ingest 后自动调用)
- [x] Token 节省 → 📊 已实现三层缓存架构，节省效果待生产实测

---

##### Phase 1：铸造"开发者利刃"

> **目标**: 从"精密重型实验室设备"升级为"开发者友好型工具"  
> **周期**: 12 周（Q4 2026） | **人力**: 3 后端 + 1 前端 | **成本增量**: $0

---

###### 1.1 Agent SDK（4 周）

**实施位置**: `aiplat-sdk/` — 新建独立 Python 包

**API 设计**:

```python
from aiplat import Agent, Pipeline, Skill

### ── Level 1: 高级封装 (对齐 Claude Code Agent SDK) ──

### 3 行代码创建 + 执行 Agent
agent = Agent(name="my-analyst", model="qwen2.5-coder:7b")
agent.bind_skill("data_analysis")
result = agent.execute("分析上周销售数据")

### 流式模式
async for chunk in agent.stream("生成 Q3 报告"):
    print(chunk, end="")

### ── Level 2: 中级流水线 ──

pipeline = Pipeline()
pipeline.add_stage("retrieve", skill="knowledge_retrieval")
pipeline.add_stage("analyze", agent=agent)
pipeline.add_stage("report", skill="text_generation")
result = await pipeline.run(input_data)

### ── Level 3: 低级 Harness 控制 ──

from aiplat.harness import ReActLoop, StageConfig
loop = ReActLoop(model="qwen2.5-coder:7b", max_steps=20)
loop.on_hook("PreReasoning", my_callback)
loop.run(task_description)
```

**暴露层次**:
| Level | 封装 | 适用 |
|:---:|------|------|
| L1 | `aiplat.Agent` | 快速创建 Agent，对齐 Claude Code SDK |
| L2 | `aiplat.Pipeline` | 自定义流水线编排 |
| L3 | `aiplat.harness.ReActLoop` | 直接控制 Harness 执行循环 |

**验收 KPI**:
- [x] pip install → ✅ pyproject.toml 已配置, aiplat-sdk/ 目录可构建
- [x] 3行代码 → ✅ Agent(name, model) + bind_skill + execute (agent.py:1)
- [ ] SDK 内 Agent 与 Web UI 共享同一 Session/run_id
- [ ] 文档: API Reference + 5 个 QuickStart 示例
- [ ] GitHub Star > 200

---

###### 1.2 Sub-Agent FanOut 并行（4 周）

**实施位置**: `core/apps/agents/multi_agent.py` → 新增 `ParallelExecutor`

**Map-Reduce 模式**:

```
┌─────────────────────────────────────────────────────────┐
│  Main Agent (协调者)                                     │
│    task = "对比分析A/B/C三个方案"                          │
│                                                          │
│  Map Phase (并行, asyncio.gather):                        │
│    SubAgent_A → analyze("方案A") ─┐                       │
│    SubAgent_B → analyze("方案B") ─┤ 并行                  │
│    SubAgent_C → analyze("方案C") ─┘                       │
│         ↓                      ↓                         │
│    [result_A, result_B, result_C]                         │
│                                                          │
│  Reduce Phase (聚合):                                     │
│    LLM 对比 sub_results →

…

_(节选；全文见权威源)_


### 3.3 厂商策略对比（节选）

### aiPlat 与商业图数据库 / 知识图谱厂商 对比分析

> 本文对比 aiPlat 与四家国内图数据库 / 知识图谱厂商（海致科技、创邻科技、杭州悦数、星环科技）以及 Hermes Agent 的定位差异。
> 基于公开资料和各自产品特性整理，不构成采购建议。

---

#### 一、定位差异

**aiPlat 不是一个图数据库。它是图驱动的 AI 推理内核。**

| 方案 | 核心交付 | 目标用户 |
|------|---------|---------|
| **海致科技** | 全栈自研知识图谱 + 图模融合 + 行业大模型 | 金融/能源/政务企业 |
| **创邻科技** | 原生分布式图数据库 (Galaxybase) | 万亿级图数据处理 |
| **杭州悦数** | 成熟商业图数据库 | 企业级标准化需求 |
| **星环科技** | 图计算引擎 + 算法平台 | 高性能图计算场景 |
| **Hermes Agent** | 个人 AI 助手（认知调度） | 终端用户 |
| **aiPlat** | 图驱动的 AI 推理内核 | AI 应用开发者 |

四家商业厂商提供的是**图数据基础设施**——存、查、算、管一体化。aiPlat 提供的是**图驱动的 AI 推理内核**——用图结构约束和增强 LLM 输出，使知识图谱从存储层变为推理层。

Hermes Agent 更像 CLI 个人 AI 助手，而 aiPlat 像可嵌入任何应用的 AI 操作系统。

---

#### 二、六维度 × 五方案对比

##### 2.1 产品能力

| 维度 | 海致科技 | 创邻科技 | 杭州悦数 | 星环科技 | aiPlat |
|------|:--:|:--:|:--:|:--:|:--:|
| 图存储引擎 | AtlasGraph (自研) | Galaxybase (原生图) | 商业图数据库 | Sophon 平台 | SQLite + JSON |
| 数据规模 | 万亿级 | 万亿级 | — | — | 单 SQLite/域 |
| 图查询语言 | — | — | — | — | Python BFS API |
| 图算法库 | — | 丰富 | — | 丰富 | 无（无 PageRank 等） |
| LDBC 基准 | 有 | — | — | 领先 | 有目标未实测 |
| 图+LLM 融合 | 图模融合 | — | — | 待加强 | **CRAG/HyDE/Self-RAG** |
| 推理路径追溯 | — | — | — | — | **全链路录制+图验** |
| 本体规模 | — | — | — | — | 5 域/40类/52关系 |
| 13 步自动管线 | — | — | — | — | ✅ (classify→extract→resolve→state→graph→synthesis) |

##### 2.2 生态与集成

| 维度 | 商业厂商 | aiPlat |
|------|---------|--------|
| 数据导入 | ETL 工具、Kafka、JDBC、专有导入器 | YAML 本体定义 + Python 函数 + SQL/API/CSV/JSON/Excel 连接器 |
| 查询方式 | 专有查询语言 / Cypher / Gremlin | `GraphTraversal` Python API（无专用查询语言） |
| 工具链集成 | 数仓/BI/数据治理平台对接 | 零依赖，可嵌入任何 Python 应用或通过 REST API 调用 |
| 开放标准 | 部分兼容 TinkerPop/Gremlin | 不兼容 TinkerPop/Cypher/GQL，自有 API |
| 部署形态 | 私有化部署、云服务、一体机 | 开源 MIT，单进程，用户自行部署 |
| 许可证 | 商业许可 | MIT 开源 |

##### 2.3 与 Hermes Agent 的定位

| 维度 | 商业图厂商 | aiPlat | Hermes Agent |
|------|:--:|:--:|:--:|
| 核心交付 | 图数据库 | AI 推理内核 | 个人 AI 助手 |
| 图存储 | 专用图引擎 | SQLite | 无 |
| 图+LLM 融合 | 待完善 | **深度集成** | 无（纯调度） |
| 本体自动构建 | — | ✅ 13 步管线 | 无 |
| 部署模式 | 企业级分布式 | 单进程零依赖 | CLI 个人部署 |
| 目标用户 | 企业数据团队 | AI 应用开发者 | 终端用户 |
| 权限/安全 | 企业级 | PolicyGate + 架构边界 | 工具级允许列表 |

---

#### 三、维度详解

##### 3.1 图存储与规模 — aiPlat 的短板

- **商业厂商**：自研 / 原生图数据库，万亿级节点，LDBC 基准验证
- **aiPlat**：SQLite 为存储引擎，单域单文件，最大约 1TB 库大小。无分布式分片，无图原生存储引擎。查询靠 BFS 遍历（P95 < 500ms 目标）

**定位**：aiPlat 不适合需要万亿级图数据、高并发查询的场景。它是嵌入在 AI 运行时中的知识辅助层，不是独立图数据库。

##### 3.2 图+LLM 融合 — aiPlat 的核心长板

这是商业厂商文章中提及最少、也是 aiPlat 最深的领域：

| 能力 | 说明 | 代码 |
|------|------|------|
| 本体优先检索 | 3 级回退链：本体过滤 → FTS5 → HyDE | `materials_chat.py:380` |
| 图遍历增强查询 | 终端实体注入 LLM 上下文 `[related: e1, e2, ...]` | `graph_traversal.py:397` |
| 跨域查询降级 | 主域不足 → 自动 fallback 到补充域 | `sharded_graph.py:75` |
| 消幻图验证 | NLI 事实核查 + GraphIndex 边存在验证 | `hallucination_tracker.py` |
| 推理路径录制 | 从意图分类→遍历→检索→答案的完整链 | `materials_chat.py` |
| Self-RAG | low_evidence → 自动 HyDE 重检 | `materials_chat.py` |
| 语义缓存 | 3 层（精确→余弦≥0.95→穿透），减少 35-50% LLM 调用 | `semantic_cache.py` |
| 图推理 | YAML 规则引擎 → 传递闭包推断新边 | `graph_inference.py:174` |

##### 3.3 知识图谱构建 — 全自动 13 步

| 步骤 | 能力 | 代码行数 |
|------|------|:--:|
| 分类 | 关键词倒排索引 → T-Box 类映射（零 LLM） | 185 |
| 属性提取 | LLM 并行提取（semaphore=5） + table_context | 148 |
| 消歧 | 3 层（编辑距离 0.4 + 共现 0.3 + 上下文 0.3） | 273 |
| 状态机 | YAML 驱动（3 触发器 × 7 联动） | 403 |
| 推理 | YAML 规则 → 传递闭包推断边 | 174 |
| 合成 | 推理链/事实卡 → Wiki 页面 | 194 |
| 外部源 | SQL/API/CSV/JSON/Excel 连接器 | 263 |

##### 3.4 部署与自主可控

- **商业厂商**：私有化部署、云服务、一体机，商业许可证
- **aiPlat**：开源 MIT 协议，零外部依赖，Python 3.10+ 单进程，SQLite 不需要单独数据库服务。CTO 可低成本验证，无需采购审批

---

#### 四、场景选型建议

| 你需要什么 | 推荐方案 |
|-----------|---------|
| 万亿级图数据存储与高并发查询 | 海致科技 / 创邻科技 |
| LDBC 基准验证的高性能图计算 | 星环科技 |
| 成熟商业图数据库产品 | 杭州悦数 |
| **图+LLM 深度融合** | **aiPlat** |
| **轻量化、零运维部署** | **aiPlat** |
| **知识图谱自动构建** | **aiPlat** |
| **推理路径全链路可追溯** | **aiPlat** |
| **图驱动的消幻、Self-RAG** | **aiPlat** |
| 个人终端使用 | Hermes Agent |

---

#### 五、总结

aiPlat 不是一个图数据库的替代品，而是图数据库之上的 **AI 推理层**。四家厂商提供"图数据基础设施"，aiPlat 提供"图驱动的 AI 推理内核"——两者处于不同的生态位，互为补充。

理想情况下，aiPlat 可以通过 `DataSource` 连接器接入商业图数据库作为后端存储，同时保留自己的图推理和 LLM 融合层。这种组合可以实现"商业数据库的存储能力 + aiPlat 的推理能力"的最佳效果。

---

*基于 2026 年 7 月公开信息整理。各厂商产品参数可能因版本迭代而变化，具体选型请以官方信息及实际业务需求为准。如有错误欢迎指正。*


## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`commercial-value`*
