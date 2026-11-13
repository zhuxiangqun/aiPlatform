---
doc_type: Architecture
---

# 评测信任边界：实验室仪器 ≠ 认证机构

> **状态**：工程立场锁定（2026-11-08）· **≠** 外部审计 · **≠** staging/prod 认证 · **≠** accuracy_claim  
> **依据**：对象契约 §0.7 / §0.9；G2b / Arena / Plan #618 证据；本地重跑清单见 `.aiplat/eval_trust/`

## 一句话

**可信的是「这次评测怎么跑、命中了什么」；不可信的是「成果物已准确 / 可上线 / 已安全认证」。**

| 层面 | 可信度（工程自评） | 判断 |
|------|:--:|------|
| 工程系统本身 | 3.5–4/5 | 队列/门禁/证据链真实；Plan §0.7 修复已合 main（#618） |
| 单次执行记录 | 4/5 | runner / 输出 / 规则命中可追溯 |
| 评测判断/分数 | 2–2.5/5 | 启发式并存；G2b 未达门槛；旧 Plan 无效 |
| 准确率/安全/生产认证 | 1/5 | 无 staging、无外部审计、无认证 |

## 可信任 / 有条件 / 不可信

| 用途 | 态度 |
|------|------|
| 固定 gold 的 pass/fail 回归 | 有条件可用（发现退化；不可外推） |
| 单次执行记录 / 规则命中 | 可信任 |
| 同 benchmark Prompt/模型 A/B | 有条件参考 |
| 跨对象 / 跨 runner 排名 | 不可直接比 |
| 开放文本质量 / Arena 胜负 | 弱；Arena QA 未过则不可替换 length smoke |
| 准确率声明 / 安全认证 / FDE 签收 | **不可**由本系统单独支撑 |

## Plan 修复与作废

| 项 | 状态 |
|----|------|
| #618：`derived_hints` 不得单独驱动 `not_applicable` | ✅ 合入 main |
| 本机重跑 `qa_agent` compile-plan | ✅ `plan-ed6fe2bb40fc087f` · selected=6 · N/A=0 |
| 旧 Plan `plan-924f6c070f4e1927`（3 入选 / 3 不适用） | **`pre-fix_invalid`** — 禁止用于产品结论 |
| 证据清单 | `.aiplat/eval_trust/plan_rerun_manifest.json` + 同目录 JSON |

重跑断言（已写入 manifest）：

- `eval_profile_source=derived_hints`
- `counts.not_applicable == 0`
- 原 N/A 三套（`missing_info` / `tool_failure` / `multi_turn`）均在 `selected`

## 下一档工程进展（仍 ≠ 认证）

| 项 | 状态 | 证据 |
|----|------|------|
| Plan 重跑 | ✅ | `.aiplat/eval_trust/plan_rerun_manifest.json` |
| Arena SEND 泄漏类缺陷（代码路径） | ✅ leak-guard 绿；**人签 QA 仍未过** | `.aiplat/eval_trust/arena_clean_pack_20261108/` + `next_rung_manifest.json` |
| G2b 28 失败工程分桶 | ✅ 假设标签（≠ 根因认证） | `.aiplat/eval_trust/g2b_fail_taxonomy_v0.json`（重审前快照） |
| G2b 失败决策表（重审） | ✅ 6 题 rubric 误标→pass；22 题 hold | `.aiplat/eval_trust/g2b_fail_decision_table_v0.json` |
| G2b ≥ 80% / CI 下界 ≥ 70% | ✅ **80%** / [71.1%, 86.7%]（§4 数值达标） | `g2b_accuracy_aggregate.v1.json`；**claim 仍关** |
| Arena QA `overall_pass` / 替换 length smoke | ❌ | 需对人发**本干净包**重签；默认 runner 仍 length smoke |
| staging / 外部审计 | ❌ | — |

G2b 失败分桶摘要（重审前 n=28 假设 → 重审后 hold=22）：

- 决策：`re_label_pass=6` · `hold_fail=22`（详见 decision table）
- 格式干预后：`pass_rate=0.80` · Wilson `[0.7112, 0.8666]` · §4 **数值达标** · **claim 仍关**
- hold 主因：能力/安全错答与格式非 JSON（55/95 等），**不**用水化 rubric 冲门槛

## 仍缺（进入「更可信任」之前）

1. G2b §4 数值已达标；开 claim 仍需 owner `accept_accuracy_claim=true`（当前 false）  
2. 对本干净 Arena pack **独立 QA 重签** `overall_pass=true` 后，再单独立项是否 shadow length smoke  
3. staging + 生产轴证据；独立第三方审计  
4. 代表性任务扩样；把假设标签升级为有人复核的错误类型  
5. 冻结 commit / 题集 / 判分器 / 执行清单的完整可复现包

## 诚实约束

- `accuracy_claim=false` 保持默认。  
- `capability_unconfirmed:*` ≠ 已证明具备该能力。  
- 失败分桶 / 干净 Arena 包 = **工程就绪证据**，不是准确率或质量认证。  
- 本文件是**信任边界声明**，不是认证证书。
