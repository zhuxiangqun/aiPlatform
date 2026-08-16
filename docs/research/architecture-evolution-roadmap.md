# aiPlat 架构演进路线图（基于 §19 架构对比）

> **依据**：《aiPlat核心能力对标报告.md》§19 架构对比分析（四系统架构面 8 维度对比）+ 本仓库代码现状实测 + 既有架构文档（`docs/architecture/plans/` 的 worker-split-plan 等先例）
> **原则**：渐进式演进（参考 worker-split-plan 的"当前不拆分、触发条件驱动"哲学）；每次演进必须保留向后兼容与回退路径（CLAUDE.md §核心系统修改自检规则 5）；每阶段含代码证据、目标架构特征、任务清单、验收标准
> **目标架构愿景**：在保持"分层单体 + 治理内核 + 多服务部署"定位不变的前提下，向 DSH 的"单一真相源"与"可替换性"演进，同时消化历史耦合，最终形态 = **可治理的分层内核 + 事件可重放的状态层 + 白名单化的扩展缝**

---

## 阶段总览

```
Phase 0（基线固化）→ Phase 1（状态/事件一致性）→ Phase 2（扩展缝）→ Phase 3（耦合治理）→ Phase 4（架构验证闭环）
     1-2 周                       2-3 周                  2-3 周              3-4 周                持续
     「把现状钉住」                「向单一真相源演进」       「把扩展点白名单化」      「消化历史耦合」         「守卫/宪法/度量常态化」
```

每个 Phase 可独立交付、独立回退，不阻塞主线迭代。

---

## Phase 0：架构基线固化（1-2 周）

**目标**：把当前架构事实"钉住"——消除守卫误报、建立耦合度量基线、补齐 BOUNDARY 声明，使后续演进有可信的"前测"。

### 0.1 修正守卫自身误报（对应改进方案 P2-4）

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

### 0.2 建立耦合度量基线

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

### 0.3 BOUNDARY.yaml 补齐审计

- **现状证据**：`core/harness/BOUNDARY.yaml` 存在（layer: core + known_debt）；但 core 内其他子目录（execution/knowledge/memory/gates 等）是否都有 BOUNDARY 声明未全量核实
- **任务**：`scripts/validate_rules_paths.py` 扩展或新增检查：core 下每个一级子目录（harness 内）必须有 BOUNDARY.yaml（声明 layer + 依赖方向 + known_debt）
- **验收**：`bash scripts/architecture_guard.sh` 新增 § 检查 pass；缺 BOUNDARY 的目录被列出并补齐

---

## Phase 1：状态/事件一致性——向"单一真相源"演进（2-3 周）

**目标**：把 PipelineRunStore 的状态快照 + run_events 事件表升级为"状态由事件折叠派生"的双写模型，对齐 DSH 事件源哲学，同时保留状态查询快的优势（改进方案 P2-1 落地）。

### 1.1 run_events 写入完整性（Phase 1a）

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

### 1.2 状态折叠派生（Phase 1b）

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

## Phase 2：扩展缝白名单化（2-3 周）

**目标**：把"运行时扩展"做成受限、可审计、可回滚的白名单机制（对齐 DSH 的插件缝，但保留 aiPlat 的治理边界——DSH 自述"自修改不是安全边界"，aiPlat 必须做成安全边界）。

### 2.1 运行时 Handler 注册缝（Phase 2a）

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

### 2.2 Provider 插件化（Phase 2b，对齐 Hermes/DSH）

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

## Phase 3：耦合治理（3-4 周）

**目标**：用 Phase 0.2 的度量基线，真实降低 `avg_degree` 与"非聚合点 max_degree"（CLAUDE.md 硬指标），消化历史耦合。

### 3.1 高耦合模块优先治理

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

### 3.2 历史耦合专项（已知债务）

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

## Phase 4：架构验证闭环（持续）

**目标**：把架构事实变成"每次改动自动验证"的常态化机制。

### 4.1 守卫规则扩展

- 新增架构维度检查：
  - §: run_events 写入完整性（新增 `_exec_stage` 事件落库点存在性 grep）
  - §: 运行时 handler 注册必须走 PluginManager（禁止散落 importlib 直接加载）
  - §: provider 必须经 ModelManager 发现（禁止 core 直接扫描模型目录）
- 每条规则进 `arch_guard_rules.yaml`（数据化）+ `validate_rules_paths.py` 校验路径

### 4.2 宪法测试扩展

- `tests/constitution/` 新增：
  - `test_event_source_consistency.py`：run_events 折叠 == 状态快照（采样 run）
  - `test_runtime_handler_governed.py`：运行时 handler 必须 pending_review + audit
  - `test_coupling_ratchet.py`：avg_degree 不高于基线

### 4.3 文档同步（CLAUDE.md 强制）

- 每阶段完成同步更新：
  - `AIPLAT_CAPABILITIES.md`（新公共符号 +1 行）
  - `core/capability_registry.yaml`（新 public 符号注册）
  - `CLAUDE.md` §16 已知债务（新增/修复标注 + 验证命令）
  - `docs/architecture/plans/`（本路线图进度同步，参照 worker-split-plan 的 `last_synced` 格式）

---

## 阶段依赖与风险

| 阶段 | 依赖 | 主要风险 | 缓解 |
|---|---|---|---|
| Phase 0 | 无 | 守卫规则修改可能误放真实违规 | 规则改动必须附带新违规检测的黄金样本测试（`tests/tool_correctness/`） |
| Phase 1 | Phase 0.1（守卫可信） | 事件折叠与状态漂移 | 默认路径不变；`from_events` 显式开启；一致性校验工具报警不阻断 |
| Phase 2 | 无 | 运行时 handler 被滥用 | 白名单 + 危险 import 校验 + pending_review 审批 + 全链路审计（安全边界明确） |
| Phase 3 | Phase 0.2（度量基线） | 重构引入回归 | 每轮 3-5 模块 + constitution 测试 + E2E 回归 |
| Phase 4 | 全部 | 守卫噪音 | 黄金样本 + 基线 ratchet |

## 验收总纲（每 Phase 完成后强制）

```bash
# 1. 守卫全绿（含本路线图新增规则）
bash scripts/architecture_guard.sh
# 预期：0 ERROR 0 WARNING

# 2. 宪法测试
python3 -m pytest tests/constitution/ -q --tb=short

# 3. 耦合基线不上升
python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json

# 4. E2E 回归
python3 -m pytest aiPlat-platform/tests/test_builder.py -q --tb=short

# 5. 文档同步（CLAUDE.md 规则 5）
bash scripts/check_doc_sync.sh   # 新增符号已登记
```

---

## 与既有计划的关系

| 既有计划 | 关系 |
|---|---|
| `docs/architecture/plans/worker-split-plan.md` | 本路线图 Phase 1 的事件源双写**为未来 worker 拆分提供一致性基础**（多进程共享 run_events 单一真相源）；worker 拆分本身维持"触发条件驱动、当前不拆分"结论 |
| `docs/architecture/plans/router-migration-plan.md` | Phase 3 耦合治理沿用其迁移方法论（核心 router → 模块 router） |
| `docs/architecture/plans/optimization-roadmap.md` | 本路线图专注架构面，优化路线图专注性能面，两者互补 |
| 改进方案 `aiPlat改进方案.md` | 本路线图是改进方案 P2 部分的"架构专项展开"（P2-1/P2-2/P2-3/P2-4 在此细化到阶段与验收） |

---

## 目标架构最终形态（Phase 4 完成后）

```
┌─────────────────────────────────────────────────────────┐
│ 控制平面：管理端 Web + RBAC + 审批中心 + 诊断中心          │
│   （治理：172+ 守卫规则 + 宪法测试 + 耦合 ratchet 常态化）   │
├─────────────────────────────────────────────────────────┤
│ 门面层：CoreFacade 210+ 接口（唯一通道）                  │
├─────────────────────────────────────────────────────────┤
│ 执行平面：Syscall 封口 → Gate 链 → PipelineEngine          │
│   ├─ 状态层：PipelineRunStore（快照，查询快）              │
│   └─ 事件层：run_events 完整落库（单一真相源，可折叠/回放）  │
│   └─ 扩展缝：PluginManager 运行时 handler（白名单+审批+审计）│
│   └─ Provider 缝：ModelManager 目录插件化                 │
├─────────────────────────────────────────────────────────┤
│ 基础设施：infra（模型/存储/网络/可观测）→ core → platform   │
│   （四层单向依赖，BOUNDARY.yaml 全覆盖，avg_degree 下降）    │
└─────────────────────────────────────────────────────────┘
```

**一句话总结**：aiPlat 的架构演进不是"照搬 DSH 的一切皆插件"，而是**在保持治理内核优势的前提下，把状态层向"事件可重放"演进、把扩展点向"白名单可审计"演进、把耦合向"度量可 ratchet"演进**——最终实现"可治理的分层内核 + 事件可重放的状态层 + 白名单化的扩展缝"。
