# infra LLM 自动选择策略审计报告（2026-08-19 修复后现状）

> **对象**：aiPlat-infra 模型选择策略（`infra/management/model/manager.py` + `llm_profile.yaml`）+ core 消费链（`model_injection.py`）。
> **方法**：全链路代码阅读 + 本机实测（无 env / 有 env 两场景），每条结论附 `文件:行号` 证据与验证命令。
> **阶段**：① 审计（发现 2 P0 + 4 P1/P2）→ ② 修复 6 项（PR #41）→ ③ 用户决策简化（去 env + 删死代码，PR #42）。
> **现状结论**：策略框架（purpose 需求驱动 + 资源感知 + 降级链 + safe 保底 + **自我学习闭环**）正确且完整；原 8 项问题 **7 项已修复**（P0-1/P0-2/P1-3/P1-4/P1-5/P2-6/P2-7），遗留项（P2-8/探索/business_score）**已全部闭环**；模型选择已**完全基于 infra 注册表**（无 env 干预）。

---

## 1. 现状：选择链路（三层职责，单一 v3 评分）

```
选型层（唯一策略）
core best_model_for_purpose (model_injection.py:1552)
  └─ Step 0: session override → Step 0.5: tts/stt 捷径
  └─ Step 1: unified_pipeline (manager.py:1265) ← v3 评分
       ├─ hard filter (_hard_filter:206): enabled/尺寸/RAM/VRAM/磁盘
       ├─ soft filter 降级链: full → -cap → -cap-hlt → none
       ├─ _score_model 15 项评分 (:425) ← 符号已修复（latency/cost × abs(weight)）
       └─ safe_model 保底: 存在性校验 + RAM 校验 → RuntimeError

候选列表层（供执行层容错）
select_by_purpose_list (manager.py:1101) ← 与 unified_pipeline 同源 v3 评分（P1-5 收敛）
  ├─ capability/资源硬过滤 → _score_model 排序
  └─ 空候选 → fallback.safe_model 存在性校验（P0-2 修复，无 phantom 模型）

执行容错层（活跃，3 个生产调用者）
generate_with_fallback (model_injection.py:1001) ← 候选纯 infra 评分，无 env 覆盖
  └─ top1 超时 → top2 自动切换 + _record_success/_record_failure 回写学习

已删除：create_adapter_with_fallback（0 caller 死代码，被 generate_with_fallback 取代）
env 解析（保留，非选择干预）：get_default_model (manager.py:1013) ← env_model_map 配置化 + 存在性校验
```

---

## 2. 问题清单与修复状态

### 2.1 已修复（7 项，均附代码证据）

| # | 原问题 | 修复 | 证据 | 状态 |
|---|---|---|---|---|
| **P0-1** | v3 评分延迟/成本惩罚**符号反转**：`-20 × (-2.5) = +50` 奖励高延迟 API 模型 | 3 处改 `penalty × abs(weight)`：chat API 延迟 **-50**、高延迟历史 **-40**、高成本 **-10**（均负分） | `manager.py:514,562,574-575`；单测 `test_latency_penalty_negative`/`test_cost_penalty_negative` | ✅ **PR #41** |
| **P0-2** | `select_by_purpose_list` 空候选返回**注册表不存在的模型**（硬编码 `deepseek-chat`） | fallback 改读 `fallback.safe_model` + `_find_model_by_name` 存在性校验；空注册表实测 `[]`（原 `['deepseek-chat']`） | `manager.py:1215`；单测 `test_empty_registry_returns_empty`/`test_fallback_returned_only_when_registered` | ✅ **PR #41** |
| **P1-3** | `fallback.ultimate_model` 配置缺失 → 配置-代码漂移 | 消除 `ultimate_model` 引用（改 `safe_model`），无硬编码模型名 | `manager.py:1079-1082`；单测 `test_no_hardcoded_deepseek_chat` | ✅ **PR #41** |
| **P1-4** | `get_default_model` 只读 env 不校验模型有效性 | 返回前 `_find_model_by_name` + `enabled` 校验，无效 → WARNING + 返回空（实测 `ghost-model → ''`） | `manager.py:1060-1068`；单测 3 个（不在注册表/禁用/有效） | ✅ **PR #41** |
| **P1-5** | **双轨评分并存**（v2 自研打分 vs v3 `_score_model`，结果分叉） | `select_by_purpose_list` 删除 v2 打分块（~90 行），排序统一 `_score_model` | `manager.py:1146-1159`（统一调用）；与 unified_pipeline 同源 | ✅ **PR #41** |
| **P2-6** | purpose 枚举两处注册（yaml `purpose_profiles` vs 代码 `purpose_env_map`） | `llm_profile.yaml` 新增 `env_model_map`（配置驱动），`get_default_model` 优先读它，内置 map 保留 fallback | `llm_profile.yaml:85`；`manager.py:1035-1052`；单测 `test_env_model_map_from_yaml` | ✅ **PR #41** |
| **P2-7** | `select()` 无条件 local-first（无质量门） | 复用 `_within_quality_band`（与 unified_pipeline #15 同门）；无质量数据时 API 优先 | `manager.py:1419-1432`；单测 `test_api_preferred_without_quality_data` | ✅ **PR #41** |

### 2.2 用户决策简化（PR #42：LLM 全在 infra 注册表，不使用 env）

| 变更 | 内容 | 验证 |
|---|---|---|
| 删除 `create_adapter_with_fallback` | 0 生产 caller 死代码（-84 行） | `grep -c` → 0 |
| `generate_with_fallback` 去 env 覆盖 | 候选纯 `select_by_purpose_list`（infra 评分），删除 `AIPLAT_{purpose}_MODEL` 段 | `model_injection.py:1048`；3 个生产调用者不受影响 |
| `_build_preferences` 去 env 偏好 | 仅 YAML `model_overrides`；docstring 同步 | `model_injection.py:1537` |
| 顺手修复 `pipeline_state.py` | 存量缺 `import logging`（checkpoint OSError 路径 NameError） | `test_builder_pipeline_e2e` 5 passed |

**保留（非选择干预）**：`get_default_model` 的 env 解析（P1-4 已校验，env 未设返回空、无副作用）；`create_selected_adapter` 的 `AIPLAT_LLM_MODEL` 兼容兜底（显式传 model_name 不受影响）。

### 2.3 遗留项处理（2026-08-19 全部闭环）

| # | 原问题 | 处理 | 证据 |
|---|---|---|---|
| P2-8 | 降级到 `-cap-hlt` 层时 health 过滤被去掉 | ✅ **已处理**：降级日志补充被 health 排除的候选明细（模型名 + 失败率>50% 标记），放宽可观测 | `manager.py` 降级循环（_health_bad detail） |
| — | 学习探索信号弱（冷启动仅 +2 分） | ✅ **已处理**：冷启动加分配置化（`model_exploration.cold_bonus/cold_threshold`）+ 可选 epsilon-greedy（`explore_epsilon`，默认 0.0 稳定优先不变）；单测 3 个 | `llm_profile.yaml` model_exploration 节；`manager.py` _calculate_dynamic_boost + unified_pipeline |
| — | `business_score` 写入侧未确认 | ✅ **已确认**：完整闭环——pipeline_runs 昨日 pass_rate → `kpi_tracker.py:68`（cron 触发）→ `set_business_score` → health store → `_calculate_dynamic_boost` biz | `kpi_tracker.py:45-68`、`scheduler/cron.py:401`、`model_health_store.py:175` |

---

## 3. 自我学习能力（完整闭环实证）

**有**——运行时结果回写 → 下次评分自适应：

| 信号 | 写入侧 | 消费侧 |
|---|---|---|
| 健康（成功/失败/延迟） | `_record_success`/`_record_failure`（`generate_with_fallback` 成功/超时/异常分支）→ ModelHealthStore | `_score_model` #14 dynamic boost（成功率+15/失败率-15/延迟-10）+ `_filter_health`（>50% 失败率丢弃）+ #15 quality-gated local |
| 质量 | `_record_quality_and_metrics_async` → QualityValidator.validate（ontology/chat/clarify 3 验证器）→ `get_quality_tracker().update`（EWMA α=0.3） | `_score_model` #10（-80~+80） |
| 延迟 | `record_latency` → LatencyTracker p95 + congestion | `_score_model` #11 + 拥塞惩罚 |
| 短期失败记忆 | `_FAILURE_TRACKER`（3 次/5 分钟） | `_is_model_degraded` 跳过 |

**边界**：① 是**选择策略自适应**（非模型权重训练）——符合 infra 层职责；② 冷启动模型 calls<5 有 +2 探索分（稳定优先，无 epsilon-greedy）；③ 学习依赖 `generate_with_fallback` 执行路径（被调用的模型才产生学习信号）。

---

## 4. 验证命令（修复后回归）

```bash
# 符号修复回归
cd aiPlat-infra && python3 -c "
from infra.management.model.manager import _get_scoring_weights
import yaml
cfg = yaml.safe_load(open('config/infra/llm_profile.yaml'))
print(-20 * abs(_get_scoring_weights('chat', cfg)['latency']))  # -50.0（修复前 +50）
"
# fallback 校验回归
cd aiPlat-infra && python3 -c "
import asyncio
from infra.management.model.manager import ModelManager
async def m():
    mgr = ModelManager(); await mgr.list_models()
    print(mgr.select_by_purpose_list('chat'))  # []（修复前 ['deepseek-chat']）
asyncio.run(m())
"
# 全量单测
cd aiPlat-infra && python3 -m pytest infra/tests/unit/test_model_selection.py -q  # 11 passed
# 死代码确认
grep -c "create_adapter_with_fallback" aiPlat-core/core/harness/utils/model_injection.py  # 0
```

---

## 5. 可信度

- 全部结论为**源码级阳性证据**（`文件:行号`）+ 本机实测输出；无阴性推断。
- P0-1/P0-2 修复前后均实测复现（+50→-50、phantom 模型→[]、ghost-model→''）；P1/P2 为代码级修复 + 单测断言。
- 契约同步：run spec 二十二轮、boundary 契约、acceptance 1.28（contracts-guard 三 binding 全绿）。
