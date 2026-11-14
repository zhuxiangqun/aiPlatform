---
doc_type: Architecture
---

# aiPlat 评测系统改善方案（完整可执行版）

> **文档类型**：Design / Execution Plan（**已定稿冻结** · v1.1.7）  
> **版本**：v1.1.7 · 2026-11-14  
> **状态**：**方案已定稿（冻结）** — §15 **14/14**；Phase 1 已验收；META_EVAL F1–F4 **全绿**；Phase 2 **预备中（未授权）**；Phase 3 **A 19/19 scoped** · **B1 suite attached** · B2 待决（全局扩容仍 false）  
> **诚实锁**：定稿 ≠ 生产独立 / ≠ 准确率已认证 / ≠ `process_split_authorized=true` / ≠ Tier A 自动扩容；改阈值或结构须走变更控制  
> **工件**：[`META_EVAL_STATUS.md`](../../../packages/aiplat-evaluation/docs/a3/META_EVAL_STATUS.md) · [`PHASE3_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE3_PREP.md) · [`PHASE1_AUDIT_WORKSHEET.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE1_AUDIT_WORKSHEET.md) · [`PHASE2_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE2_PREP.md) · [`R11_META_EVAL_THRESHOLDS.md`](../../../packages/aiplat-evaluation/docs/a3/R11_META_EVAL_THRESHOLDS.md) · [`R12_CAPABILITY_RECONCILIATION.md`](../../../packages/aiplat-evaluation/docs/a3/R12_CAPABILITY_RECONCILIATION.md) · [`TIER_MATRIX_V0.md`](../../../packages/aiplat-evaluation/docs/a3/TIER_MATRIX_V0.md) · Phase0 处置/SHA/fixtures/CI 子集  

> **关联**：[`eval-v1-charter.md`](./eval-v1-charter.md) · [`eval-production-independent-service.md`](./eval-production-independent-service.md) · [`eval-trust-boundary-lab-vs-cert.md`](./eval-trust-boundary-lab-vs-cert.md) · [`eval-a3-independent-service.md`](./eval-a3-independent-service.md) · `packages/aiplat-evaluation/docs/a3/SCORECARD_V1.md` · `SCORE_SCOPE_V1.md` · `evidence/evidence_manifest.v1.json`  
> **证据时点**：2026-11-14（`.venv` Py3.11：scorecard PASS；honesty scan PASS；`phase0_ci_stable_subset` PASS；`package_release_check` PASS；GH `eval-phase0-stable.yml` 已挂；R11 owner 签字）  
> **本文件不是**：`process_split_authorized` / 产品级 `accuracy_claim=true` / staging 已解冻的许可证。

---

## 0. 一句话

**先把尺子校准、证据链钉死、宣称口径统一，再谈首版满分、生产独立、平台覆盖与修复闭环；覆盖必须分层；尺子本身必须做元评测。**

```text
证据链止血 → 首版 5/5 可审计 → 生产独立（授权后）→ 平台覆盖（分层）
                                              ↘ Phase 3.5 元评测
                                                    → 失败处置闭环
```

### 审核结论（2026-11-14 · §15.3 四条件齐 → 定稿冻结）

```text
方案正确性：高
结构完整性：高
可执行性：高
当前可定稿性：满足（设计冻结）

§15.3：
  R1–R9 正式 ☑
  R10–R14 工件齐并正式 ☑（含 R11 owner 签字；R12 tranche-1 H5=0）
  scorecard_v1_check 绿
  accuracy 方案 A 落地 + 消费方验证

仍开放（执行层，不阻止定稿）：
  Phase 2 authorize / staging
  R12 tranche-1 H5 已清零（H6 out_of_tranche 仍在；≠全平台覆盖）
  Phase 3 / 3.5 落地
```

```text
结构 / 顺序 / 边界：正确
五个硬收口：方向正确
五个执行细节：正确
可作为执行基线：是
可作为已审核冻结定稿：是（v1.1.7）
```

一句话：

> **改善方案设计已定稿冻结；执行上继续 Phase 2 预备（未授权）与 R12/元评测落地，禁止误读为生产已独立或准确率已认证。**

---

## 1. 现状诊断（代码/证据事实，非愿望）

### 1.1 已经对的地方

| 项 | 现状 | 含义 |
|---|---|---|
| 入口收敛 | canonical `/api/platform/apps/eval`；UI `/eval` | 不再多入口并行宣称 |
| 首版记分卡结构 | `feature / arch / local(-microVM) / production` | 范围相对 `SCORE_SCOPE_V1` |
| 生产独立诚实 | `process_split_authorized=false`；production 轴 `scored_in_v1=false` | 未授权不宣传 |
| G2b 数值 | n=100，κ≈0.7624，pass_rate=0.80，Wilson lo≈0.7112 | §4 数值门槛已达 |
| Owner attestation | `accept_scoped_accuracy_claim` 已签 | 仅授权 **scoped G2b**，不是产品级 accuracy 认证 |

### 1.2 当前阻断（必须 Phase 0 先清）

| # | 事实 | 验证 |
|---|---|---|
| 1 | `scorecard_v1_check` **失败**：三份 instruction SHA mismatch | `SCORE_SCOPE_V1.md` / `G2B_PREP.md` / `PREFERENCE_V0.md` |
| 2 | `g2b_accuracy_aggregate.v1.json`：`accuracy_claim=true`、`not_accuracy_certification=false`、`claim_refuse_reason=null` | **字段名复用冲突**：scoped 事实成立，但写进了产品级字段名，与 scorecard 产品级 `false` 冲突 |
| 3 | attestation 为 **scoped accept**；aggregate 复用产品级 `accuracy_claim` | 须拆字段：产品级永远 false；scoped 另字段 |
| 4 | manifest 仍指 `human_pack/20261103T130302Z`；该 pack 在 `_archive/`；`calibration_human_pack.py` 仍硬编码旧路径 | fixture 与归档纠缠 |
| 5 | κ/CLI 存在 n=100 vs 30-task 子集不一致风险 | 须子集包 + 输入输出一致 |
| 6 | production 轴缺口仍在：staging / B4-S / B5 / B6 / SPLIT_CHECKLIST | 正确：首版不计分，但宣传禁区 |

### 1.3 核心风险（若不收口会发生什么）

1. **哈希洗白**：文档编辑后只改 SHA，语义变了却仍报旧分。  
2. **宣称漂移**：G2b scoped 被读成「产品已认证准确」。  
3. **尺子失效**：覆盖矩阵很全，但 judge/gold/holdout 不可信。  
4. **分类无出口**：失败只贴标签，不处置 → 永远「快全绿」。  
5. **全量平铺**：每个能力都要 gold+gate → 清单不可完成，真正高风险能力反而漏测。  
6. **子集冒充全绿**：CI 只跑 5 个包测，core/platform 隐藏回归未进处置表。  
7. **证据不可回滚**：改错 manifest/aggregate 后无法回到上一审计态。  
8. **fixture 隐私泄漏**：把 raw human_pack 当正式测试源。

---

## 2. 目标 / 非目标 / 锁定决策

### 2.1 目标

1. **可审计的证据链**：manifest SHA、聚合、双人 attestation、CI 可复现。  
2. **诚实的宣称语义**：产品级 accuracy 关闭；仅 G2b scoped 可开。  
3. **首版 5/5 真可复核**：相对 `SCORE_SCOPE_V1`，不是口号。  
4. **生产独立有授权门**：未授权不写「已独立」。  
5. **平台覆盖可完成**：Tier A/B/C；源=`AIPLAT_CAPABILITIES.md` + `capability_registry.yaml`。  
6. **失败可闭环**：分类 → 处置 → owner → 退出条件 → 复评。  
7. **尺子可信**：Phase 3.5 元评测通过才扩覆盖。

### 2.2 非目标

- 不在 Phase 0 未绿时宣称首版审计通过  
- 不把 κ / preference agreement 当 accuracy  
- 不把 local rehearsal 当 staging authorize  
- 不把 Arena length-smoke 当 blind gate  
- 不做「每个能力立刻 gold+gate」  
- 不跳步开 `process_split_authorized=true`

### 2.3 锁定决策（不再争论）

| ID | 决策 | 锁定值 |
|---|---|---|
| L1 | accuracy 方案 | **A**：产品 `accuracy_claim=false`；G2b `scoped_accuracy_claim=true` |
| L2 | 诚实锁四字段 | 见 §4.2；八消费方一致 |
| L3 | SHA | **先变更控制评审，再更新 manifest**；禁 hash-wash |
| L4 | fixture | **独立 fixture**；禁止 `_archive` 回迁；须满足 §4.6 隐私/来源/授权 |
| L5 | κ 包 | **优先 30-task 子集包**；CLI I/O 与门禁一致 |
| L6 | 覆盖源 | registry=机器主键；CAPABILITIES=人类视图；对账后 canonical 为唯一源 |
| L7 | 覆盖策略 | Tier A/B/C；非全量平铺 |
| L8 | 生产独立 | 授权证未绿前 `process_split_authorized=false` |
| L9 | 顺序 | 0→1→2→3→3.5→4；禁止跳步宣称 |
| L10 | Phase 0 测试 | **先全量基线快照**，再选稳定子集进 CI；禁止只用 5 个包冒充全绿 |
| L11 | 元评测初始阈值 | 见 §4.4；可调，但必须有初始值 + owner |
| L12 | 能力对账 | registry = 机器主键；CAPABILITIES = 人类视图；差异进对账队列 |
| L13 | 证据版本/回滚 | evidence/scorecard/aggregate 有版本与 `change_id`；可回滚上一审计态 |
| L14 | fixture 隐私 | 无 PII；来源可追溯；有授权/license；与 raw human_pack 脱敏关系明确 |

---

## 3. 阶段总览

| Phase | 名称 | 退出条件（硬） | 未退出时禁止宣称 |
|---|---|---|---|
| **0** | 证据链止血 | §5 清单 0.0 / 0.0a / 0.1–0.6 全绿 | 「证据链健康」「首版可审计」 |
| **1** | 首版 5/5 可审计 | scorecard check 绿 + 三轴 5.0 有证据 + 双人 attestation 有效 | 「首版 5/5 已通过」 |
| **2** | 生产独立 | SPLIT_CHECKLIST + staging + B4-S/B5/B6 授权 | 「评测已独立生产」 |
| **3** | 平台覆盖 | Tier 矩阵发布；Tier A 全部有 gold+gate | 「全平台已评测覆盖」 |
| **3.5** | 元评测 | judge/gold/contamination/holdout 门禁绿 | 「评测体系成熟/尺子可信」 |
| **4** | 修复闭环 | 失败 taxonomy→路由→复评 SLA 可跑 | 「自动改进已闭环」 |

```text
顺序锁定：证据链 → 首版 5/5 → 生产独立 → 平台覆盖 → 修复闭环
         （元评测 3.5 与覆盖 3 咬合，扩 Tier A 前必须过）
```

---

## 4. 五个硬收口 + 五个执行细节（验收层 SSOT）

### 4.1 收口①：失败必须有处置结论

**规则**：分类只是输入；没有「处置 + Owner + 退出条件」的条目不算处理完。

#### 失败类型与默认处置

| 类型 | 含义 | 默认处置 | 退出条件 |
|---|---|---|---|
| 环境 | 缺服务/GPU/密钥/OS | 补环境；短期可 `skip` + 原因 + 跟踪单 | 复跑该用例绿，或 skip 有 owner 与过期日 |
| 数据 | fixture/gold 缺失或脏 | 补 fixture；或标 `known-gap` | fixture 可加载且断言稳定，或 known-gap 入账 |
| 实现 | 代码/接线错误 | 修缺陷并登记 | 单测/门禁覆盖该路径且绿 |
| 断言过期 | 行为已变、断言仍旧 | 改断言 + 附 diff/证据 | 新断言与产品意图一致且评审通过 |

#### 处置表模板（Phase 0.0 必填）

| 失败 ID | 症状/命令 | 类型 | 处置 | Owner | 退出条件 | 状态 |
|---|---|---|---|---|---|---|
| F-001 | （粘贴失败摘要） | 环境/数据/实现/断言过期 | … | … | 可复现命令 → 期望结果 | open/done/wontfix |

**门禁**：未分类且未处置的失败数 > 0 → 禁止进入 Phase 1。

---

### 4.2 收口②：accuracy 诚实锁（方案 A）

#### 语义拆分（禁止再混）

```text
accuracy_claim            = 产品级字段，永远 false（未做平台 accuracy 认证）
scoped_accuracy_claim     = G2b 范围字段，attestation accept 后可为 true
not_accuracy_certification = true（诚实锁打开：不是平台/外部认证）
claim_refuse_reason       = 非空，解释为何产品级不开
```

**方案 A 不是**把 scoped 事实抹掉、简单把 `true` 改 `false`；而是：

```text
保留 scoped 事实（G2b n=100 / pass_rate / attestation）
换字段名：scoped → scoped_accuracy_claim
产品级字段 accuracy_claim 保持 false
```

#### 字段真值（修正后）

```text
accuracy_claim                 = false
scoped_accuracy_claim          = true   # 仅在 G2b attestation accept 后
not_accuracy_certification     = true
claim_refuse_reason            = "产品级 accuracy 未认证；仅 G2b scoped"
```

#### 当前错误样例（字段名复用，必须改）

`packages/aiplat-evaluation/docs/a3/evidence/g2b_accuracy_aggregate.v1.json` 现状（2026-11-14）：

```json
"accuracy_claim": true,
"not_accuracy_certification": false,
"claim_refuse_reason": null
```

说明：在 **scoped** 语义下 `true` 可以成立，但复用了**产品级字段名**，导致与 scorecard 冲突。应改为：

```json
"accuracy_claim": false,
"scoped_accuracy_claim": true,
"not_accuracy_certification": true,
"claim_refuse_reason": "产品级 accuracy 未认证；仅 G2b scoped"
```

attestation 保持：`accept_scoped_g2b_accuracy_claim` / `scoped_g2b_accuracy_claim_only=true`，**禁止**再把产品级 `accuracy_claim` 拧成 true。

#### 八消费方一致性检查表

| # | 消费方 | 期望 |
|---|---|---|
| 1 | `g2b_accuracy_aggregate.v1.json` | 方案 A 四字段 |
| 2 | `scorecard_v1.json` | `accuracy_claim=false` |
| 3 | `evidence_manifest.v1.json` | `accuracy_claim=false`；method 注明 scoped |
| 4 | `g2b_accuracy_claim_attestation.v1.json` | scoped accept；非产品认证 |
| 5 | 包内 / core 相关 tests | assert 产品级 false；scoped 另字段 |
| 6 | API / CoreFacade 返回 | 同上 |
| 7 | 管理端 UI（Scorecard/G2b panel） | 展示 scoped，不展示「已认证准确」 |
| 8 | 对外 docs / CAPABILITIES 文案 | 禁止「accuracy 已认证」 |

**门禁**：任一消费方产品级 `accuracy_claim=true` → CI 红。

---

### 4.3 收口③：SHA 变更控制（可审计，不只口头 review）

#### 变更流程

```text
改文档 → 生成 diff 摘要 → 判定编辑性/语义性 → 写评审记录
  →（语义）升 SCORE_SCOPE 版本 + 重跑 scorecard + 通知下游
  →（编辑）可更新 manifest SHA
  → commit 带变更单号
```

#### 每次 SHA 更新必附字段

| 字段 | 说明 |
|---|---|
| paths | 哪些 instruction 文件 |
| old_sha / new_sha | 变更前后 |
| diff_summary | 3–10 行实质变更 |
| change_class | `editorial` \| `semantic` |
| judge | 有权判定人 |
| reviewer | 复核人（可与 judge 不同） |
| bump_score_scope | yes/no + 新版本号 |
| rescore_required | yes/no |
| downstream_notified | yes/no + 渠道 |
| commit | SHA |

#### 判定规则

| 变化 | 归类 | 动作 |
|---|---|---|
| 错别字、标点、链接、格式 | editorial | 可只更新 SHA |
| 范围、门槛、排除项、计分含义、宣称语义 | semantic | **必须**升版本 + 重评分；旧 5/5 作废直至重跑 |
| 无法判断 | 按 semantic 处理 | 保守 |

**禁止**：先改 SHA 再补理由；禁止无评审记录的 manifest 更新。

#### 证据版本与回滚（执行细节，必做）

仅有 SHA review 不够；证据包本身必须可回滚到上一审计态。

| 字段 | 说明 |
|---|---|
| `evidence_version` | `evidence_manifest` 的单调版本（如 `ev-2026-11-14.1`） |
| `scorecard_version` | `scorecard_v1.json` 记录版本（与 SCOPE 版本可对齐） |
| `aggregate_version` | 各 `*_aggregate.v1.json` 写入时的版本戳 |
| `change_id` | 关联 SHA 变更单 / 处置单号 |
| `rollback_ref` | 上一审计态的 git commit 或证据快照路径 |
| `rollback_command` | 可复现回滚步骤（至少：`git checkout <commit> -- <paths>`） |

**规则**：

```text
每次更新 manifest / scorecard / aggregate：
  1. bump evidence_version（或 scorecard/aggregate 对应版本）
  2. 写入 change_id + rollback_ref
  3. 旧版证据保留可读（勿覆盖销毁）
失败回滚：执行 rollback_command → 重跑 scorecard_v1_check → 记入变更日志
```

---

### 4.4 收口④：Phase 3.5 元评测（评测评测）

覆盖矩阵回答「测了没有」；元评测回答「尺子靠不靠谱」。

| 检查 | 目的 | 初始阈值（可调，必须有 owner） | Owner |
|---|---|---|---|
| Judge calibration | judge 与人标对齐 | agreement ≥ **0.80**；κ ≥ **0.60**；ECE ≤ **0.10** | 评测 owner |
| Gold audit | gold 是否泄漏/污染/标注错误 | 抽样错误率 ≤ **5%**；争议有仲裁记录 | 标注/仲裁 |
| Contamination check | 训练/提示/开发是否见过测例 | 超阈 → **advisory**（不得当 Tier A 硬阻断宣称） | 评测 owner |
| Holdout isolation | holdout 是否真 holdout | 开发/调参禁止碰 holdout；**仅发布前一次揭榜** | 评测 owner |
| Inter-annotator 稳定 | 人标尺是否稳 | 双人 κ ≥ **0.60**（与 G2b 门槛对齐）；漂移超阈触发重标 | 标注/仲裁 |

**阈值修订规则**：改阈值 = semantic 变更 → 走 §4.3 变更控制 + 记 `change_id`；禁止口头改阈。

**门禁**：Tier A 能力扩容前，对应家族的元评测项必须绿或显式 `advisory_only`。

---

### 4.5 收口⑤：覆盖分层（Tier A/B/C）

| Tier | 定义 | 要求 | 阻断？ |
|---|---|---|---|
| **A** | 高风险 / 高频 / **已在对外宣称**的能力 | gold + gate + 元评测挂钩 | 是 |
| **B** | 中风险 / 内部关键路径 | suite + 人工复核节奏 | 否（缺口入账） |
| **C** | 低风险 / 实验 / 未宣称 | 仅登记能力 ID 与计划 | 否 |

#### 能力源对账规则（执行细节，必做）

```text
机器主键：core/capability_registry.yaml（capability_id / module / symbol）
人类视图：AIPLAT_CAPABILITIES.md
Join key：capability_id；若无 id 则 (module, symbol) 回退
```

| 差异类型 | 处置 |
|---|---|
| registry 有、CAPABILITIES 无 | 入对账队列 → 补文档行或标「待登记人类视图」 |
| CAPABILITIES 有、registry 无 | 入对账队列 → 补 registry 或降为非能力叙述 |
| 同一能力两条（重复 join） | 合并为一条；保留 canonical id |
| 仅文档口语、无机器符号 | 不得进入 Tier A 覆盖矩阵 |

**覆盖矩阵只吃对账后的 canonical 清单。**  
**禁止**：另建平行能力清单；禁止「未宣称能力」占用 Tier A 名额挤掉已宣称能力。

**R12 完成工件**（同意规则 ≠ 勾完成）：须产出对账结果，至少含：

| 字段 | 说明 |
|---|---|
| 差异清单 | 每条差异的 capability_id / 类型 |
| 差异数量 | 按类型汇总 |
| owner | 每条或每类责任人 |
| 处理结果 | 已补文档 / 已补 registry / 豁免+到期日 / open |

---

### 4.6 执行细节：fixture 隐私与来源约束

human_pack 含人工标注；「独立 fixture」**不是**随意复制 raw pack。

| 约束 | 要求 |
|---|---|
| 无 PII | fixture 不得含姓名/电话/邮箱/内部路径可识别信息（除已公开角色名且经授权） |
| 来源可追溯 | 每份 fixture 标明 `source_pack` / `derived_from` / 生成脚本 |
| 授权 / license | 入仓 fixture 须有使用授权说明（内部评测用途即可，但必须显式） |
| 脱敏关系 | 文档写明：raw human_pack → 脱敏/切片 → fixture；raw 可留 `_archive` 或 gitignore |
| 禁止 | 为过测把含 PII 的 archive 回迁为正式测试源 |

**门禁**：新增 fixture PR 无来源字段或未声明脱敏 → 拒合。

---

## 5. Phase 0 — 证据链止血（立刻执行）

### 5.1 最小检查清单

```text
0.0  失败处置表填满（分类+处置+owner+退出条件）
0.0a 全量测试基线快照（package 全量 + core eval 相关全量 + platform eval）
0.1  三份 SHA mismatch 文档：diff → 判定 → 评审记录 →（按需）升版本/更新 SHA
     + evidence_version / change_id / rollback_ref
0.2  accuracy：拆字段（产品级 false / scoped 另字段）；八消费方扫描全绿
0.3  human_pack：独立 fixture（无 PII、可追溯、有授权）；不回迁 _archive
0.4  G2b：建立/钉死 30-task 子集包；κ CLI 输入输出与 CI 一致
0.5  CI：仅保留稳定子集（scorecard + 包内关键测 + core 关键项）
0.6  子集全绿复跑 → 才允许进入 Phase 1
     （全量基线中的已知失败必须已在 0.0 处置表闭合或 skip）
```

### 5.2 Phase 0 硬约束（不可妥协）

```text
未分类失败处置完成前不宣称全绿
先全量基线，再 CI 子集（禁止「5 个绿 = 全绿」）
SHA 先变更控制再更新；证据可回滚
accuracy 拆字段；产品级永远 false
fixture 无 PII、不依赖 _archive 作正式源
kappa 用子集包（优先 30-task）
CI 钉死 scorecard + 稳定子集
```

### 5.3 Phase 0 工作包明细

#### WP-0.0 失败处置

1. 收集当前红灯：`scorecard_v1_check`、相关 pytest、κ CLI、calibration 路径、**core eval 相关失败（含已知 ~13）**。  
2. 填处置表（§4.1）；至少录入：SHA×3、accuracy 字段冲突、human_pack 路径、κ n=30/100、core 失败集。  
3. 每条做到 `done` 或带过期日的 `skip/known-gap`。

#### WP-0.0a 全量测试基线快照

```text
目的：暴露隐藏回归，避免「包内 5 绿、core 仍红」
范围：
  1) packages/aiplat-evaluation 全量 pytest
  2) core 侧 eval 相关全量测试
  3) platform 侧 eval 相关测试
产出：基线报告（时间戳、命令、pass/fail 清单、归入处置表的 ID）
之后：从基线中挑选稳定子集 → 写入 0.5 CI；失败项不得静默消失
```

#### WP-0.1 SHA 变更控制

对以下三文件执行 §4.3：

- `packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md`
- `packages/aiplat-evaluation/docs/a3/G2B_PREP.md`
- `packages/aiplat-evaluation/docs/a3/PREFERENCE_V0.md`

产出物：`SHA_CHANGE_LOG` 条目（含 `evidence_version` / `change_id` / `rollback_ref`）+ 更新后的 `evidence_manifest.v1.json`（仅在判定通过后）。

#### WP-0.2 accuracy 诚实锁

1. **拆字段**：产品级 `accuracy_claim=false`；G2b 用 `scoped_accuracy_claim`；改 aggregate / schema / tests / UI。  
2. 跑一致性扫描（建议脚本化 grep/assert）：产品级 `accuracy_claim=true` → 红。  
3. 保留 attestation「scoped accept」语义；**禁止**再写回产品级 true。

#### WP-0.3 fixture 与归档隔离（含隐私）

```text
正式路径：docs/a3/fixtures/... 或 human_pack/<active_stamp>/（入仓、可测）
归档路径：docs/a3/_archive/human_pack/...（只读历史）
脚本：calibration_human_pack / g2b_n100_pack / manifest 全部改指正式路径
隐私：见 §4.6（无 PII、来源、授权、脱敏关系）
禁止：测试依赖 _archive；禁止「为了让测过把 archive 搬回」
```

#### WP-0.4 G2b 子集包

```text
优先：固定 30-task 子集（稳定、可 CI）
全量 n=100：保留为 closeout/报表包，不强制每次 PR
CLI：同一入口参数 → 同一输出 schema；incomplete_pair 必须失败并带 missing_n
```

#### WP-0.5 CI 钉死（稳定子集，非全量冒充）

在 **0.0a 基线** 之上选取稳定子集入 CI：

1. `bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh`  
2. 包内稳定子集（从基线绿项中钉死；数量可变，但须显式列表）  
3. core eval 稳定子集（基线中仍红的项留在处置表，**不得**因未进 CI 就当不存在）  
4. 全量基线建议 nightly / 手动里程碑再跑；PR 门禁用子集

#### WP-0.6 进入 Phase 1 的闸门命令（示例）

```bash
bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh
# + CI 稳定子集 pytest 全绿
# + accuracy 八消费方扫描：产品级 accuracy_claim=true → fail
# + 失败处置表 open=0（或仅允许未过期 skip）
# + 0.0a 基线报告已归档，且基线红项均有处置 ID
```

---

## 6. Phase 1 — 首版 5/5 可审计

### 6.1 定义

「5/5」= 相对 `SCORE_SCOPE_V1` **in-scope** 三项达到可审计满分：

| 轴 | 要求 |
|---|---|
| feature_coverage | 5.0 + manifest/聚合/双人 attestation 有效 |
| engineering_architecture | 5.0 + 范围文档与实现一致 |
| local_independence_no_microvm | 5.0 + local 证据；≠ authorize |

另两项保持诚实：

| 轴 | 首版态度 |
|---|---|
| local_independence_with_microVM | Darwin = N/A；Linux 证据另补 |
| production_independence | **不计首版分**；缺口列表保留 |

### 6.2 验收

- `scorecard_v1_check` 绿  
- 无 SHA mismatch  
- 产品级 `accuracy_claim=false`  
- 文档/UI 不出现「生产已独立」「准确率已认证」  
- 审计人可凭 manifest 复算哈希与聚合

### 6.3 仍禁止的误读

| 误读 | 正解 |
|---|---|
| 功能 5 = 评得准 | 否；accuracy 另表；仅 scoped G2b |
| 本地 5 = 可 authorize | 否 |
| JSON 写 5 = 已审计 | 否；须 check 脚本绿 |

---

## 7. Phase 2 — 生产独立（授权后）

沿用 [`eval-production-independent-service.md`](./eval-production-independent-service.md) B 轨方案，但宣传门禁如下：

```text
未同时满足前，禁止宣传「生产独立」：
  process_split_authorized=true（经 SPLIT_CHECKLIST）
  staging 验收通过（B4-S）
  B5/B6 按清单关闭
  环境标签不得把 local 证据标成 staging
```

本地 A1–A6 / B1-L/B2-L 可继续工程推进，但 **证据 `environment=local`**，与授权证分离。

---

## 8. Phase 3 — 平台覆盖（分层）

### 8.1 流程

```text
1. 对账：registry（主键）⋈ CAPABILITIES（视图）→ canonical 清单（§4.5）
2. 对差异入对账队列，清零后再打 Tier
3. 打 Tier A/B/C（风险×频率×是否已宣称）
4. Tier A：建/挂 gold + gate + 元评测挂钩（§4.4 阈值）
5. Tier B：suite + 复核日历
6. Tier C：只登记
7. 覆盖率报表按 Tier 分列，禁止只报一个「覆盖%」糊弄
```

### 8.2 Tier A 准入启发式（可配置，禁止写死业务名在 harness）

- 已在对外文档/UI 宣称  
- 安全/权限/资金/隐私相关  
- 发布门禁路径上的能力  
- 高频用户路径（以观测为准）

### 8.3 退出

- Tier A：0 个「无 gold 且无豁免」  
- 报表：A/B/C 分列；豁免有 owner 与到期日

---

## 9. Phase 3.5 — 元评测（与 Phase 3 并行咬合）

最小协议已成文：[`META_EVAL_V0.md`](../../../packages/aiplat-evaluation/docs/a3/META_EVAL_V0.md)；**初始阈值见 §4.4 / R11**（agreement≥0.80 / κ≥0.60 / ECE≤0.10 / gold 抽样错误率≤5%）：

1. **Judge calibration**：固定人标集；低于阈 → judge 不得用于 Tier A gate。  
2. **Gold audit**：每季度（或每升 SCOPE 版本）抽样；错误率 >5% → 冻结宣称。  
3. **Contamination**：对 Tier A 题包做重叠检查；超阈 → advisory（不得当已认证）。  
4. **Holdout**：开发/验证/holdout 三分离；CI 只跑开发/验证；**仅发布前一次揭榜**。  
5. **IAA 稳定**：双人 κ≥0.60；漂移超阈 → 重训标注说明 + 重标争议集。

Phase 3 扩 Tier A 与 Phase 3.5 绑定：**无元评测绿灯，不新增 Tier A gate 宣称。**  
改阈值须走 §4.3 + owner 签字。

---

## 10. Phase 4 — 修复闭环

```text
失败出现
  → taxonomy（环境/数据/实现/断言过期/产品缺陷/评测缺陷）
  → 路由：
       环境 → infra/运维
       数据 → fixture/gold owner
       实现 → 对应模块缺陷单
       断言过期 → 评测 owner + 产品确认
       评测缺陷 → Phase 3.5 / judge / gold
  → 修复
  → 复评（同一 pack 指纹）
  → 关闭（附证据）
```

**SLA（建议）**：Tier A 门禁红 → 24h 内有 owner；72h 内有处置结论（修/skip/降级宣称）。

---

## 11. 组织与产物

| 产物 | 用途 |
|---|---|
| 失败处置表 | Phase 0.0 / 日常 |
| 全量测试基线快照 | Phase 0.0a |
| SHA / 证据变更日志 | instruction + evidence_version + rollback |
| accuracy 一致性扫描报告 | CI（产品级字段禁 true） |
| 能力对账队列 + canonical 清单 | Phase 3 |
| Tier 覆盖矩阵 | Phase 3 |
| Meta-eval 报告（含阈值） | Phase 3.5 |
| Scorecard + manifest | 首版审计 |
| fixture 来源/脱敏说明 | Phase 0.3 / §4.6 |
| 缺陷/skip 账本 | 禁止静默洞 |

角色（最小）：

| 角色 | 职责 |
|---|---|
| 产品 owner | scoped claim 接受；语义变更最终解释 |
| 评测 owner | 处置表、SHA 日志、CI、元评测 |
| 标注/仲裁 | gold / IAA |
| 模块 owner | Tier A/B 缺陷修复 |

---

## 12. 验证命令锚点（执行时用）

```bash
# 证据链
bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh

# accuracy 诚实锁（示例扫描；落地时可脚本化）
rg -n '"accuracy_claim":\s*true' packages/aiplat-evaluation/docs/a3 -g '*.json'

# fixture 不依赖 archive（示例）
rg -n '_archive/human_pack|human_pack/20261103T130302Z' \
  packages/aiplat-evaluation/scripts packages/aiplat-evaluation/tests

# 生产独立禁宣
rg -n 'process_split_authorized"\s*:\s*true' packages/aiplat-evaluation
```

---

## 13. 时间盒建议（单人 + AI，可调）

| 阶段 | 建议 |
|---|---|
| Phase 0 | 3–7 天（先 0.0+0.0a+0.1+0.2，再 fixture/κ/CI 子集） |
| Phase 1 | 2–4 天复核与文书 |
| Phase 2 | 按已有 B 轨月级；与宣传解耦 |
| Phase 3 首轮 Tier A | 2–4 周（只砍已宣称高风险） |
| Phase 3.5 MVP | 与首轮 Tier A 并行 1–2 周 |
| Phase 4 | 在 A 门禁稳定后 1 周接线 |

---

## 14. 最终评价标准（怎样算「完整、正确、可执行」）

同时满足：

1. **顺序正确**：0→1→2→3/3.5→4，无跳步宣称  
2. **Phase 0 清单可勾选**（含 **0.0a 全量基线**）  
3. **五个硬收口有工件**：处置表、拆字段诚实锁、SHA 日志、元评测协议（含初始阈值）、Tier 矩阵  
4. **五个执行细节有工件**：全量基线报告、阈值+owner、能力对账队列、evidence 版本/回滚、fixture 来源/脱敏说明  
5. **CI 可自动抓住回归**：SHA、产品级 accuracy 字段、scorecard；且不冒充全量  
6. **对外句子经得起追问**：scoped ≠ 认证；local ≠ 生产；5/5 ≠ 全能；子集绿 ≠ 全绿  

**当前可写**：`方案已定稿（冻结）· v1.1.7`；`首版 5/5 已审计通过（相对 SCORE_SCOPE_V1；产品 accuracy_claim=false；≠ authorize）`  
**不可写**：`生产已独立` / `准确率已认证` / `process_split_authorized=true` / Tier A 自动扩容

---

## 15. 审核清单（给审阅人）

### 15.1 勾选语义（强制区分）

| 组别 | 含义 | 勾「完成」的前提 |
|---|---|---|
| **R1–R9** | **设计审核**：是否同意方案设计 | 审阅人同意设计即可；**≠** Phase 0 已落地 |
| **R10–R14** | **条件接受 + 工件**：条件可先「接受」；勾「完成」须有对应工件 | 有基线报告 / owner 签字 / 对账结果 / 回滚工件 / fixture 来源说明 |

**禁止**：用勾选代替工件（例如勾 R10 ≠ 已有全量基线报告）。  
**禁止**：R2 设计通过后宣称 accuracy 已满足——须 Phase 0.2 改齐四字段且八消费方验证后才算落地。

### 15.2 勾选状态（2026-11-14 · owner 授权按建议稿正式勾选）

> **建议稿全文**：[`packages/aiplat-evaluation/docs/a3/PHASE0_R_CHECKLIST_RECOMMENDATION.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE0_R_CHECKLIST_RECOMMENDATION.md)  
> **确认方式**：产品/评测 owner 授权执行方按建议稿落勾；R11 owner=朱向群 · 2026-11-14 accept 初值。  
> §15 **14/14** → 按 §15.3 已允许「方案已定稿（冻结）」。

| # | 审核项 | 设计/条件 | 建议 | 完成勾选 | 理由 / 工件 |
|---|---|---|---|---|---|
| R1 | 阶段顺序 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | 顺序正确 |
| R2 | 方案 A 拆字段 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | **落地已完成**（aggregate/API/UI/scan） |
| R3 | SHA 变更控制 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | `SHA_CHANGE_LOG.md` EV-001/002 |
| R4 | 失败处置表 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | `PHASE0_FAILURE_DISPOSITION.md` F-001…F-010 done |
| R5 | Tier 分层 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | 计划 §4.5；实施在 Phase 3 |
| R6 | 元评测必须 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | 计划 §4.4；实施在 Phase 3.5 |
| R7 | Phase 0.6 禁宣称 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | 诚实锁仍有效 |
| R8 | 生产独立门禁 | ✅ 设计可通过 | 建议正式 ☑ | ☑ | authorize 未开 |
| R9 | 立刻第一步（§16） | ✅ 设计可通过 | 建议正式 ☑ | ☑ | §16 已执行 |
| R10 | 0.0a 全量基线 | ⚠️→工件齐 | 建议完成 ☑ | ☑ | drills 基线报告 + `PHASE0_CI_STABLE_SUBSET.md` |
| R11 | 元评测阈值 + owner | ⚠️→签字齐 | 建议完成 ☑ | ☑ | [`R11_META_EVAL_THRESHOLDS.md`](../../../packages/aiplat-evaluation/docs/a3/R11_META_EVAL_THRESHOLDS.md) · owner 朱向群 accept v0 |
| R12 | 能力对账 | ⚠️→工件齐 | 建议完成 ☑ | ☑ | tranche-1：[`R12_CAPABILITY_RECONCILIATION.md`](../../../packages/aiplat-evaluation/docs/a3/R12_CAPABILITY_RECONCILIATION.md)；H5/H6 过滤后 H5 仍 open；Tier 初稿见 [`TIER_MATRIX_V0.md`](../../../packages/aiplat-evaluation/docs/a3/TIER_MATRIX_V0.md) |
| R13 | 证据版本与回滚 | ⚠️→工件齐 | 建议完成 ☑ | ☑ | `evidence_version` + change log rollback |
| R14 | fixture 隐私/来源 | ⚠️→工件齐 | 建议完成 ☑ | ☑ | `FIXTURE_SOURCES.md` + fixtures |

```text
正式完成勾选：14 / 14
  R1–R9：正式 ☑（设计确认）
  R10–R14：正式 ☑（R12 差异队列仍 open，属处置态）
  门禁：绿（scorecard + honesty + phase0 子集）
  定稿（冻结）：是（v1.1.7 · §15.3 四条件齐）
```

### 15.3 何时可改为「定稿（冻结）」

须**同时**满足：

1. R1–R9 正式勾选完成（设计确认）  
2. R10–R14 各自工件已产出并勾选完成  
3. `scorecard_v1_check` 绿  
4. accuracy 四字段按方案 A 落地且八消费方验证通过  

**2026-11-14**：上述四条件已满足 → 状态改为 **已定稿（冻结）**。  
冻结后改结构/阈值须 bump 版本 + change_id；**不**自动打开 authorize / 产品级 accuracy / Tier A 扩容。

---

## 16. 立刻第一步（设计认可后开工，不改结构）

```text
1. 建失败处置表，录入：
   - SHA×3
   - accuracy 字段名冲突（产品级 vs scoped）
   - human_pack 路径 / _archive
   - κ n=30/100
   - core eval 失败集（含已知 ~13）
2. 对三份文档做编辑性/语义性判定 + 第一条 SHA/证据变更记录（含 rollback_ref）
3. 按方案 A 拆字段改 aggregate（保留 scoped 事实；产品级 false；
   not_accuracy_certification=true；claim_refuse_reason 非空）→ 八消费方验证
4. 跑全量基线（0.0a）并归档报告；红项全部入处置表
5. 再从基线选稳定子集进 CI（0.5）
6. 产出 R12 对账结果（差异清单/数量/owner/处理结果）——可与覆盖阶段并行起步
```

当前：

```text
可写：方案已定稿（冻结）· v1.1.7
      首版 5/5 已审计通过（相对 SCORE_SCOPE_V1；产品 accuracy_claim=false；≠ authorize）
      META_EVAL F1–F4 全绿（≠ Tier A 扩容授权）；Phase 2/3 预备中（未授权）
      R12 tranche-1 H5=0；Tier 矩阵 v0（A_candidate≠授权）
不可写：生产已独立 / 准确率已认证 / process_split_authorized=true / Tier A 自动扩容
```

R11 已签字（朱向群 · accept v0）。执行焦点：META_EVAL F1–F4 均绿（[`META_EVAL_STATUS.md`](../../../packages/aiplat-evaluation/docs/a3/META_EVAL_STATUS.md)）；进入 Phase 3 预备（[`PHASE3_PREP.md`](../../../packages/aiplat-evaluation/docs/a3/PHASE3_PREP.md)）但 `tier_a_expansion_authorized=false`；Phase 2 仅 authorize 后推进；禁一次全开 A。

---

## 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-11-14 | 执行基线成文：Phase 0–4 + 3.5 + 五个硬收口；供审核 |
| v1.1 | 2026-11-14 | 钉死全量基线、元评测初始阈值、能力对账、证据回滚、fixture 隐私；accuracy 拆字段；R10–R14 |
| v1.1.1 | 2026-11-14 | 审核结论入文：状态改回「执行基线（待审核工件）」；区分 R1–R9 设计 vs R10–R14 条件+工件；禁止勾选代替工件；明确不可定稿/冻结 |
| v1.1.2 | 2026-11-14 | Phase 0 工程落地 + §15 勾选建议稿；门禁绿；正式勾选仍待 owner |
| v1.1.3 | 2026-11-14 | owner 授权按建议稿正式勾选 R1–R9 + R10/R13/R14；R11/R12 仍开放；仍非定稿 |
| v1.1.4 | 2026-11-14 | Phase0 CI 绿；进入 Phase 1 工程预检；新增 `PHASE1_AUDIT_WORKSHEET`；仍非「5/5 已审计通过」 |
| v1.1.5 | 2026-11-14 | Phase 1 双人签字（朱向群/朱鸿林）；允许「首版 5/5 已审计通过」受限宣称；仍非定稿 |
| v1.1.6 | 2026-11-14 | Phase2 预备页；R11 阈值签字页；R12 evaluation-system 对账工件；§15→13/14 |
| v1.1.7 | 2026-11-14 | R11 owner 签字（朱向群 accept v0）；§15 14/14；方案按 §15.3 定稿冻结 |
| v1.1.7+exec | 2026-11-14 | 执行加料（不改结构）：`META_EVAL_V0`；R12 H1–H5 分诊（exempt/downgrade；H1_candidate 仍 open） |
| v1.1.7+exec2 | 2026-11-14 | R12 join 修（表首列）；H1 27 符号入 CAPABILITIES；`H1_candidate=0`；H5 仍 open |
| v1.1.7+exec3 | 2026-11-14 | H5 收紧（严格形 + 尾 `_`→H3 + H6 out_of_tranche）；[`TIER_MATRIX_V0.md`](../../../packages/aiplat-evaluation/docs/a3/TIER_MATRIX_V0.md)（A=19/B=160/C=458；≠授权） |
| v1.1.7+exec4 | 2026-11-14 | H5 跨域已登记→H6（open 73→9）；[`META_EVAL_FAMILY_CHECKLIST_V0.md`](../../../packages/aiplat-evaluation/docs/a3/META_EVAL_FAMILY_CHECKLIST_V0.md)（F1–F4 pending） |
| v1.1.7+exec5 | 2026-11-14 | R12 tranche-1 H5 open=0（补 5 SubjectAdapter；`eval_code_generator`/protocol/sets→H3，retrieval→H4）；≠ Tier A |
| v1.1.7+exec6 | 2026-11-14 | META_EVAL F1 状态工件（IAA 绿；judge/ECE 仍 open；`family_green=false`） |
| v1.1.7+exec7 | 2026-11-14 | F1 prep：holdout 声明 + contamination 扫描 + gold 抽样夹具 + judge pack pin；F1=3/5 |
| v1.1.7+exec8 | 2026-11-14 | F1 人裁判+confidence 齐：family_green=true（≠ Tier A authorize） |
| v1.1.7+exec9 | 2026-11-14 | META_EVAL F4 记分卡家族 5/5（依赖 F1 + scorecard_v1_check；≠ Tier A） |
| v1.1.7+exec10 | 2026-11-14 | META_EVAL F2 安全家族看板 3/5（F1≠安全裁判；待人标+dual-human） |
| v1.1.7+exec11 | 2026-11-14 | META_EVAL F3 G2b/process_split 边界 5/5（≠ 翻转 process_split_authorized） |
| v1.1.7+exec12 | 2026-11-14 | META_EVAL F2 人填包：安全裁判 worksheet(n=19)+dual-human；仍 3/5 待人 |
| v1.1.7+exec13 | 2026-11-14 | F2 CSV 人填面（judge/dual）+ import/score；仍待真人，禁 AI 预填 |
| v1.1.7+exec14 | 2026-11-14 | F2 安全人裁判 19/19 scored（agr=1 κ=1 ECE=0.05）→ 4/5；dual-human 仍开 |
| v1.1.7+exec15 | 2026-11-14 | F2 dual-human（朱莹/朱鸿林 · g2b-81）→ META_EVAL F1–F4 全绿；≠ Tier A/L5 |
| v1.1.7+exec16 | 2026-11-14 | META_EVAL 汇总 + Phase3 预备页；`meta_eval_families_green=true` 仍 ≠ 扩容授权 |
| v1.1.7+exec17 | 2026-11-14 | Phase3 A_candidate 19 符号工程清单（def/证据/缺口）；仍 ≠ 扩容授权 |
| v1.1.7+exec18 | 2026-11-14 | Phase3 B 复核日历草稿 + A/B/C 覆盖报表骨架；仍 ≠ 扩容/覆盖完成 |
| v1.1.7+exec19 | 2026-11-14 | Tier A 扩序 + 提案#1 `evaluate_judge_calibration_gate`（pending owner；≠ 已授权） |
| v1.1.7+exec20 | 2026-11-14 | owner ACCEPT #1 scoped gate；账本 1 符号；开提案#2；全局扩容仍 false |
| v1.1.7+exec21 | 2026-11-14 | owner ACCEPT #2 `open_capability_judge_calibration`；账本 2 符号；开提案#3 |
| v1.1.7+exec22 | 2026-11-14 | owner ACCEPT #3 `judge_calibration_gate_for_ticket`；账本 3 符号；开提案#4 κ |
| v1.1.7+exec23 | 2026-11-14 | owner ACCEPT #4 `cohen_kappa_binary`；账本 4 符号；开提案#5 Wilson CI |
| v1.1.7+exec24 | 2026-11-14 | owner ACCEPT #5 `wilson_score_ci`；F1 impl 链齐；开提案#6 facade |
| v1.1.7+exec25 | 2026-11-14 | owner ACCEPT #6 `eval_judge_calibration_gate` facade；开提案#7 |
| v1.1.7+exec26 | 2026-11-14 | owner ACCEPT #7 facade；F1 A_candidate 7/7 scoped；开提案#8 F4 scorecard |
| v1.1.7+exec27 | 2026-11-14 | owner ACCEPT #8 `build_release_scorecard`；开提案#9 evidence-pack |
| v1.1.7+exec28 | 2026-11-14 | owner ACCEPT #9 evidence-pack；F4 2/2 scoped；开提案#10 F2（≠ L5） |
| v1.1.7+exec29 | 2026-11-14 | owner ACCEPT #10 F2 security judge；开提案#11 defaults（≠ L5/cert） |
| v1.1.7+exec30 | 2026-11-14 | owner ACCEPT #11 defaults；开提案#12 family gates（≠ cert） |
| v1.1.7+exec31 | 2026-11-14 | owner ACCEPT #12 family gates；F2 impl 3/3；开提案#13 facade |
| v1.1.7+exec32 | 2026-11-14 | owner ACCEPT #13 F2 facade；开提案#14 defaults facade |
| v1.1.7+exec33 | 2026-11-14 | owner ACCEPT #14 defaults facade；开提案#15 family-gates facade |
| v1.1.7+exec34 | 2026-11-14 | owner ACCEPT #15 family-gates facade；开提案#16 L5-gate API（≠ declare） |
| v1.1.7+exec35 | 2026-11-14 | owner ACCEPT #16 L5-gate API；`l5_declare` 仍 false；F2 7/7；开提案#17 F3 |
| v1.1.7+exec36 | 2026-11-14 | owner ACCEPT #17 F3 assert；`process_split` 仍 false；开提案#18 dual-review |
| v1.1.7+exec37 | 2026-11-14 | owner ACCEPT #18 dual-review；开提案#19 末 facade（≠ process_split / 全局扩容） |
| v1.1.7+exec38 | 2026-11-14 | owner ACCEPT #19 末 facade；A_candidate 19/19 scoped 齐；全局扩容仍 false |
| v1.1.7+exec39 | 2026-11-14 | 覆盖率骨架 A 行实测（19/19）；scoped 闭环文；开 B1 suite 挂接提案 |
| v1.1.7+exec40 | 2026-11-14 | owner ACCEPT B1 suite 挂接（13 smoke+agent+Eval partial）；开 B2 提案 |
