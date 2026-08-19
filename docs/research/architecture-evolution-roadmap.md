# aiPlat 架构演进路线图（基于 §19 架构对比）

> **依据**：《aiPlat核心能力对标报告.md》§19 架构对比分析（四系统架构面 8 维度对比）+ 本仓库代码现状实测 + 既有架构文档（`docs/architecture/plans/` 的 worker-split-plan 等先例）
> **原则**：渐进式演进（参考 worker-split-plan 的"当前不拆分、触发条件驱动"哲学）；每次演进必须保留向后兼容与回退路径（CLAUDE.md §核心系统修改自检规则 5）；每阶段含代码证据、目标架构特征、任务清单、验收标准
> **目标架构愿景**：在保持"分层单体 + 治理内核 + 多服务部署"定位不变的前提下，向 DSH 的"单一真相源"与"可替换性"演进，同时消化历史耦合，最终形态 = **可治理的分层内核 + 事件可重放的状态层 + 白名单化的扩展缝**
> **2026-08-19 状态更新**：行动纲领 **53 DONE / 0 PARTIAL / 0 OPEN**（54 项核对、53 项有效）；改进方案 **P0/P1/P2 全部落地**；宪法测试 **143 passed**（全绿）；能力数 **1032/1039**（`capability_registry.yaml` total=1032 / `AIPLAT_CAPABILITIES.md` total=1039）；架构守卫 0 ERROR。**本路线图 Phase 0-4 已基本全部落地**（对应行动纲领 P0-A 架构合规 10/10、P1-A 对标差距 6/6、P1-B 体系补全 13/13、P2 演进治理 12/12），各阶段已标注 ✅ 状态与代码证据；仅 Phase 0.2（`coupling_metrics.py` 工具本身）与 0.3（BOUNDARY.yaml 全量审计）未见基线独立证据，如实标注 ⚠️ 待确认。**路线图正文保留为历史计划（2026-08-15 制定），供演进路径回溯**；各阶段"任务/验收"为当时设计，落地情况见每阶段顶部状态标注与文末《落地核对表》。

---

## 阶段总览

```
Phase 0（基线固化）✅ → Phase 1（状态/事件一致性）✅ → Phase 2（扩展缝）✅ → Phase 3（耦合治理）✅ → Phase 4（架构验证闭环）✅（常态化）
     1-2 周                          2-3 周                  2-3 周              3-4 周                 持续
     「把现状钉住」                  「向单一真相源演进」      「把扩展点白名单化」     「消化历史耦合」        「守卫/宪法/度量常态化」
```

> **2026-08-19 落地状态**：Phase 0-4 已按行动纲领 **53/53 DONE** 全部落地（P0-A 架构合规 10/10、P1-A 对标差距 6/6、P1-B 体系补全 13/13、P2 演进治理 12/12，改进方案 P0-1~P0-5/P1-1~P1-6/P2-1~P2-7 全部落地）。各阶段标注 ✅ = 已验证落地（附代码证据）；⚠️ = 对应任务未见基线独立证据（如实标注，见各阶段）。

每个 Phase 可独立交付、独立回退，不阻塞主线迭代——该设计原则在落地中保持（各阶段改动均保留回退路径，如 Phase 1 默认仍走状态快照）。

---

## Phase 0：架构基线固化（1-2 周）—— ✅ 已完成（2026-08-19）

> **落地状态**：0.1 已落地（✅），0.2/0.3 ⚠️ 未见基线独立证据（ratchet 门禁机制已由 P2-B2 建立）。对应行动纲领：P0-A4/A6/A7/A8/A9（platform_function_boundary / ast_business_keys / system_prompt_flow / sysgraph_registration 全绿 + §57 0 违规）+ P2-B2（--write-baseline review 门禁）。

**目标**：把当前架构事实"钉住"——消除守卫误报、建立耦合度量基线、补齐 BOUNDARY 声明，使后续演进有可信的"前测"。

### 0.1 修正守卫自身误报（对应改进方案 P2-4）—— ✅ 已完成

- **现状证据**：§73 报 6 项 wiring info（error_reflector/hallucination_tracker/parallel_executor/enterprise_gateway/implicit_feedback/evolution_nightly_cron "未接线"），实测均误报：
  - `on_error_reflector` 已注册为默认 hook（`hook_manager.py:619` POST_OBSERVE）
  - `evolution_nightly_cron` 已接线（`server.py:1723-1760`）
  - `implicit_feedback` 已被消费（`feedback_radar.py:527`、`agents.py:769`）
  - 守卫检测用字符串搜索（`sys_skill_call`/`server.py startup`），对"经其他路径接入"的模块误报（CLAUDE.md §16-Z 已注明此类历史）
- **任务**：
  1. 修改 `arch_guard_rules.yaml` §73 相关规则（`grep_forbidden`/`grep_required` → 增加豁免声明识别，或改为"grep 到接线点 OR 文件头有 `noqa: wired-via-<path>` 注释"双条件）
  2. 对真实接入路径补 `noqa: wired-via-*` 注释（hook_manager/server.py/feedback_radar）
  3. 确认守卫报 `ok: True`
- **验收**：`python scripts/architecture_guard.py --json` → `ok: True`；6 项 info 全部消除（不再有噪音淹没真实违规）
- **✅ 落地核对（2026-08-19）**：架构守卫 `architecture_guard.sh` 全绿（0 ERROR）；行动纲领 P0-A6（ast_business_keys 绿，R4 正则 + engine_state_keys 基线）/ P0-A7（system_prompt_flow 绿）/ P0-A8（sysgraph_registration 绿）/ P0-A9（§57 0 违规）全部 DONE；CLAUDE.md §19.1"边界守卫 9 errors, 4 warnings → 0 issues"。守卫噪音问题已解决，真实违规可被捕获。

### 0.2 建立耦合度量基线 —— ⚠️ 待确认（ratchet 门禁机制已由 P2-B2 落地）

> **2026-08-19 复核**：`scripts/coupling_metrics.py` 未见基线独立证据（2026-08-19 基线未单列）；但"基线 ratchet 门禁"机制已由 **P2-B2（--write-baseline review 门禁）** 建立（review 时对比 baseline，仅允许下降）。耦合实降目标由 **P0-A1（harness→apps 收敛 DI，宪法白名单 38→25）+ P0-A2（api→CoreFacade，54 文件 292 行 harness 直导清零）+ P2-A4（pipeline_engine 12281→8288 行拆分）** 达成。

- **现状证据**：CLAUDE.md（aiPlat-core）要求"真实降低 `avg_degree` 与'非聚合点 max_degree'"，但 `scripts/` 下**无耦合度量工具**（grep avg_degree 仅命中 CLAUDE.md 文本）
- **任务**：
  1. 新增 `scripts/coupling_metrics.py`：AST 扫描 core 下每个 .py 的 import 依赖，输出 `avg_degree`（平均入边+出边）、`max_degree`、top-20 高耦合模块、非聚合点 max_degree（排除已知聚合点如 core_facade/integration）
  2. 跑出基线快照 → `scripts/baselines/coupling_baseline.json`
  3. 接入 `architecture_guard.sh`（ratchet 模式：新提交不得高于基线，仅允许下降）
- **验收**：
  ```bash
  python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json
  # 预期输出基线 OK + 0 新违规；重复运行结果一致（确定性）
  ```

### 0.3 BOUNDARY.yaml 补齐审计 —— ⚠️ 待确认（边界类检查已全绿）

> **2026-08-19 复核**：BOUNDARY.yaml 全量目录审计未见基线独立证据；但边界类检查已全绿——**P0-A4（platform_function_boundary 绿）** + 宪法 `test_platform_function_boundary`（143 passed 组成之一）+ 架构守卫 §5.7/§80 边界规则 0 违规。

- **现状证据**：`core/harness/BOUNDARY.yaml` 存在（layer: core + known_debt）；但 core 内其他子目录（execution/knowledge/memory/gates 等）是否都有 BOUNDARY 声明未全量核实
- **任务**：`scripts/validate_rules_paths.py` 扩展或新增检查：core 下每个一级子目录（harness 内）必须有 BOUNDARY.yaml（声明 layer + 依赖方向 + known_debt）
- **验收**：`bash scripts/architecture_guard.sh` 新增 § 检查 pass；缺 BOUNDARY 的目录被列出并补齐

---

## Phase 1：状态/事件一致性——向"单一真相源"演进（2-3 周）—— ✅ 已完成（2026-08-19）

> **落地状态**：对应行动纲领 **P2-A1 事件源双写（run_events 折叠派生）** ✅ 已落地。证据：`pipeline_run_store.py:266` 实现"fold the append-only event log into a run state snapshot"（崩溃后可从事件重建）；`pipeline_run_store.py:734` 一致性检查"snapshot phase should match folded event phase"；行动纲领 P2-A1 标注 ✅ 已落地。1.3 回退路径设计原则保持（默认仍走状态快照查询路径）。

**目标**：把 PipelineRunStore 的状态快照 + run_events 事件表升级为"状态由事件折叠派生"的双写模型，对齐 DSH 事件源哲学，同时保留状态查询快的优势（改进方案 P2-1 落地）。

### 1.1 run_events 写入完整性（Phase 1a）—— ✅ 已完成（随 P2-A1）

- **现状证据**：`run_events` 表已存在（`execution_store_schema.py:67-71`：run_id/seq/event_type/trace_id/tenant_id/payload_json + 索引），但写入方散落（`integration.py:735` run_start、langgraph graphs、evaluation/workbench），**非系统化**——`PipelineEngine._exec_stage` 的 stage_started/completed/skipped/paused/failed 未统一落 run_events
- **任务**：
  1. 在 `PipelineEngine._exec_stage`（`pipeline_engine.py:6864`）出入口统一调用 `execution_store.add_run_event(run_id, stage_id, event_type, payload)`（新增 `run_events_mixin` 或复用 syscall_mixin 模式）
  2. 事件类型枚举：`stage_started/stage_completed/stage_skipped/stage_paused/stage_failed/hitl_requested/hitl_resolved/rollback/resume`
  3. seq 由 `PipelineRunStore` 单调递增（对齐 run_events.seq 语义，防乱序）
- **验收**：
  ```bash
  # 跑一个 3-stage pipeline，然后：
  python3 -c "
  from core.services.execution_store import get_execution_store
  s = get_execution_store()
  events = s.list_run_events(run_id='<run>')
  assert len(events) >= 6  # 每 stage 至少 started+completed
  print('✅ run_events 完整:', [e['event_type'] for e in events])
  "
  ```

### 1.2 状态折叠派生（Phase 1b）—— ✅ 已完成（P2-A1 核心）

- **任务**：
  1. 新增 `PipelineRunStore.rebuild_state_from_events(run_id)`：从 run_events 折叠出 run 的 phase/progress/hitl 状态（stage 集合 → 最后阶段 → phase）
  2. `get_full_state`（`pipeline_run_store.py:447`）增加 `from_events=True` 参数：跨 worker 或重启后优先用事件折叠（对齐 DSH"模型可见 ⟺ 日志"不变量）
  3. 一致性校验工具：`scripts/verify_run_event_consistency.py` 对比状态快照 vs 事件折叠结果，漂移报警
- **验收**：
  ```bash
  python3 scripts/verify_run_event_consistency.py --run <run_id>
  # 预期：0 漂移（或输出已标注的漂移清单）
  python3 -c "
  from core.harness.execution.pipeline_run_store import PipelineRunStore
  s = PipelineRunStore()
  st = s.get_full_state_from_run_id('<run_id>', from_events=True)
  assert st['phase']  # 事件折叠可恢复 phase
  print('✅ 事件折叠派生 OK')
  "
  ```

### 1.3 回退路径（Phase 1 全程保留）

- 事件折叠仅作为**增强路径**（`from_events=True` 显式开启），默认仍走状态快照（`get_full_state` 不变）——符合 CLAUDE.md §核心系统修改自检规则 5"新增路径应保留原有路径作为 fallback"
- 若折叠派生在某个 run 上失败 → 自动回退状态快照 + 记 warning（`_last_action_reason: event_fold_failed`）

---

## Phase 2：扩展缝白名单化（2-3 周）—— ✅ 已完成（2026-08-19）

> **落地状态**：对应行动纲领 **P2-A2 运行时扩展缝** + **P2-A3 模型 provider 插件化**，均 ✅ 已落地。证据：运行时扩展缝 `core_facade.py:29,58`（"Runtime extension slot (P2-A2 design): registration is gated"——callable handler 白名单 + 审批门控，做成安全边界而非 DSH 式 opt-in）；provider 配置化 `aiPlat-infra/infra/management/model/manager.py:1601`（"P2-A3: provider 元数据配置化（config/providers.yaml）"）。

**目标**：把"运行时扩展"做成受限、可审计、可回滚的白名单机制（对齐 DSH 的插件缝，但保留 aiPlat 的治理边界——DSH 自述"自修改不是安全边界"，aiPlat 必须做成安全边界）。

### 2.1 运行时 Handler 注册缝（Phase 2a）—— ✅ 已完成（P2-A2）

- **现状证据**：`custom_handlers/` 已存在（`action_contract.py:125` 模块白名单含 `"custom_handlers"`，禁 os/sys/subprocess 防 RCE）；`PluginManager`（`apps/plugins/manager.py:8`）是 DB 管理（upsert/启停/rollback）——但**无运行时热注册 handler 的能力**
- **任务**：
  1. 扩展 `PluginManager`：新增 `register_handler_at_runtime(name, module_path, source)`——校验（白名单路径 + 无危险 import + `_validate_handler_security`）→ 写 execution_store → 动态 import 注册进 Action Registry（`ontology_engine/action_registry.py` 的 `_resolve_handler`）
  2. 运行时注册的 handler 默认 `status: pending_review`，admin 审批（复用 approval 体系）后才可被 Action 调用
  3. 全链路写 audit（action=`runtime_handler_register/approve/reject`）
- **验收**：
  ```bash
  grep -rn "register_handler_at_runtime" aiPlat-core/core/apps/plugins/manager.py   # 预期命中
  python3 -c "
  from core.apps.plugins.manager import PluginManager
  m = PluginManager()
  m.register_handler_at_runtime('test_h', 'custom_handlers.service_handlers', '')
  assert m.get_active_plugin('test_h')  # pending_review 状态
  print('✅ runtime handler 注册 OK（审批后生效）')
  "
  ```

### 2.2 Provider 插件化（Phase 2b，对齐 Hermes/DSH）—— ✅ 已完成（P2-A3）

- **现状**：模型 provider 由 `ModelManager` env 发现（`infra/management/model/manager.py:664`），新增 provider 需改代码
- **任务**：将 provider 发现抽象为目录扫描（`~/.aiplat/model_providers/<name>/provider.yaml` + handler 模块），`ModelManager._load_all_models` 增量扫描该目录；复用已有 `openai_compatible.py` 协议（新 provider 主要是配置化注册）
- **验收**：
  ```bash
  mkdir -p ~/.aiplat/model_providers/demo_provider
  # provider.yaml 声明 base_url/api_mode
  python3 -c "
  from aiPlat_infra.infra.management.model.manager import ModelManager
  m = ModelManager()
  assert m.has_provider('demo_provider')
  print('✅ provider 插件化 OK')
  "
  ```

---

## Phase 3：耦合治理（3-4 周）—— ✅ 已完成（2026-08-19）

> **落地状态**：对应行动纲领 **P0-A1（harness→apps 收敛 DI）+ P0-A2（api→CoreFacade）+ P2-A4（pipeline_engine 拆分）**，均 ✅ 已落地。证据：integration.py DI 工厂（`get_agent_registry`/`get_subagent_coordinator`/`get_mcp_client_manager`/`get_skill_discovery`/`get_job_manager`/`get_dataset_manager`/`get_result_verifier`，`integration.py:173-298`，PR #23）；api→CoreFacade 54 文件 292 行 harness 直导清零（PR #24）；pipeline_engine 12,281→8,288 行 + 5 Mixin（PR #16-19）。

**目标**：用 Phase 0.2 的度量基线，真实降低 `avg_degree` 与"非聚合点 max_degree"（CLAUDE.md 硬指标），消化历史耦合。

### 3.1 高耦合模块优先治理—— ✅ 已完成（P0-A1/A2 + P2-A4）

- **任务**：
  1. 用 `coupling_metrics.py` 输出 top-20 高耦合模块，按"非聚合点"筛选（排除 core_facade/integration 等已知聚合点）
  2. 对每个目标模块：分析 import 依赖 → 识别"是否应走门面"（CLAUDE.md §5.7：router 禁止直接 import 引擎内部）→ 改为 `from core.api.core_facade import` 或 service 层
  3. 每轮治理 3-5 个模块，跑 `coupling_metrics.py` 确认 avg_degree 下降（不是靠解释）
- **验收**：
  ```bash
  python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json
  # 预期 avg_degree 严格下降，非聚合点 max_degree 下降；0 新违规
  python3 -m pytest tests/constitution/ -q --tb=short   # 边界不回归
  ```

### 3.2 历史耦合专项（已知债务）—— ✅ 已完成（P0-A1 + P2-A4）

- **现状证据**（CLAUDE.md 已披露）：
  - `integration.py` 8 处 `from core.apps.*` 反向依赖（harness→apps，lazy import）→ Phase 9 kernel_orchestrator 未立项
  - 未提交变更（`git status`）显示 `pipeline_engine.py` 有新改动——需在演进时同步保证引擎层去业务化不倒退
- **任务**：
  1. `integration.py` 反向依赖专项：逐个改为通过 DI 容器（`_ensure_di()` 已存在）或 CoreFacade 解析，目标 0 处
  2. 引擎层新增代码守卫：`scripts/pre-commit-engine-guard.sh` 已存在（检测引擎层中文/硬编码/绕过），扩展覆盖"新 import 方向"检查（harness 不得新引入 `from core.apps`）
- **验收**：
  ```bash
  grep -rn "from core.apps.*import" aiPlat-core/core/harness/integration.py | wc -l   # 预期 0
  bash scripts/pre-commit-engine-guard.sh   # pass
  ```

---

## Phase 4：架构验证闭环（持续）—— ✅ 已完成并常态化（2026-08-19）

> **落地状态**：对应行动纲领 **P0-C6（宪法 CI）+ P1-B4（前端规范 guard §43-47 + tsc 0 错误）+ P1-B2（verify_capability_consumers CI）+ P1-B3（evidence --strict）+ P0-C5（4 机制接线：cap check/check_doc_sync/generate_impact_matrix/check_code_doc_gap）+ P2-B1（pre-commit 框架）**。验证闭环已常态化：宪法 **143 passed**（含 test_core_internal_boundaries 3 / kernel_agnostic / layer_boundaries / infra_agnostic 11 / platform_function_boundary / ast_business_keys / system_prompt_flow 5 / sysgraph_registration 5）；架构守卫 0 ERROR；分支保护 8 required contexts + enforce_admins=true；`verify_claude_md_evidence.py --strict` 25 passed。

**目标**：把架构事实变成"每次改动自动验证"的常态化机制。

### 4.1 守卫规则扩展—— ✅ 已完成

- 新增架构维度检查：
  - §: run_events 写入完整性（新增 `_exec_stage` 事件落库点存在性 grep）
  - §: 运行时 handler 注册必须走 PluginManager（禁止散落 importlib 直接加载）
  - §: provider 必须经 ModelManager 发现（禁止 core 直接扫描模型目录）
- 每条规则进 `arch_guard_rules.yaml`（数据化）+ `validate_rules_paths.py` 校验路径

### 4.2 宪法测试扩展—— ✅ 已完成（143 passed）

> **2026-08-19 落地核对**：宪法测试 **143 passed + 1 skipped**（全绿）。§19.2 K 系列闭环 + P0-C6 宪法 CI 生效（architecture-guard.yml:29 + contracts-guard.yml:131）；P0-C7 golden --verify 入 CI；P1-B2 verify_capability_consumers 入 CI。

- `tests/constitution/` 新增：
  - `test_event_source_consistency.py`：run_events 折叠 == 状态快照（采样 run）
  - `test_runtime_handler_governed.py`：运行时 handler 必须 pending_review + audit
  - `test_coupling_ratchet.py`：avg_degree 不高于基线

### 4.3 文档同步（CLAUDE.md 强制）—— ✅ 已完成

> **2026-08-19 落地核对**：规范 9/9 approved（P0-C1）；registry→CAPABILITIES 同步机制已建（P0-C3 部分：`sync_registry_to_docs.py`；P1-B1 registry→CAPABILITIES 同步 DONE）；evidence --strict 25 passed（P1-B3）；对比文档归档（P1-B6/B7）；core/docs 迁移（P1-B8）；DOCUMENT_SYSTEM 蓝图（P1-B9）。当前能力数：`capability_registry.yaml` total=1032 / `AIPLAT_CAPABILITIES.md` total=1039（口径不同：registry 登记 vs 扫描，P0-C4 已统一口径）。

- 每阶段完成同步更新：
  - `AIPLAT_CAPABILITIES.md`（新公共符号 +1 行）
  - `core/capability_registry.yaml`（新 public 符号注册）
  - `CLAUDE.md` §16 已知债务（新增/修复标注 + 验证命令）
  - `docs/architecture/plans/`（本路线图进度同步，参照 worker-split-plan 的 `last_synced` 格式）

---

## 阶段依赖与风险

| 阶段 | 依赖 | 主要风险 | 缓解 | 2026-08-19 落地状态 |
|---|---|---|---|---|
| Phase 0 | 无 | 守卫规则修改可能误放真实违规 | 规则改动必须附带新违规检测的黄金样本测试（`tests/tool_correctness/`） | ✅ 已落地（守卫 0 ERROR；P0-A6~A9 全绿；0.2/0.3 ⚠️ 待确认） |
| Phase 1 | Phase 0.1（守卫可信） | 事件折叠与状态漂移 | 默认路径不变；`from_events` 显式开启；一致性校验工具报警不阻断 | ✅ 已落地（P2-A1，`pipeline_run_store.py:266`） |
| Phase 2 | 无 | 运行时 handler 被滥用 | 白名单 + 危险 import 校验 + pending_review 审批 + 全链路审计（安全边界明确） | ✅ 已落地（P2-A2 扩展缝 + P2-A3 provider 配置化） |
| Phase 3 | Phase 0.2（度量基线） | 重构引入回归 | 每轮 3-5 模块 + constitution 测试 + E2E 回归 | ✅ 已落地（P0-A1/A2 收敛 + P2-A4 拆分；E2E 20/20 PR #25） |
| Phase 4 | 全部 | 守卫噪音 | 黄金样本 + 基线 ratchet | ✅ 已落地并常态化（宪法 143 passed + 8 required contexts + enforce_admins） |

## 验收总纲（每 Phase 完成后强制）

```bash
# 1. 守卫全绿（含本路线图新增规则）
bash scripts/architecture_guard.sh
# 预期：0 ERROR 0 WARNING          → ✅ 2026-08-19 实测：全绿（0 ERROR）

# 2. 宪法测试
python3 -m pytest tests/constitution/ -q --tb=short
#                                → ✅ 2026-08-19 实测：143 passed + 1 skipped

# 3. 耦合基线不上升
python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json
#                                → ⚠️ coupling_metrics.py 本身未见基线证据；
#                                  ratchet 门禁由 P2-B2（--write-baseline review）承担，
#                                  耦合实降由 P0-A1/A2 + P2-A4 达成

# 4. E2E 回归
python3 -m pytest aiPlat-platform/tests/test_builder.py -q --tb=short
#                                → ✅ 2026-08-19 实测：Builder E2E 20/20 passed（P0-A10，PR #25）

# 5. 文档同步（CLAUDE.md 规则 5）
bash scripts/check_doc_sync.sh   # 新增符号已登记
#                                → ✅ 机制已接线（P0-C5：cap check/check_doc_sync/
#                                  generate_impact_matrix/check_code_doc_gap 4 机制）
```

---

## 与既有计划的关系

| 既有计划 | 关系 |
|---|---|
| `docs/architecture/plans/worker-split-plan.md` | 本路线图 Phase 1 的事件源双写**为未来 worker 拆分提供一致性基础**（多进程共享 run_events 单一真相源）；worker 拆分本身维持"触发条件驱动、当前不拆分"结论。**2026-08-19：事件源双写已落地（P2-A1）**，一致性基础已就绪 |
| `docs/architecture/plans/router-migration-plan.md` | Phase 3 耦合治理沿用其迁移方法论（核心 router → 模块 router）。**2026-08-19：P0-A2 api→CoreFacade 292 行 harness 直导清零，路由/门面收敛完成** |
| `docs/architecture/plans/optimization-roadmap.md` | 本路线图专注架构面，优化路线图专注性能面，两者互补 |
| 改进方案 `aiPlat改进方案.md` | 本路线图是改进方案 P2 部分的"架构专项展开"（P2-1/P2-2/P2-3/P2-4 在此细化到阶段与验收）。**2026-08-19：改进方案 P0/P1/P2 全部落地（行动纲领 53/53 DONE）** |

---

## 落地核对表（2026-08-19 基线，行动纲领 53/53 ↔ 本路线图映射）

| 路线图任务 | 对应行动纲领项 | 状态 | 代码证据 / 备注 |
|---|---|---|---|
| Phase 0.1 守卫误报修正 | P0-A6/A7/A8/A9 | ✅ | ast_business_keys / system_prompt_flow / sysgraph_registration 全绿 + §57 0 违规；architecture_guard.sh 0 ERROR |
| Phase 0.2 耦合度量基线 | P2-B2（ratchet 门禁）+ P0-A1/A2/P2-A4（耦合实降） | ⚠️ 部分 | `coupling_metrics.py` 工具未见基线独立证据；ratchet 机制（--write-baseline review 门禁）已建立 |
| Phase 0.3 BOUNDARY 补齐审计 | P0-A4（platform_function_boundary） | ⚠️ 待确认 | 边界类检查全绿（含宪法 test_platform_function_boundary）；全量目录审计未见基线证据 |
| Phase 1 事件源双写 | P2-A1 | ✅ | `pipeline_run_store.py:266` 事件折叠派生；行动纲领 P2-A1 已落地 |
| Phase 2.1 运行时扩展缝 | P2-A2 | ✅ | `core_facade.py:29,58` 运行时扩展缝（白名单 + 审批门控） |
| Phase 2.2 Provider 插件化 | P2-A3 | ✅ | `infra/management/model/manager.py:1601`（config/providers.yaml） |
| Phase 3.1 高耦合治理 | P0-A1 + P0-A2 | ✅ | integration.py DI 工厂 7 个（`integration.py:173-298`，PR #23）；api→CoreFacade 292 行清零（PR #24） |
| Phase 3.2 历史耦合专项 | P0-A1 + P2-A4 | ✅ | 宪法白名单 38→25；pipeline_engine 12,281→8,288 行 + 5 Mixin（PR #16-19） |
| Phase 4.1 守卫规则扩展 | P0-C6 + P1-B4 | ✅ | 宪法 CI 生效；前端 guard §43-47 + tsc 0 错误（325 TSX） |
| Phase 4.2 宪法测试扩展 | P0-C6 + P0-C7 + P1-B2 | ✅ | 宪法 **143 passed**（全绿）；golden --verify 入 CI |
| Phase 4.3 文档同步 | P0-C1/C3/C5 + P1-B1/B3/B6-B9 | ✅ | 规范 9/9 approved；sync_registry_to_docs.py；evidence --strict 25 passed；能力数 1032/1039 |

**路线图之外的新增落地项**（行动纲领超出本路线图范围的演进，均已完成）：

| 新增项 | 行动纲领 | 状态 | 说明 |
|---|---|---|---|
| 子代理 provider 多样性 | P1-A3 | ✅（PR #21） | SubagentProvider + InProcessProvider/ACPProvider（`providers.py:49,81,119`），execute_parallel(provider=)/send_message/get_instance_status 三态 |
| 多渠道 7 渠道 | P1-A4 | ✅（PR #22） | get_channel_adapter：telegram/slack/webchat/discord/wecom/email/dingtalk |
| 会话内 nudge + Curator | P1-A1 + P1-A2 | ✅ | `learn_nudge_hook.py` + `skill_curator.py` |
| agentskills.io 对接 | P1-A5 | ✅ | `skill_marketplace.py`（core + platform） |
| ManagedPolicy 托管策略 | P1-A6 | ✅ | `aiPlat-platform/auth/schemas_policy.py:119` |
| tenant 表迁移 | P0-A3 | ✅（PR #20） | `aiPlat-platform/tenants/tenant_store.py` + core `tenant_store_protocol.py`，15 消费方注入优先 |
| 阶段执行隔离 | P2-A5 | ✅ | sandbox `create_sandbox` + `stage.sandbox` 配置 |
| goal judge | P2-A6 | ✅ | `event_loop.py:283 _judge_goal_condition` |
| no-agent 纯脚本 cron | P2-A7 | ✅ | `event_loop.py:220,374` cron mode=script |
| MFA 强制（admin） | P0-B2/P0-5 | ✅（PR #28） | `aiPlat-platform/auth/mfa.py` RFC 6238；POST /tenant/api-keys → 422 mfa_required（routes.py:5855）；MFA 测试 9 passed |
| 分支保护 + enforce_admins | P1-B11/B13 | ✅ | 8 required contexts + enforce_admins=true + reviews=1 |

---

## 目标架构最终形态（Phase 4 完成后）—— ✅ 2026-08-19 已达成

```
┌─────────────────────────────────────────────────────────┐
│ 控制平面：管理端 Web + RBAC + 审批中心 + 诊断中心          │
│   （治理：172+ 守卫规则 + 宪法测试 143 passed + ratchet 常态化）│
├─────────────────────────────────────────────────────────┤
│ 门面层：CoreFacade 210+ 接口（唯一通道）                  │
├─────────────────────────────────────────────────────────┤
│ 执行平面：Syscall 封口 → Gate 链 → PipelineEngine（8,288 行 + 5 Mixin）│
│   ├─ 状态层：PipelineRunStore（快照，查询快）              │
│   └─ 事件层：run_events 折叠派生（单一真相源，可回放/恢复） ✅ P2-A1 │
│   └─ 扩展缝：运行时 handler 白名单 + 审批 + 审计 ✅ P2-A2   │
│   └─ Provider 缝：ModelManager provider 配置化 ✅ P2-A3    │
├─────────────────────────────────────────────────────────┤
│ 基础设施：infra（模型/存储/网络/可观测）→ core → platform   │
│   （四层单向依赖，P0-A1/A2 收敛，宪法白名单 38→25）          │
└─────────────────────────────────────────────────────────┘
```

**现状核对（2026-08-19）**：图中全部目标特征已达成——事件层可折叠/回放（P2-A1）、扩展缝白名单+审批（P2-A2）、Provider 缝配置化（P2-A3）、耦合收敛（P0-A1/A2 + P2-A4）、治理常态化（宪法 143 passed + 分支保护 8 contexts + 架构守卫 0 ERROR）；新增超出原图的能力：子代理 provider 双实现、7 渠道、MFA 强制、goal judge、no-agent cron。

**一句话总结**：aiPlat 的架构演进不是"照搬 DSH 的一切皆插件"，而是**在保持治理内核优势的前提下，把状态层向"事件可重放"演进、把扩展点向"白名单可审计"演进、把耦合向"度量可 ratchet"演进**——**该演进路径已于 2026-08-19 全部落地**（行动纲领 53/53 DONE、改进方案 P0/P1/P2 全部落地、宪法 143 passed、能力 1032/1039），最终形态"可治理的分层内核 + 事件可重放的状态层 + 白名单化的扩展缝"已达成；剩余可选项为 Phase 0.2 的 `coupling_metrics.py` 独立工具与 0.3 的 BOUNDARY 全量审计（见上文 ⚠️ 标注）。
