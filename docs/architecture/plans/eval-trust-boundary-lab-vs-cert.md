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

## 仍缺（进入「更可信任」之前）

1. G2b ≥ 门槛或明确 scoped 披露（当前 72% / CI 下界未达 70% → `accuracy_claim=false`）  
2. Arena clean pack + QA pass 后再谈替换 length smoke  
3. staging + 生产轴证据；独立第三方审计  
4. 代表性任务扩样 + 失败归因；人评 `filled_by`/签名强化  
5. 冻结 commit / 题集 / 判分器 / 执行清单的完整可复现包（本文件 + manifest 仅为 Plan 切片）

## 诚实约束

- `accuracy_claim=false` 保持默认。  
- `capability_unconfirmed:*` ≠ 已证明具备该能力。  
- 本文件是**信任边界声明**，不是认证证书。
