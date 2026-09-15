# FDE 工作台契约（FDE Workbench Contract）

版本：v1.0  
状态：Phase 0 生效，Phase 1 强制  
适用范围：FDE 工作台前端、CoreFacade、ActionRegistry、PipelineEngine、DomainRouter、PolicyGate、Eval 服务  

规范文件：
- 本文：`docs/contracts/FDE_WORKBENCH_CONTRACT.md`
- 审计 / Eval：`aiPlat-core/core/harness/schemas/audit_schema.v1.yaml`
- **能力台账（成熟度/消费方/证据/缺口）：** [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md)（实例）· [`FDE_CAPABILITY_LEDGER_TEMPLATE.md`](./FDE_CAPABILITY_LEDGER_TEMPLATE.md)（空白模板）
- **AI FDE 受控应用闭环（设计）：** [`FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md`](./FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md)

---

## 0. 一句话定义

FDE 工作台是**现场工程师的控制台**：选客户、看状态、批动作、盯 KPI。  
它不是第二个 Builder IDE，不是自由多 Agent 聊天界面，不是诊断 YAML 编辑器。

执行核是**工厂 / Pipeline**：在契约化约束下完成多 Agent 交付。  
工作台不平行实现执行逻辑，一律经 CoreFacade。

---

## 1. 分层职责

| 层 | 定位 | 不允许 |
| :--- | :--- | :--- |
| FDE 工作台 | 控制台：客户上下文、运行态 Pipeline、Action 审批、KPI/Eval | 代码编辑器、文件树、调试器、自由 LLM 对话代替 Action |
| 工厂 / Pipeline | 执行核：契约化多 Agent 交付 | 动态 spawn、自由编排、绕过 PolicyGate |
| ActionRegistry | 客户运营 Action 与平台诊断 Action 的统一注册与执行入口 | 硬编码业务分支（如 `if action == "accept_order"`） |
| DomainRouter | 客户域解析唯一入口 | core/harness 中出现字面量客户域名 |
| Ontology | 客户业务世界模型 + 平台交付跟踪元层 | 两类本体混用命名空间 |
| Eval / Evidence | 质量门与物理证据 | LLM 断言替代物理证据进入 confirmed |

原则：工作台不平行实现检索、编排、权限；一律经 CoreFacade。

---

## 2. 两类 Action 的命名空间与治理

### 2.1 命名空间

| 类型 | 命名空间前缀 | 示例 | 影响对象 |
| :--- | :--- | :--- | :--- |
| 客户运营 Action | `customer_action:` | `customer_action:lock-service:accept_order` | 客户业务实体状态 |
| 平台诊断 Action | `platform_action:` | `platform_action:fde-delivery:field_assessment` | 平台自身状态、元数据 |

**强制规则：**
- Ontology 中两类本体使用独立命名空间，禁止混用。
- ActionRegistry 注册时必须声明 `action_namespace` 与 `domain_id`。
- UI 中两类 Action 使用不同颜色、不同审批面板、不同审计视图。

### 2.2 权限与审批

| 维度 | 客户运营 Action | 平台诊断 Action |
| :--- | :--- | :--- |
| 默认执行者 | 仅 Agent 提议，人审批 | 人可直接执行，Agent 可提议 |
| 高风险动作 | 必须 HITL + MFA（admin） | HITL 可选，按 PolicyGate 配置 |
| 回滚要求 | 必须支持状态回滚或补偿 Action | 可重建，不强制回滚 |
| 审计保留 | 永久（合同责任） | 按平台日志策略 |
| PolicyGate | 租户隔离 + 角色 + 域白名单 | 平台角色 + 环境隔离 |

### 2.3 审计与证据

- 客户运营 Action 每次执行必须写 `audit_record`（见 `audit_schema.v1.yaml`）。
- 平台诊断 Action 写平台日志，可复用同一 schema 但 `retention` 不同。
- 客户运营 Action 的 `confirmed` 级证据必须包含：
  - Action 执行前后实体状态快照
  - 审批者 ID
  - 执行结果（成功/失败/部分成功）
  - 关联的 Pipeline run_id 与 evidence_ref

### 2.4 Eval 门

| 阶段 | 客户运营 Action | 平台诊断 Action |
| :--- | :--- | :--- |
| 上线前 | 必须通过 `eval_gate:customer_action_safety` | 必须通过 `eval_gate:platform_action_health` |
| 生产变更 | 全量 Eval 通过 + 人工审批 | 全量 Eval 通过 |
| Evolve 提案 | 仅允许改 prompt_extra / 白名单配置 | 同左 |

Eval 门语义见 `audit_schema.v1.yaml` 的 `eval_gate` 节。

---

## 3. 域解析规则（DomainRouter）

**唯一入口：** 所有客户域解析必须经 `DomainRouter.resolve(domain_id)`（或 Facade 等价导出）。

**禁止：**
- core/harness 中出现字面量 `"fde-delivery"`、`"lock-service"`、`"supply-chain"` 等客户域名作为行为分叉。
- 前端硬编码 `INDUSTRY_DOMAIN_MAP` 后直接传给后端；必须经 DomainRouter 校验。
- GraphIndex.load 直接接受客户域名硬编码；`domain_id` 必须来自 DomainRouter / 调用方上下文。

**架构守卫：**
- `architecture_guard` 增加规则：`core/harness/**` 中禁止字符串字面量匹配 `^(fde-delivery|lock-service|supply-chain|...)`（测试与 `# noqa: domain-literal` 登记豁免除外）。
- CI 中运行域字面量检查（目标：`python -m architecture_guard --check domain_literals` 或等价脚本钩子）。

**Phase 0 验收：**
- 全仓库搜索 `GraphIndex.load("fde-delivery")`，收敛为 DomainRouter 调用或平台跟踪域固定常量（仅允许出现在 ontology 种子 / 明确的 FDE 跟踪 API）。
- 客户域列表由 DomainRouter 维护，新增客户只需注册，不改 harness。

---

## 4. 工作台否定清单

**路径事实（强制对齐守卫 scope）：**

| 层 | 真实路径 |
|----|----------|
| 前端工作台 UI | `aiPlat-management/frontend/src/pages/Diagnostics/`（入口 `/diagnostics/fde`） |
| 后端 FDE API | `aiPlat-platform/apps/fde/`（canonical HTTP：`/api/platform/apps/fde`） |

> **禁止**在守卫规则中使用不存在的 `aiPlat-platform/platform/apps/fde/**/*.{ts,tsx}`——会静默扫空。

工作台**不允许**出现以下能力：

1. **代码编辑器**：不允许内置 Monaco / CodeMirror / Ace 等代码编辑组件。
2. **文件树 / 资源管理器**：不允许浏览仓库文件系统。
3. **调试器 / 终端**：不允许内嵌 shell、调试控制台。
4. **自由 LLM 对话代替 Action**：不允许用聊天窗口直接触发未注册的 Action。
5. **动态 Agent 编排**：不允许在工作台前端配置 Agent 拓扑、spawn 新 Agent。
6. **绕过 PolicyGate 的快捷执行**：不允许“一键执行”跳过审批。
7. **硬编码业务分支**：不允许 `if action == "accept_order"` 类逻辑出现在 harness。
8. **假进度条**：不允许用 React 本地状态模拟 Pipeline 进度。
9. **空 stub 伪装运营监控**：不允许用空数组或静态数据冒充真实 KPI。
10. **API 双轨扩散**：不允许新增 `/api/core/fde` 类平行路径；旧路径仅兼容。

**检查方式：**
- 前端组件审查 + ESLint 规则禁止引入编辑器类库。
- CoreFacade 入口审查，禁止工作台直调 harness 内部。
- `FDE_WORKBENCH_CONTRACT.md` 作为 PR 模板勾选项。

---

## 5. 与安全审计 Pipeline 的对接

- FDE 工作台 Phase 4A 的“上线前检查”一键跑，对接 `security_audit` / `security_review` Pipeline。
- 阶段命名映射：
  - FDE Phase 4A ↔ security_audit Phase B/C
  - FDE Phase 4B ↔ security_audit Phase D（成本与质量度量；若尚未立项则标注待接线）
- 安全审计产出的 `finding` 与 `evidence_bundle` 纳入 FDE 工作台的 Evidence Store。
- 客户运营 Action 的 `eval_gate:customer_action_safety` 可复用 security_audit 的 critique + evidence 结果。

---

## 6. 成功度量（含反向指标）

| 指标 | 用途 |
| :--- | :--- |
| Pipeline 刷新一致率 | Phase 1 |
| customer_action 审计完整率 | Phase 2 |
| 人审**拒绝率** + 拒绝理由分布 | Phase 4（防橡皮图章） |
| 人审通过后的**回滚率** | Phase 4 |
| 补丁经人审后的**平均存活时间** | Phase 4 |
| 人审通过率 | **仅作参考**，不得单独作为 KPI |

---

## 7. 验收与检查

Phase 0：
- [x] `FDE_WORKBENCH_CONTRACT.md` 合入仓库（本文）
- [x] `audit_schema.v1.yaml` 合入 `core/harness/schemas/`
- [x] §98 守卫落地（见 `FDE_GUARD_REGISTRY_LANDING.md`）— 含 `workbench_no_fake_progress` / `workbench_no_agent_topology` warning
- [x] API 前缀统一为 `/api/platform/apps/fde`，旧路径标兼容
- [x] Tab⑤ 文案改为“平台离线包”，新增“启动交付 Pipeline”入口（可灰）
- [x] FDEBuilderOrchestrator 定生死（接线或删除计划）→ **已归档** `service/_archive/builder.py`
- [x] dashboard 空 stub 接真数据或隐藏
- [x] fde_delivery_v1 标注“模板已存在 / 执行未接线”

Phase 1：
- [x] DomainRouter 成为唯一域解析入口（`require_known_domain` + `fde_pipeline` 改 `list_domains`；守卫 warning 观察中）
- [x] architecture_guard 域字面量检查通过（`fde_domain_literals` **error**；AST=0；见 `domain_literals_scan.md` v1.1）
- [x] 两类 Action 命名空间在 ActionRegistry 中生效（register 强校验 + seed `customer_action:lock-service:accept_order`）
- [x] 审计 schema 落地，lock-service accept_order 产生完整 audit_record（Phase 1：params/`entity_snapshot` 嵌入 `audit.v1`）
- [x] Eval 门语义在 Phase 1 定义，Phase 2 复用（`audit_schema.v1.yaml` + `eval_gate_ids` / register 校验）
- [x] HITL 端到端验证：≥2 次暂停/恢复 + 刷新一致（交付 session 自动化 + [`FDE_PHASE1_HITL_SMOKE.md`](./FDE_PHASE1_HITL_SMOKE.md)）
- [x] 变更面白名单（`change_surface_whitelist`）落地为可加载 YAML，清单外一律 HITL（`check_change_surface`）
- [x] `scripts/fde_audit_mapping.py` dry-run + `docs/contracts/audit_mapping_report.md`
- [x] `WorkbenchRuntimeGuard` 骨架（registered / policy_gate shape / stub KPI）
- [x] Tab⑤ 启动 `fde_delivery_v1` 服务端 session（进度来自服务端；honesty=template_session）

Phase 2：
- [x] `accept_order` → `customer_action:lock-service:accept_order` + legacy 别名（D3）
- [x] AcceptTab 经 Registry 真执行；`audit.v1` 嵌入完整率 100%（bench sample）
- [x] UI 区分客户运营 / 平台诊断（`action_kind` badge）
- [x] GraphIndex `metadata`/`state` 持久化往返（`add_entity_property` UPDATE + load）
- [x] D4 压测 200：失败率 0；审计 200；execute→audit P95&lt;500ms；entity 查询 P95&lt;100ms（`scripts/bench_accept_order_p95.py`）
- [x] 种子脚本可生成 N 工单（`scripts/seed_lock_service_orders.py`，A4 验证）

Phase 3：
- [x] 交付 session 可链接 Builder `project_id`（`link_builder_project` / start 参数）
- [x] 工作台经 Facade 观测/启动工厂 Pipeline（`observe-builder` / `start-builder`）；不平行构建
- [x] 验收前 `fde_delivery_pipeline` Eval 门（未观测 / failed → `eval_blocked`）
- [x] Tab⑤ honesty 文案更新；展示 `artifact_links` / Builder 观测
- [x] 生成物：apps/fde 仍「不适用」；交付物走 builder 已接线路径（§23）

Phase 4：
- [x] 独立「⑥b 上线前检查」入口（D5）；默认 Phase B；Phase C 显式开关
- [x] `POST /fde/security-preflight/run` 经 `CoreFacade.run_security_review_dry`；Evidence 只读摘要存 `$AIPLAT_HOME/fde_security_preflight/`
- [x] Evolve 提案门 `evolve_proposal` + 变更面白名单；ABox/Ontology 写强制 HITL；无静默写库
- [x] **AI FDE 半步**：approve / reject / **受控 apply** / rollback（白名单配置 → `fde_evolve_applied_config.json`）；D6 指标 API+UI
- [x] EvolutionTab 展示 Evolve 队列与反向 KPI；文案声明人审通过率不得单独作 KPI（D6）
- [x] platform `fde_phase4.py` 仅经 CoreFacade（无直导 security_* handler）
- [x] **预检签收硬门**：`preflight_signoff_gate` → checklist + `POST /acceptance/signoff` 409；AcceptTab 展示阻断原因
- [x] **第二域竖切**：`customer_action:service-domain:assign_technician` seed + `assign_work_order` handler（无 harness 分叉）

Phase 5：
- [x] `fde_domain_literals` → **error**；行为分叉=0；D2 关闭
- [x] 新客户 = DomainRouter + 本体/Action 配置（[`FDE_PHASE5_CUSTOMER_ONBOARDING.md`](./FDE_PHASE5_CUSTOMER_ONBOARDING.md)）；不改 harness
- [x] Agent Fleet / 拓扑 UI 不展开（`AgentNetworkPanel` 隔离）
- [x] 工作台 ① 业务认知诚实说明配置驱动接入路径

---

## 8. 变更记录

| 版本 | 日期 | 变更 | 作者 |
| :--- | :--- | :--- | :--- |
| v1.0 | 2026-09-14 | 初始版本，Phase 0/1 契约 | FDE 工作台改进方案 |
| v1.1 | 2026-09-14 | Phase 2 验收勾选（D3/D4） | Oliver Zhu |
| v1.2 | 2026-09-14 | Phase 3 Builder 链接 + Eval | Oliver Zhu |
| v1.3 | 2026-09-14 | Phase 4 安全预检 + Evolve 门（D5/D6） | Oliver Zhu |
| v1.4 | 2026-09-14 | Phase 5 多客户；D2 升 error | Oliver Zhu |
| v1.5 | 2026-09-15 | AI FDE 半步：Evolve apply/rollback + D6 指标 | Oliver Zhu |
| v1.6 | 2026-09-15 | 预检签收硬门 + service-domain 第二竖切 | Oliver Zhu |
| v1.7 | 2026-09-15 | 挂载能力台账（成熟度/消费方/失败路径） | Oliver Zhu |
