# 本体运行时权威契约（Ontology Runtime Authority）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-RUNTIME-AUTHORITY-2026-09` |
| 版本 | v1.0 |
| 状态 | 生效 |
| 关联 | [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md) |
| 维护人 | Oliver Zhu |

---

## 1.1 axioms 分布基线（2026-09-15）

| 范围 | axioms | 说明 |
|------|-------:|------|
| 28 域 YAML（加载前） | 0 | 结构预留未用 |
| `lock-service`（P1 后） | 4（LS-A1…A4） | 已加载；compiler 优先域公理 |
| Wiki 全局 AXIOMS | 8 | 知识库轨道；业务路径勿单独依赖 |

报告脚本：`PYTHONPATH=aiPlat-core python3 scripts/report_domain_axioms.py`

---

## 1. 双轨权威（业务 vs 知识库）

| 场景 | 权威 | 说明 |
|------|------|------|
| Action 可否执行、实体状态、审计前后快照 | **域 GraphIndex + 域 YAML** | Wiki 不进审计链 |
| 业务域检索 / GraphRAG / FDE 交付对象 | **域 GraphIndex** | |
| 平台知识库问答、文档编译 Wiki | Wiki TBox/ABox | 不得冒充客户业务本体 |
| 冲突时 | 域胜出；Wiki 仅 warning | UI 标注「知识库定义，非业务权威」 |

**配置源**：`~/.aiplat/ontologies/registry.json` + `~/.aiplat/ontologies/{domain_id}.yaml`  
**运行时权威**：`DomainRouter`（`list_domains` / `require_known_domain` / classify）  
不以「磁盘有 YAML 但未进 registry」为已注册。

---

## 2. 约束三层（L1 > L2 > L3）

| 层 | 组件 | 性质 | 失败后果 |
|----|------|------|----------|
| L1 硬门 | `ActionRegistry.check_entity_constraints` | 必须否决非法动作 | 阻塞执行 |
| L2 软约束 | `ontology_constraint_compiler` → prompt | 降低胡言；可被模型忽略 | **不得**单独作为安全边界 |
| L3 审计 | ActionStore entity_snapshot / before/after | 事后可追责 | 不替代 L1 |

顺序：**prompt 失误 → 执行层兜底 → 审计留痕**。  
任何「仅 L2、无 L1」的高风险动作禁止进入 `customer_action` 生产路径。  
业务路径的 L2 必须编译**当前域** axioms/required_fields，不得只用 Wiki 全局 `AXIOMS`。

---

## 3. Action 命名空间 ↔ 域本体

- `required_state` / `forbidden_states` / `target_class` / `domain_id` **对 `customer_action` 与 `platform_action` 均生效**（硬门与命名空间正交）。
- `customer_action:{domain}:{name}` 的 `{domain}` 必须 ∈ `DomainRouter.list_domains()`，且与合同 `domain_id` 一致。
- `platform_action:*` 可跨域；若 `scope=DOMAIN` 仍受域状态机约束。
- 试点域（lock-service）禁止新增 legacy（空 `action_namespace`）Action。

---

## 4. 审计快照权威

- `before_state_snapshot` / `after_state_snapshot` **唯一来源：域 GraphIndex**。
- Wiki triples **禁止**写入 Action 审计链。
- 实体不在 GraphIndex → Action 失败或显式 `entity_missing`，不得用 Wiki 页顶替。

---

## 5. Evolve vs 本体演化（禁混）

| 变更类型 | 门 | 路径 |
|----------|----|------|
| 白名单配置键（含 prompt_extra） | Evolve HITL + observing + sync-ops | Phase 4B |
| 域 YAML 类/状态机/axioms/关系 | `VersionedOntologyStore` tier 审批 + apply | 知识工厂 / ontology-editor |
| ABox 实例增删改 | Action / 抽取确认 / 引擎管道 | 非 Evolve |

`touches_abox|touches_ontology` 的提案**不得**经 Evolve apply（见 `evolve_proposal_gate.py`）。  
UI 文案必须带前缀：`配置 Evolve` vs `本体提案`。

---

## 6. graph_validate 假绿禁令

| 条件 | 要求 |
|------|------|
| 未执行一致性检查 | `status="unchecked"`（或 `"error"`），**`valid` 不得为 true** |
| 部分检查失败/跳过 | `status="error"` 或 `"degraded"`，列出 `skipped_checks[]` |
| 通过 | `status="ok"` 且 `checks_run` 非空 |

---

## 7. 场景闭环深度（结项度量）

| 档位 | 标准 |
|------|------|
| 浅 | 类+状态机写全；≥1 个 customer_action 可按状态否决 |
| 中 | 抽取→待审→提案→应用走通 ≥1 次；审计可查 |
| 深 | ≥1 次「例外→改模式→行为变化」且提案+审计可追溯 |

本阶段试点域：`lock-service`；结项目标：中档 + 深档证据各 ≥1。

---

## 8. 风险点案例库（实施期追加）

| ID | 风险 | 处置 |
|----|------|------|
| R1 | 同名类两边定义不一致 | Agent/Action 听域；Wiki 文案 warning |
| R2 | compiler 只读全局 AXIOMS | 业务路径改读域 YAML |
| R3 | Infra OntologyManager 打 wiki API 被当成业务已校验 | UI 标注知识库轨道 |
