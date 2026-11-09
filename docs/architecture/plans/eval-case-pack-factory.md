# Eval Case Pack 工厂 — 设计基线 + 实施进度

> **类型**：架构方案 / 实施契约  
> **版本**：v0.6.0 · 2026-11-08  
> **状态**：**P0–P3.1**（LLM 候选 + 难度人标校准 + judge 开单→打分→关单；仍不可 claim）· PR #622 · 基线会签栏仍见 §8.1（人工签字另轨）  
> **关联**：[`eval-object-contract-and-plan.md`](./eval-object-contract-and-plan.md) · [`eval-trust-boundary-lab-vs-cert.md`](./eval-trust-boundary-lab-vs-cert.md) · [`workspace-isolation-contract.md`](./workspace-isolation-contract.md) · #618 `derived_hints`  
> **诚实锁**：不打开 `accuracy_claim`；L3 生成题不可 claim；禁止运行时随机出题当金标；G2b/Arena 另轨  

---

## 0. 一句话

**L1 冻结保可比 · L2 人审保覆盖 · L3 生成保发现；Plan 升 v2 负责选池/过滤/采样并输出 `sample_manifest`；Runner 只执行 manifest。**  
P0–P3.1 已接线：工厂链 + 变异/trace/holdout + LLM 候选（默认 dry）+ 难度启发式/人标校准 + judge 持久化工单闭环；L3 禁 freeze 入 claim；未开 accuracy_claim。

```text
种子/模板/trace/变异/LLM候选
        ↓ Case Factory（generate→validate→dedupe→review→freeze）
Case Pack（version + hash + scope + claim_eligible）
        ↓ Plan v2（filter + sample + seed）
sample_manifest（唯一执行依据）
        ↓ Runner（hash fail-closed；无整包回退）
报告（pack_kind / claim_eligible / plan_id / manifest_hash / execution_fingerprint）
```

---

## 1. 现状锚点（代码事实）

| 项 | 事实 |
|----|------|
| Plan schema | `PLAN_SCHEMA = "eval.evaluation_plan.v1"`（`eval_plan.py`） |
| 选题单位 | **卷** `set_id`；非题 |
| 题库 | `core/engine/eval_sets/*.json` → `ensure_builtin_sets()` → `~/.aiplat/eval_sets/` |
| 任务模型 | `EvalTask` / `EvalSet`（`eval_types.py`） |
| #618 | 仅 `profile_source=explicit` 时缺 capability → N/A |
| 工作区 | Eval 一期隔离 Agent/结果；packs 必须显式 `scope`，不得默认串 workspace |
| 独立基准 | G2b / Arena / S1 ≠ 本 Plan 出题链 |

---

## 2. P0 前六钉（必须签字；缺一不开工）

### 钉 1 — Plan schema 升 `v2`，禁止偷改 v1

| 规则 | 要求 |
|------|------|
| 新路径输出 | `schema: "eval.evaluation_plan.v2"` |
| v1 | **只读兼容投影**；不得在 v1 上 silently 塞入 manifest 语义 |
| `selected_cases`（v2） | **legacy 投影**（卷/包级摘要），**不是**执行清单 |
| 消费者 | UI / 报告 / 测试必须按 `schema` 分支；禁止假定 `selected_cases` 仍等于「要跑的卷」 |

**v2 必选字段（增量）：**

```json
{
  "schema": "eval.evaluation_plan.v2",
  "plan_id": "plan-...",
  "pack_ref": {"pack_id": "...", "version": "...", "hash": "sha256:..."},
  "selection": {
    "mode": "legacy_sets|pack_filter_sample",
    "set_ids": [],
    "filter": {},
    "sample_n": null,
    "seed": null,
    "strategy": "all|random|stratified"
  },
  "sample_manifest": [
    {"case_id": "...", "hash": "...", "pack_id": "...", "pack_version": "...", "session_group": null}
  ],
  "manifest_hash": "sha256:...",
  "coverage": {},
  "legacy_set_projection": [],
  "selected_cases": [],
  "excluded_cases": [],
  "eval_profile_source": "explicit|derived_hints|null",
  "honesty": "..."
}
```

v1 投影规则：若调用方仍要 v1，由适配层把 v2 的入选 pack/`set_id` 压成旧 `selected_cases`，并标注 `projected_from: v2`；**不得**让 Runner 读 v1 投影执行。

### 钉 2 — `sample_manifest` 是唯一执行依据

> **Runner 只认 `sample_manifest`。`selected_cases` / `set_ids` 仅选题说明与 legacy 投影，不是执行清单。**

| 条件 | 行为 |
|------|------|
| `sample_manifest` 缺失或 `[]` | **fail closed**（新路径） |
| 任一 `case_id` 不在 pack | fail closed |
| 任一 case `hash` ≠ pack 内 canonical hash | fail closed |
| `pack_ref.version` / hash 不存在或不匹配 | fail closed |
| manifest 失败后回退「整包全跑」 | **禁止** |

迁移期仅允许：`mode=legacy_sets` 编译时**先展开**为全量 `sample_manifest`，再交给 Runner——Runner 仍只见 manifest。

### 钉 3 — 三套指纹分离

| ID | 作用 | 至少纳入 hash 的内容 |
|----|------|----------------------|
| `plan_id` | **选题方案**指纹 | `plan_schema` + target 关键字段 + `pack_id/version/hash` + filter + seed + strategy + `sample_n` + purpose + `manifest_hash` |
| `manifest_hash` | **实际跑了哪些题** | canonical 序列化的 `sample_manifest[]`（按 `case_id` 排序） |
| `execution_fingerprint` | **一次执行** | `plan_id` + `manifest_hash` + runner_id + judge/oracle 版本 + model（若有）+ UI `run_key` 序列（含 `#2` 复跑） |

**禁止**用旧 `_plan_id`（仅 object + selected set_ids + purpose）冒充 v2 可比指纹。

### 钉 4 — Hash canonical 规范

#### Case hash

**纳入（排序后 JSON canonical、UTF-8、`separators=(',',':')`、`ensure_ascii=False` 再 sha256）：**

- `case_id`, `prompt`（或归一后的 `user_input`）, `rubric`（或归一后的 `success_criteria`）
- `category`, `tags`（排序）, `difficulty`
- `applies_to`, `requires`, `oracle`
- `expected_tools` / `forbidden_tools` / `expected_steps`（排序）
- `risk_level`, `session_group`, `holdout`
- `provenance.generator`, `provenance.generator_version`, `provenance.seed`

**排除：**

- `review.*`（含 notes/status/reviewed_at）
- 运行期绑定 `agent_id`
- 文件路径、本地绝对路径
- 任意非 schema 扩展除非列入白名单

#### Pack hash

纳入：`pack_id`, `version`, `kind`, `claim_eligible`, `scope`, `object_types`（排序）, 各 case 的 **case hash 列表（按 case_id 排序）**。  
**排除：** registry 缓存时间戳、review 队列状态。

#### 冻结规则

修改 `frozen` pack **禁止原地改文件**；只能 `version++` 且 pack hash 必须变。CI 对 git 中 `kind=frozen` 内容做 ratchet。

### 钉 5 — `scope` + ACL + registry 原子写

对齐 [`workspace-isolation-contract.md`](./workspace-isolation-contract.md)：workspace ≠ tenant；header 是选择器不是凭证。

```json
"scope": "global|workspace|tenant"
```

| scope | 含义 | 默认 ACL |
|-------|------|----------|
| `global` | 内置 / 平台级基准镜像 | 全租户只读；仅平台发布角色可发新 version |
| `workspace` | 命名工作区私有题库 | 仅该 workspace ACL 可读写；**跨 workspace 引用禁止** |
| `tenant` | 租户共享（若启用） | 同 tenant 策略；跨 tenant 禁止 |

**存储（建议）：**

```text
# global / builtin（只读）
aiPlat-core/core/engine/eval_sets/packs/{pack_id}/{version}.json

# workspace（可写）
$AIPLAT_HOME/workspaces/{workspace_id}/eval_packs/{pack_id}/{version}.json
# default workspace 兼容映射须书面写清，禁止 silent 落到无关目录

# tenant（可选二期）
$AIPLAT_HOME/tenants/{tenant_id}/eval_packs/...
```

**Registry：**

- 每 scope 一份 `registry.json`
- **原子写**（temp + `os.replace`）+ **文件锁**
- 并发 create 同一 `(pack_id, version)` → 一方失败，文件不损坏
- 弃用：`status=deprecated`；删除策略：frozen 不可删，仅 deprecated + 保留期

**用户改过的旧路径：**  
`~/.aiplat/eval_sets/**` 若与内置 hash 不同 → 视为 **user overlay**；`ensure_builtin_*` **禁止覆盖**；迁移到 pack 时标记 `source=user_overlay` 并提示升级，不静默抹掉。

### 钉 6 — 旧 `EvalTask` / `EvalSet` 字段映射（bit 兼容）

现字段（`eval_types.EvalTask`）：  
`task_id, agent_id, user_input, category, expected_tools, forbidden_tools, expected_steps, success_criteria, risk_level`

| 新字段 | 旧字段 / 规则 |
|--------|----------------|
| `case_id` | = `task_id`（legacy 视图） |
| `prompt` | **读优先** `prompt`；否则 `user_input`；写入双写过渡期 |
| `user_input`（投影） | = `prompt`（保证旧 Runner 可读） |
| `rubric` | **读优先** `rubric`；否则把 `success_criteria` 包成 `{type: lexical, ...}` |
| `success_criteria`（投影） | 从 `rubric` 可逆投影；无法投影则保留原 dict |
| `agent_id` | **不属于 case 内容**；执行绑定时注入；hash **排除**；缺省 = Plan 目标 `object_id` |
| `tags` | 缺省 `[category]` |
| `difficulty` | 缺省 `medium` |
| `session_group` | multi_turn 卷：整卷共用 `set_id` 作为 group id |
| `applies_to` / `requires` / `oracle` | 来自 applicability_draft 下沉模板；case 可覆盖 |

**`load_eval_set("default/normal")` 验收：**

1. 映射 `pack_id=agent.default.normal` / `version=1.0.0`（命名表冻结在附录 A）  
2. 投影回 `EvalSet` 后，对 **内置未改动** 包：`tasks` 序列化与改造前 **bit-identical**（或规范化后 hash identical，规范须在测试夹具写死）  
3. 用户 overlay 存在时：加载 overlay，**不**被 builtin 覆盖  

---

## 3. 三个设计缺口（一并锁定）

### 3.1 多轮：`session_group` 不可拆散

| 规则 | 要求 |
|------|------|
| 采样单位 | 逻辑上可以是 case，但带同一 `session_group` 的 case **必须整组入选或整组落选** |
| 推荐策略 | 先抽 group，再 group 内 **全取** |
| manifest | 每条含 `session_group`；同组顺序固定（`case_id` 排序或显式 `turn_index`） |
| 禁止 | 只抽到 `mt-002` 而无 `mt-001` |

### 3.2 Stratified sampling 最小样本

| 规则 | 要求 |
|------|------|
| 每层最小 | 默认 **≥1**（可配置，但不得静默改） |
| 层不足 | **报错或显式降级**（写入 Plan `selection.degraded` + reasons）；禁止静默改配额 |
| 落盘 | seed、各层配额、实际抽中数写入 manifest 旁路元数据或 `selection.quota_trace` |

### 3.3 `claim_eligible` 执行门（非装饰字段）

| 门 | 要求 |
|----|------|
| 字段 | `generated` / exploratory → `claim_eligible` **恒 false** |
| CI | `generated + claim_eligible=true` → **阻断** |
| Scorecard / 正式报告 | 读取 `claim_eligible`；false 的 pack **不得**进入 accuracy/claim 聚合 |
| 报告披露 | 强制 `pack_kind` + `claim_eligible` |
| L1 候选 | 仅 `frozen + reviewed`；仍须外部 protocol / attestation 才可能 claim（默认仍 false） |

---

## 4. Match / N/A（继承 #618）

| 条件 | 决策 |
|------|------|
| object_type 不匹配 | `not_applicable` |
| 缺 tool / permission / runtime | `not_applicable` |
| 缺 capability + `explicit` | `not_applicable` |
| 缺 capability + `derived_hints\|unknown` | **selected** + `capability_unconfirmed:*` |
| special 未开 purpose | `untested` |
| refuse_or_handoff 例外 | 保留 |

Case 级匹配为主；卷级 draft = 默认模板。

---

## 5. 三层题库与工厂（摘要）

| 层 | kind | claim_eligible |
|----|------|----------------|
| L1 | `frozen` | 仅 reviewed+frozen 可**候选**；默认仍 false |
| L2 | `curated` | 默认 false |
| L3 | `generated`/`trace` | **恒 false** |

工厂：`generate → validate → dedupe → human_review → freeze`  
路径优先级：模板 → trace → 变异 → LLM 候选（最后）。

G2b / Arena / S1：**另轨**；本方案最多只读 import 镜像，不吞并协议权威。

---

## 6. 现实排期（修订）

| 阶段 | 内容 | 周期 |
|------|------|-----:|
| **契约冻结** | 本文件 §2–§3 评审签字 | 前置 |
| **P0** | v2 Plan + manifest 唯一执行 + hash + scope/registry + EvalTask 映射 + 多轮 group + 旧测兼容 | **2–3 周** |
| **P1** | 模板生成 + 人审队列 + 每包扩题 + coverage + stratified | **4–6 周** |
| **P2** | trace / 变异 / holdout | **4–6 周** |
| **P3** | LLM 候选 + 难度校准 + judge 校准工单 | **4–8 周** |

P0 **不以「1–2 周」承诺**。P1 扩题依赖审核人力，进度与「谁审、题从哪来」绑定。

---

## 7. P0 验收测试清单（契约级）

| # | 测试 | 要求 |
|---|------|------|
| T1 | 旧路径 bit 兼容 | 内置 6 卷投影后与改造前一致（或规范化 hash 一致） |
| T2 | manifest 稳定性 | 同 seed/filter/strategy 两次 `sample_manifest` 字节级一致 |
| T3 | hash 校验 | 改一个 case 内容 → 旧 manifest fail closed |
| T4 | 多轮采样 | 不会拆散 `session_group` |
| T5 | 用户 overlay | 改过的 `eval_sets` 不被 `ensure_builtin` 覆盖 |
| T6 | registry 并发 | 双 create 不损坏；一方失败 |
| T7 | claim 守卫 | `generated + claim_eligible=true` 被拒（CI+运行时） |
| T8 | 缺 manifest | 新路径 fail closed；**无**整包回退 |
| T9 | #618 回归 | derived_hints 缺 capability → selected + unconfirmed |
| T10 | scope/ACL | workspace A 不能读 B 的 `scope=workspace` pack |
| T11 | 指纹分离 | 改 UI run_key 只变 `execution_fingerprint`，不变 `manifest_hash` |
| T12 | stratified 不足 | 层不足时报错或显式 degraded，不静默改配额 |

---

## 8. 开工门禁（Go / No-Go）

**Go P0** 当且仅当：

1. 本文件 §2 六钉经产品负责人 + 评测方法负责人会签；  
2. 附录 A（set_id↔pack_id 表）与附录 B（hash 测试向量）已填；  
3. 变更单写明：不触及 G2b/Arena claim、不打开 `accuracy_claim`。  

**No-Go：** 六钉未签、或试图在 v1 上偷加字段、或允许 manifest 失败回退整包。

### 8.1 会签栏（PR #621 / 实施跟踪 #622）

| 角色 | 勾选范围 | 签字（GitHub Approve / 评论 `SIGNED §2`） | 日期 |
|------|----------|------------------------------------------|------|
| 产品负责人 | 钉 1–3、§3.3 claim 门、§6 排期 | | |
| 评测方法负责人 | 钉 4–6、§3.1–3.2、附录 A/B | | |
| 工程负责人（可选） | T1–T12 可测性、存储路径与 ACL | | |

合并本 PR **≠** Go P0；仅表示基线入库。Go 须上表两名必签角色齐 + 单独开 P0 变更单。

**工程进度（#622，非会签替代）**：P0–P3.1 代码已接线（含难度人标 + judge 闭环）；诚实锁未破。人工会签仍须上表。

---

## 9. 附录 A — 旧 `set_id` → `pack_id`（冻结表 · 待填版本号）

| 旧 set_id | pack_id | 初始 version |
|-----------|---------|--------------|
| `default/normal` | `agent.default.normal` | `1.0.0` |
| `default/missing_info` | `agent.default.missing_info` | `1.0.0` |
| `default/tool_failure` | `agent.default.tool_failure` | `1.0.0` |
| `default/noise` | `agent.default.noise` | `1.0.0` |
| `default/high_risk` | `agent.default.high_risk` | `1.0.0` |
| `default/multi_turn` | `agent.default.multi_turn` | `1.0.0` |
| `prompt/*` | `prompt.<stem>` | `1.0.0` |
| `workflow/*` | `workflow.<stem>` | `1.0.0` |
| `model/*` | `model.<stem>` | `1.0.0` |

（实施前锁定；改名须升本附录版本。）

---

## 10. 附录 B — Hash 测试向量（冻结 · 2026-11-08）

**算法（与钉 4 一致）：** 取纳入字段 → list 字段排序（`tags`/`expected_tools`/`forbidden_tools`）→ `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(',',':'))` → UTF-8 → `sha256:` + hex。  
Pack：`pack_id/version/kind/claim_eligible/scope/object_types(sorted)` + `case_hashes[{case_id,hash}]`（按 `case_id` 排序）。

**Fixture A（canonical 字节串）：**

```text
{"applies_to":{},"case_id":"fixture-a-001","category":"normal","difficulty":"medium","expected_steps":[],"expected_tools":["code_generation"],"forbidden_tools":[],"holdout":false,"oracle":{},"prompt":"echo hello","provenance":{"generator":"manual","generator_version":"0","seed":null},"requires":{},"risk_level":"low","rubric":{"must_contain":["hello"],"type":"lexical"},"session_group":null,"tags":["normal"]}
```

| 夹具 | 期望 |
|------|------|
| 最小 case fixture A | `case_hash = sha256:f82bc84cdd2b83fb4dd01c8ec5985abfa1bea44c3f1e77906c0d0660cca80c61` |
| 仅改 `review.notes` / `review.status` | case_hash **不变**（同上） |
| 改 `prompt` → `echo hello!` | `sha256:9b1046c3de99d194f2d0c2e27d03c489199f5e0034b702357c0ff54de07f3916`（**变**） |
| Fixture B (`fixture-a-002`, prompt=`echo world`) | `sha256:457fda9cde2ec70ff82c821e633858ce226dec2f0b64ea708078b4eda4930703` |
| Pack `fixture.pack@1.0.0` kind=frozen claim=false scope=global object_types=[agent]，含 A+B | `pack_hash = sha256:fab6005f50da43f7bbf393a6adc6d9703af67ad16a03443ba4e219db9373806b` |
| 两 case **写入顺序对调** 的同一 pack | pack_hash **不变**（同上） |

P0 实现必须用同一算法复现上表；算法变更须升本附录日期并重算向量。

---

## 11. 结论

- **方向正确**：L1/L2/L3 + Factory + Plan v2 + manifest 唯一执行 = 正解。  
- **成熟度**：可作为**正式架构评审基线（8.5/10 级反馈已吸收）**。  
- **不可直接进 P0**：先完成 §2 六钉会签 + 附录 A/B + §8 Go。  

**一句话：** 先钉死 schema v2、manifest 唯一执行、三套指纹、hash、scope/ACL、EvalTask 映射（外加多轮 group / stratified / claim 门），再开 P0；现在写代码 = 违规开工。
