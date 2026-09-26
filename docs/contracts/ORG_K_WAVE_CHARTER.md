# K 波 Charter — 带闸门的本体进化环

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-K-WAVE-CHARTER-2026-09` |
| 版本 | **v1.6**（F2 直写门禁） |
| 日期 | 2026-09-18 |
| 状态 | ☑ **K0–K5** · ☑ **F2 直写已拒绝** · ☐ 不称 M4/L5 |
| 关联 | [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |
| 决策 | D-K1–D-K5 见 Decision Record §6 |

**纪律**：K0–K5 已落地。活 YAML 直写（编辑保存、wiki 写回/生成域/删除、importer、编辑器 CRUD、规则 deploy）在 `allow_live_yaml_write` 之外会拒绝。允许令牌只包住 `apply_proposal` 与 `rollback_proposal`。不得说出错已变成规则。不称 M4/L5。

---

## 0. 一句话

冷启动草稿 → 人审后的对齐仲裁 → 可回放推理路径 → 案例 overlay → 人批提案。草稿、仲裁、路径、案例、提案都不是本体。K 波与 Phase C 分开，共享 `trace_id` / `ActionStore` / 权限模型，互不替代，也不替代 M4。

---

## 1. 与 Phase C / M4

| 轨道 | 管什么 | 不管什么 |
|------|--------|----------|
| Phase C | 渠道、Interface、岗位、用量、签收包 | 本体进化 |
| K 波 | 本体进化环 | 飞书入站、M4 签字 |
| M4 | 客户真线 + 双签 | 不因 K 波完成而关闭 |

`m4_claim_allowed` 恒 false。`AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY` 默认 false，K 波不打开它。

---

## 2. 非目标（当前阶段）

不做：代码自动生成业务本体；对话微调；错一次改 prompt、再错自动硬编码；三路隐藏关系挖掘；CRM/财务/人力或第二入站渠道；harness 里 `if domain_id ==`；edge 自动 apply 默认开启；用本环替代 M4。

解禁条件不在本文。单线闭环、M4 签收、评测与回滚齐备之前，这些仍是非目标。

---

## 3. 代码事实（2026-09-18 核验）

K0 当时的结论是直写旁路存在。2026-09-18 已加门禁：无 `allow_live_yaml_write` 不得覆盖活 YAML。令牌只在 `apply_proposal` / `rollback_proposal` 内打开。

| # | 断言 | 事实 | 证据 |
|---|------|------|------|
| F1 | `CrossDomainResolver.resolve` 直接写边 | **部分关闭（HTTP）**。生产写边走 `apply_ticket`。E2 只撤回带 `edge_before` 的 merge 边 | `k_wave_arbit.py`；[`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md) |
| F2 | `apply_proposal` 是唯一活 YAML 写入口 | **直写已拒绝（2026-09-18）**。编辑保存、wiki 写回/生成域/删除、importer、编辑器 CRUD、规则 deploy 在令牌外抛错；HTTP 409。令牌只在 apply/rollback 内打开 | `ontology_yaml_gate.py`；`save_domain_yaml`；`_write_domain_yaml`；`import_ontology`；`create/update/delete_ontology_domain`；`upsert/delete_ontology_class`；`deploy_rule`；`versioned_ontology_store.py` `allow_live_yaml_write` |
| F3 | `auto_apply` 可被环境变量打开 | **成立**。默认关。打开后 `maybe_enqueue_evolution_proposal` 会走 `try_auto_apply_edge_proposal` | `ontology_case_learning.py` `_edge_auto_apply_enabled`；env `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY` |
| F4 | `trace_id` 已贯穿抽取、仲裁、案例、提案 | **回放已落地，写入侧继承仍未强制**。字段在。只读回放与冲突规则见 V 波 Charter §3。生产里五步同号仍取决于记录是否已经共用一个 id | `v_wave_replay.py`；`k_wave_signal.py`；`org_runtime.py` |
| F5 | `PolicyGate` 覆盖提案审批 | **HTTP 已覆盖（V4）**。`POST …/proposals/{id}/approve` 只认 `X-AIPLAT-ROLE`，`decide_ontology_approval` 判一次。旧的 `approve_proposal` 默认路径仍在，HTTP 传 `gate_passed=True` 不再用 body 角色授权 | `k_wave_approve.py`；`policy_gate.py`；`extraction_routes.py` |
| F6 | `rollback_case_evolution` 覆盖一切回滚 | **不成立**。只回滚已挂上的 store 提案。`draft_local_*`、`k5_local_*`、`resolve()` 写下的边、没有提案 id 的案例都不回滚。边界见 `GET …/org/rollback/scope` | `ontology_case_learning.py`；`k_wave_rollback.py` |

`governance_loop.py` 是 data-gov 八步只读地图，不是第二条进化环。

---

## 4. 已冻结决策（D-K1–D-K5）

| ID | 决议 |
|----|------|
| D-K1 | 试点只 it-ops。data-gov 不并行第二套环 |
| D-K2 | 沿用现有 FDE 审批身份。抽取确认、仲裁批准、提案批准必须分开记 actor，不得只留一个「已批」布尔 |
| D-K3 | 重复错误：滚动窗口内 ≥3 次，或 2 次且 `reward_ema` 低于 `AIPLAT_ONTOLOGY_EVOLVE_MIN_REWARD`。同一键去重、合并、过期。不写死「2 次即提案」 |
| D-K4 | 不生成 `SKILL.md`。只允许案例元数据 `skill_candidate=true` |
| D-K5 | 精确键也不自动合并。只出「建议合并」单，人点一次 |

---

## 5. trace 起点

抽取确认时生成 `trace_id`（尚未有 OrgRun）。变更信号同时带 `signal_id` 与该 `trace_id`。

之后若 OrgRun 由该信号触发，Run 必须继承这个 `trace_id`，禁止另造一个再声称同源。没有信号的直接 Run 用自己的 `run_id` 作本地 trace，并标明 `trace_origin=run`，不得回填到更早的抽取单。

K1 确认会生成 `trace_id` 并写入信号。仲裁、案例、Run 可以带 `trace_origin`，但尚未按 V 波闭集强制继承。缺一环只记「该步未发生」，不补假记录。回放规则以 V 波 Charter §3 为准。

---

## 6. 仲裁状态机

状态：`pending` → `approved` | `rejected` | `deferred` | `conflict`。`approved` 之后若新证据否定旧结论，旧单变 `superseded`，不改历史。

| 状态 | 含义 | 允许的副作用 |
|------|------|----------------|
| pending | 待批 | 无 |
| approved | 人批了合并或新增 | 此后才允许调用现有 `resolve()` 或写入图节点 |
| rejected | 否认同一对象 | 不写边 |
| deferred | 证据不足 | 不写边；见超时 |
| conflict | 两边证据打架 | 不写边；升级到提案批准人 |
| superseded | 被更新的单替代 | 只保留审计 |

超时：`deferred` 14 天无新证据 → `rejected`（可再开一单，不复活旧单）。`conflict` 7 天无人处理 → 保持 `conflict`，不得自动合并。

租户：左右实体 `tenant_id` 都非空且不一致 → 直接 `rejected`，理由 `cross_tenant`。K 波不提供批量批准 API。状态机预留 `batch_id`，留空。

权限：三类动作分开审计，本阶段不新建角色名。

| 动作 | 记录字段 | 不能做 |
|------|----------|--------|
| 抽取确认 | `extract_actor` | 不写活 YAML，不写跨域边 |
| 仲裁批准 | `arbit_actor` | 不调用 `apply_proposal` |
| 提案批准 | `proposal_actor` + 现有 `approver_role` | 不把 PolicyGate 策略塞进本体提案 |

同一人可以先后做两步，但两条审计都要在。禁止一个请求里同时确认抽取并写边。

---

## 7. K4 / K5 口径

**K4 连续失败**：同一次 Run 内，同一工具或动作名、同一错误类，连续两次 `tool_call` 失败。跨 Run 不算连续。`OnErrorReflector` 仍只注入当次 hint；额外写失败案例。不改 prompt 存储，不写规则。

**K5 聚合键**：`domain_id + action_id + error_code`，跨 Run，受 D-K3 门槛约束。提案去重键与聚合键相同；未批提案不重复创建；超过 30 天未批 → `expired`，不自动 apply。

**K5 提案边界**：只允许 `VersionedOntologyStore` 已支持的 edge 层类新增。不得用提案修改 `PolicyGate`。「失败则 HITL」若不能表达为现有本体类变更，就不进 `apply_proposal`，本波不做单独策略库。

`rollback_case_evolution` 只承诺回滚已挂上的 store 提案。K5 不把直接写 YAML 或 `resolve()` 的边算进可回滚范围，除非以后单独立项把那些旁路接上同一提案。

---

## 8. 数据安全（K1 前必须遵守的设计，本波不新写执行码）

| 项 | 要求 |
|----|------|
| 输入 | 文档 / PDF / Word 默认含敏感数据。进 LLM 前要有脱敏挂钩；K1 若挂钩不存在，抽取只允许明示的试点样本，不扫目录 |
| 访问 | 待审抽取、仲裁单、案例按 `tenant_id` 隔离。不跨租户列出 |
| 保留 | 待审与驳回单保留期写在实现配置，不进本文数字承诺。驳回正文不得进案例摘要 |
| 供应商 | 抽取调用的模型不用于训练。不把原文写入用量账本 |
| 审计读 | 与写入同一租户。提案审计继续落 `ActionStore`；这不等于 PolicyGate 已包住批准 |

---

## 9. 阶段与话术

| 阶段 | 关闭证据 | 本文件状态 |
|------|----------|------------|
| K0 | 本文 + Decision Record §6 | ☑ 2026-09-18 |
| K1 | 确认抽取不改活 YAML 哈希；确认时发出带 `trace_id` 的信号 | ☑ **2026-09-18** `POST …/extractions/{id}/confirm` → K1 |
| K2 | 未批准不调用 `resolve()` | ☑ **2026-09-18** 仲裁单 + decide/apply |
| K3 | Run 上有路径或显式 skip | ☑ **2026-09-18** `step=reasoning`；`can_execute=false` |
| K4 | 案例可检索；不改 TBox；无 Skill 文件 | ☑ **2026-09-18** OrgRun + 同 Run 同工具同错误连续 2 次 |
| K5 | 达门槛只提案；`auto_apply=false`；人批才 apply | ☑ **2026-09-18** `POST …/k5/scan`；30 天未批过期 |

未完成 K1 不说自动建模。K5 已落地，仍然不说出错已变成规则。F2 直写已拒绝，仍不称全域闭环或 L5。竖切验收见 V 波，不在本文开工。

---

## 10. 宣布用语

> K 波 K0 于 2026-09-18 生效。方向是带闸门的本体进化环。代码事实：跨域 `resolve()` 会直接写边；活 YAML 另有 `save_domain_yaml` 与 wiki `_write_domain_yaml`；`trace_id` 尚未贯穿；edge 自动 apply 默认关但可被环境变量打开。K1 未开工。不称 L5。

**宣布用语（K1）**：  
> K 波 K1 于 2026-09-18 落地：抽取确认只发变更信号（`signal_id` + `trace_id`），活 YAML 哈希不变，不写跨域边。HTTP `POST …/extractions/{id}/confirm` 走 K1。不称自动建模已闭环。K2 未开工。

**宣布用语（K2）**：  
> K 波 K2 于 2026-09-18 落地：`POST …/resolution/resolve` 只开仲裁单；`decide` 后人 `apply` 才调用 `resolve()` 写边；跨租户直接拒；精确键也不自动合并。K3 未开工。

**宣布用语（K3）**：  
> K 波 K3 于 2026-09-18 落地：OrgRun 增加 `reasoning` 步骤与 `reasoning_paths`（或 `skipped=no_entity|no_path|graph_error`）；`can_execute` 恒 false；动作仍过 triage_gate / Interface。K4 未开工。

**宣布用语（K4）**：  
> K 波 K4 于 2026-09-18 落地：OrgRun 结束写案例；同一次 Run 内同工具同错误连续两次写失败案例；只 overlay，不改 TBox，不生成 SKILL.md；成功 Run 可标 `skill_candidate=true`。K5 未开工。

**宣布用语（K5）**：  
> K 波 K5 于 2026-09-18 落地：`POST …/k5/scan` 按 `domain+action+error` 聚合；窗口内 ≥3 次或 2 次且 reward 低于门槛才出 edge 提案；`auto_apply=false`；未批提案不重复；超 30 天过期不 apply。这不是「出错已变成规则」。同日稍后 F2 门禁见下。

**宣布用语（F2 门禁）**：  
> 2026-09-18：活本体 YAML 的编辑保存、wiki 整文件写回、importer 在批准令牌外拒绝。令牌仅 `apply_proposal` / `rollback_proposal` 持有。这不是 M4，也不等于出错已变成规则。
