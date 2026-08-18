# PipelineEngine 拆分方案（P2-A4）

> 状态：方案（2026-08-18）· 目标：pipeline_engine.py 12281 行 → 主类 + Mixin 拆分
> 原则：**不改任何公共 API/调用语义**，纯文件结构重组（方法迁移到 Mixin 类，主类多重继承）
> 位置：research 目录（方案定稿），代码实施按 Phase 风险递增逐步进行

## 1. 现状分析

- `pipeline_engine.py` **12281 行**，`PipelineEngine` 类 **112 个方法**
- 方法间通过 `self.xxx` 互相调用（强耦合单体）
- 核心枢纽：`_run_stages_from`(9 次被调)、`_snapshot`(6)、`_healing_post_snapshot`(6)、`_exec_stage`(4)
- `__init__` 初始化 8 个实例属性（`_config`/`_model`/`_stage_runner`/`_eval_runner` 等）

## 2. 功能域聚类（拆分候选）

| 域 | 行区间 | 方法数 | 内部内聚度 | 外部依赖 | 拆分风险 |
|---|---|---|---|---|---|
| **healing**（自愈策略） | 10804-11416 | 14 | 高（互相调用多） | `_config`/`_stage_runner`/`_extract_json` | **低** ✅ |
| **state_persist**（状态持久化） | 9570-9906 | 7 | 高（snapshot 家族） | `_config`/`_output_root` | 低 ✅ |
| **prompt_parse**（prompt/解析） | 8577-9402 | 9 | 中 | 多（_build_prompt 大） | 中 |
| **eval_test**（测试评估） | 7430-8577 | 6 | 中 | `_tri_evaluate` 大 | 中 |
| **stage_dispatch**（执行分派） | 3921-6384 | 21 | 低（调用面广） | 核心枢纽 | **高** ⚠️ |
| **stage_exec**（阶段执行） | 6772-7742 | 4 | 高 | `_exec_stage` 核心 | 中 |
| **auto_pipeline**（自动流水线） | 10319-10591 | 7 | 中 | `_accept_plan_stages` | 中 |

## 3. 推荐拆分策略（风险递增，分阶段）

### Phase 1：healing Mixin（最低风险，先行验证机制）
- 新建 `execution/pipeline_healing.py`：`class PipelineHealingMixin`
- 迁移 13 个 healing 方法（`_healing_pre/post_snapshot`、`_resolve_best_strategy`、`_dispatch_strategy`、`_strategy_rotate_credential/_compress_retry/_backoff_retry/_skip_stage/_escalate`、`_inc_healing_stat`、`_meta_optimize`、`_record_strategy_outcome`、`_extract_keywords`）——562 行
- 主类改为 `class PipelineEngine(PipelineHealingMixin)`
- Mixin 依赖：`logger` + `PipelineStageConfig`（from core.schemas_builder）+ `PipelineState`（类型标注，可 lazy）
- **验证**：`_dispatch_strategy`/`_meta_optimize` 调用链不变 + 全量测试

### Phase 2：state_persist Mixin（低风险）
- 新建 `execution/pipeline_state.py`：`class PipelineStateMixin`
- 迁移 7 个状态持久化方法（`_snapshot`/`_merge_state`/`_load_checkpoints_from_disk`/`_output_root`/`_persist_files`/`_summarize_artifact` 等）

### Phase 3：prompt_parse + eval_test Mixin（中风险）
- 新建 `execution/pipeline_prompt.py`：`_build_prompt`/`_render_jinja2`/`_collect_files`/`_store_artifacts` 等 9 方法
- 新建 `execution/pipeline_eval.py`：`_tri_evaluate`/`_exec_test_runner`/`_gen_test_plan`/`_retry_loop` 等 6 方法

### Phase 4：stage_dispatch + stage_exec（高风险，最后）
- 新建 `execution/pipeline_stage.py`：执行分派（21 方法）+ 阶段执行（4 方法）
- 需仔细处理 `_run_stages_from`（9 处引用）与主类状态互访

### 目标形态
```
PipelineEngine(PipelineStageMixin, PipelineHealingMixin, PipelineStateMixin,
               PipelinePromptMixin, PipelineEvalMixin, ...)
```
主类保留：`__init__`、核心状态、`run`/`approve`/`reject`/`rollback`（生命周期 API）、模块级函数（`get_pipeline_builder` 等）

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Mixin 方法间 `self.attr` 引用断裂 | 每 Phase 迁移后跑全量宪法测试 + pipeline 相关单测 |
| import 循环（Mixin 需 PipelineConfig 等） | Mixin 文件从 `core.schemas_builder` 独立导入（与主文件同源） |
| 调用方 `from pipeline_engine import X` 断裂 | 主文件保留 `__all__`/re-export，Mixin 不改变导出 |
| `_tri_evaluate` 等巨型方法迁移后上下文丢失 | 迁移时保持方法体原样（纯剪切，不重构） |
| Mixin 访问 `self._config` 等私有属性 | 主类 `__init__` 顺序保证属性先初始化（MRO 继承链） |
| 文件间空行格式差异 | 机械提取时保持原样，仅清理行间多余空行 |

## 5. 验证标准（每 Phase）

```
1. python3 -m py_compile pipeline_engine.py + 新 Mixin 文件
2. pytest tests/constitution/test_engine_agnostic.py -q     # 引擎无关
3. pytest aiPlat-core/core/tests/unit/test_pipeline_engine_core.py -q
4. bash scripts/architecture_guard.sh --quick               # 守卫
5. grep 调用方 import 不变（grep -rn "from.*pipeline_engine import" 全仓）
6. pytest tests/constitution/test_ast_business_keys.py -q   # 业务键
```

## 6. 收益

- 主文件从 12281 → ~8000 行（Phase 1+2 后）→ ~5000 行（全部完成后）
- 每 Mixin < 1200 行，符合 §93 类大小门禁趋势
- 自愈策略/状态持久化可独立测试（模块化）
- 不改任何公共 API（零破坏性）

## 7. 实施记录

- 2026-08-18：方案定稿（本文档）。Phase 1（healing Mixin，562 行）待实施——需 workspace-write 权限做机械迁移（提取方法 → 新文件 → 主文件删除 + 继承声明）。
