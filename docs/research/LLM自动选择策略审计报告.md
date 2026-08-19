# infra LLM 自动选择策略审计报告

> **对象**：aiPlat-infra 模型选择策略（`infra/management/model/manager.py` 1790 行 + `llm_profile.yaml`）+ core 消费链（`model_injection.py`）。
> **时点**：2026-08-19。**方法**：全链路代码阅读 + 本机实测（无 env / 有 env 两场景），每条结论附 `文件:行号` 证据与验证命令。
> **结论先行**：策略框架（purpose 需求驱动 + 资源感知 + 降级链 + safe 保底）设计正确，但存在 **1 个评分符号反转 bug（P0）** 与 **1 个 fallback 无校验缺陷（P0）**，以及 3 个完整性问题（P1-P2）。

---

## 1. 选择链路全景（两条并行路径）

```
core best_model_for_purpose (model_injection.py:1687)
  └─ Step 0: session override → Step 0.5: tts/stt 捷径
  └─ Step 1: unified_pipeline (manager.py:1265)  ← 主路径（v3 评分）
       ├─ hard filter (_hard_filter:206): enabled/尺寸/RAM/VRAM/磁盘
       ├─ soft filter 降级链 (L1284-1292): full → -cap → -cap-hlt → none
       ├─ _score_model 15 项评分 (:425) ← ⚠️ 符号 bug 在此
       └─ safe_model 保底 (:1320): 存在性校验 + RAM 校验 → RuntimeError

core create_adapter_with_fallback 等 fallback 路径 (model_injection.py:974, 1151)
  └─ select_by_purpose_list (manager.py:1058)  ← 旧 v2 评分（双轨之一）
       ├─ 自研打分（capability/resource/quality/latency/cost）符号正确
       └─ 空候选 → 返回 fallback.ultimate_model ⚠️ 无存在性校验

get_default_model (manager.py:1010) ← env 唯一解析点（只读 env）
```

---

## 2. 正确性问题（实证）

### P0-1 ⚠️ v3 评分延迟/成本惩罚**符号反转**（负负得正 → 奖励高延迟/高成本模型）

`_score_model` 中惩罚值（负数）与权重（负数）直接相乘：

| 行 | 代码 | 数学结果（实测） | 应为 |
|---|---|---|---|
| L507-511 | API 模型 `latency_penalty=-20` × `weights["latency"]=-2.5`（chat） | **+50 奖励** API 模型 | 负分惩罚（注释明示 "API models have network overhead"） |
| L556-559 | `p95>10 → -40` × `weights["latency"]=-1.0` | **+40 奖励** 高延迟模型 | 负分 |
| L568-572 | `cost>0.01 → -10` × `weights["cost"]=-1.0` | **+10 奖励** 贵模型 | 负分 |

**实证**：`_get_scoring_weights` 返回 latency=-2.5/cost=-1.0（负权重），`-20 × -2.5 = +50` 已脚本验证。
**影响**：unified_pipeline（core 主路径）中，chat purpose（latency weight 最大 -2.5）实际**奖励**高延迟 API 模型 +50 分——"低延迟优先"设计目标被反转，且与 v2 旧打分（`score -= 40` 符号正确）行为矛盾。
**修复方向**：`score += int(penalty * abs(weight))` 或权重改正数、惩罚改负数统一约定。

### P0-2 ⚠️ `select_by_purpose_list` 空候选 fallback **不校验模型存在性**

- L1075：`fallback_model = profile_data.get("fallback", {}).get("ultimate_model", "deepseek-chat")`
- L1233-1234：`if not scored: return [fallback_model] if fallback_model else []`
- **实证**：本机（注册表仅 1 个 embedding 模型，无 chat 模型）实测 `select_by_purpose_list("chat")` 返回 `['deepseek-chat']`——**该模型根本不在注册表**；而 `unified_pipeline("chat")` 正确地抛 RuntimeError（safe_model 有 `_find_model_by_name` 校验）。
- **影响**：core fallback 路径（`create_adapter_with_fallback` L974）拿到不存在的模型名 → 运行时 404/失败；静默无警告。
- **修复方向**：复用 unified_pipeline 的 safe 保底逻辑（校验存在性 + 硬过滤）。

### P1-3 配置与代码漂移：`fallback.ultimate_model` 在 llm_profile.yaml 中**不存在**

- yaml L78-81 只有 `safe_model`/`safe_model_alt`/`safe_model_ram_limit`；代码 L1075 读 `ultimate_model` → 永远落默认硬编码 `"deepseek-chat"`。
- 两套 fallback 语义并存且不一致：unified_pipeline 用 `safe_model`（qwen2.5:3b），select_by_purpose_list 用硬编码 `deepseek-chat`。

### P1-4 `get_default_model` 只读 env、不校验模型有效性

- L1010-1031：按 purpose 读 `AIPLAT_*_MODEL` env，返回 env 值或空串；**不验证模型存在于注册表/已启用/资源可载**。
- **实证**：`AIPLAT_DEFAULT_CHAT_MODEL=deepseek-chat`（不在注册表）时 `get_default_model("chat")` 返回该无效名；`select()`（L1390）随后 `_find_model_by_name` 失败 → 返回 None 静默。
- 消费方：core `howl.py:193`、`parsers.py:281` 等用它做兜底，可能拿到无效模型。

---

## 3. 完整性问题

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| P1-5 | **双轨评分并存**：v3 `_score_model`（unified_pipeline）与 v2 自研打分（select_by_purpose_list）是两套独立逻辑，结果可能分叉（如延迟项符号相反） | manager.py:425 vs :1058 | 同一请求走不同路径得到不同模型；维护双倍成本 |
| P2-6 | **purpose 枚举两处注册**：`llm_profile.yaml purpose_profiles`（7 个）vs `get_default_model purpose_env_map`（9 个）独立维护 | yaml:6 / manager.py:1013-1026 | 新增 purpose 需两处注册，漏一处则 env 或 profile 静默缺失 |
| P2-7 | **本地优先裁决不一致**：`select()` L1407-1414 无条件 local-first（无质量门）；unified_pipeline #15 有 quality-gated 本地偏好（L577-592） | manager.py:1407 / :577 | 按名称 select 与按 purpose 评分对"本地 vs API"结论可能相反 |
| P2-8 | 降级到 `-cap-hlt` 层时 health 过滤被去掉（L1290），病模型可被选 | manager.py:1290 | 降级场景缺 health 保护（有 degradation WARNING，但无健康 detail） |

**已正确/良好的部分**（记录防回归）：
- `_build_preferences`（model_injection.py:1640）：env 偏好有 RAM/size 保护（size=None 拒绝偏好防 OOM、超 RAM 忽略）✓
- unified_pipeline safe 保底：存在性 + 硬过滤 + RAM 校验三重 ✓
- `_hard_filter`：物理约束永不放宽，Ollama/LM Studio 外部进程正确跳过 RAM/VRAM 检查 ✓
- `_calculate_dynamic_boost`（L659）：符号正确、冷启动返回 0 ✓
- 降级链日志：非 full 层有 WARNING ✓

---

## 4. 改善建议（按优先级）

| # | 建议 | 对应问题 | 工作量 |
|---|---|---|---|
| 1 | **修复 v3 评分符号**：`_score_model` 延迟/成本项改 `penalty * abs(weight)`（或统一权重/惩罚符号约定），补符号断言单测 | P0-1 | 0.5 天 |
| 2 | **select_by_purpose_list fallback 加存在性校验**：空候选时仅返回注册表中存在的模型；消除硬编码 `deepseek-chat`（改读 `fallback.safe_model` 或补 `ultimate_model` 配置） | P0-2, P1-3 | 0.5 天 |
| 3 | **get_default_model 加有效性校验**：返回前 `_find_model_by_name`，无效则警告 + 回退注册表默认 | P1-4 | 0.5 天 |
| 4 | **双轨收敛**：select_by_purpose_list 改为基于 unified_pipeline 评分（或标记为 deprecated 仅保留 fallback 列表语义） | P1-5 | 1 天 |
| 5 | **purpose 枚举统一**：purpose_env_map 从 llm_profile 派生 | P2-6 | 0.5 天 |
| 6 | **select() local-first 加质量门**：复用 #15 的 `_within_quality_band` | P2-7 | 0.5 天 |

**验证命令**：

```bash
# P0-1 符号验证
cd aiPlat-infra && python3 -c "
from infra.management.model.manager import _get_scoring_weights
import yaml
cfg = yaml.safe_load(open('config/infra/llm_profile.yaml'))
print(-20 * _get_scoring_weights('chat', cfg)['latency'])  # 期望 ≤0，实测 +50
"
# P0-2 空候选 fallback 实证
cd aiPlat-infra && python3 -c "
import asyncio
from infra.management.model.manager import ModelManager
async def m():
    mgr = ModelManager(); await mgr.list_models()
    print(mgr.select_by_purpose_list('chat'))  # 期望 [] 或存在的模型，实测 ['deepseek-chat']
asyncio.run(m())
"
```

---

## 5. 可信度

- 全部结论为**源码级阳性证据**（`文件:行号`）+ 本机实测输出；无阴性推断。
- P0-1/P0-2 已实测复现；P1/P2 为代码阅读结论（逻辑明确，未逐一构造场景复现）。
