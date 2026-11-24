---
doc_type: Report
title: Phase 2 — 知识系统符合性例外 ADR 包（Batch F1 §9.4 exception_adr 槽位）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
---

# Phase 2 / 例外 ADR 包（Batch F1）

> 实施权威：附录 N 认证证据包 `certification_slots.exception_adr` 最小填空。  
> **集中登记当前例外**；**非**全量 ADR 体系；试点 Core（朱鸿林）+ Extended（朱莹）+ Operational（朱莹）+ 全量（朱向群，conditional）已批准；SLO 目标已登记且遥测已接线（非生产达标）。  
> 2026-11-19：Core 12 / Extended 6 / Operational 6 均按附录 N.2–N.4 标为等级 scoped `exists`；N09 **探针集冻结**；深度缺口记为后续加深，不阻塞已开徽章。  
> 2026-11-21：非本表 catalog note 盘点见 `phase2-catalog-honesty-triage.md`（不关闭本表例外）。
> 2026-11-23：Phase 2 **sufficient-freeze 程序收口**（`phase2_sufficient_freeze_complete`；20 旗）；residual/certified 仍开放。见 `phase2-sufficient-freeze-closeout-evidence.md`。

## 例外清单（范围 / 期限 / 补偿）

| ID | 范围 | 期限 | 补偿 |
|----|------|------|------|
| N01 | FactLedger 读时 hash + DataSourceConfig content_hash→Raw + process Raw 默认强制（可 opt-out）+ Core file/sql/api 连接器矩阵 + SQL vendor 软依赖探测矩阵（sqlite/postgresql/mysql；oracle `declared_unavailable`）+ **停止**默认 N01 deepen（`n01_raw_integrity_freeze`）；未宣称生产连库验收 / certified | Raw 面足够；certified / 生产 vendor 验收仍开放 | 见 raw-integrity + datasource-raw + process-raw + default-force + `phase2-datasource-connector-matrix-evidence.md` + `phase2-n01-raw-integrity-freeze-evidence.md` + `phase2-n01-vendor-driver-matrix-evidence.md` |
| N02 | 域 YAML version + Package + ObjectType draft→人审发布（角色门；Package schema 门可选）+ 管理端薄门户 + **显式 residual** opt-in `bulk_transition_object_types` + **显式 residual** opt-in `apply_published_seed_authority` + **产品面第一刀** `list_object_type_seed_catalog` / `apply_published_seed_authority_product`（默认可用；不改写 `workspace_seeds`；非 complete / 非 certified）+ **停止**默认 N02 deepen（`n02_object_type_freeze`） | 发布面+薄门户+有界批量+种子 residual/产品面足够；certified/`seed_replacement_complete` 仍开放 | 见 ontology-package + `phase2-object-type-publish-evidence.md` + `phase2-n02-object-type-freeze-evidence.md` + `phase2-n02-object-type-publish-portal-evidence.md` + `phase2-n02-bulk-portal-residual-evidence.md` + `phase2-n02-seed-replace-residual-evidence.md` + `phase2-n02-seed-authority-product-evidence.md` |
| N03 | Claim 证据硬门+冲突记录 + 状态写路径（transition→put_claim）；非全量 Claim 生命周期产品 / 非 certified + **停止**默认 deepen（`n03_claim_freeze`） | Claim 面足够；全量生命周期/certified 仍开放 | 见 claim-evidence + `phase2-claim-status-write-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N06 | FactLedger F.1 契约 + 统一入口（fact/object_set/wiki/index/materials_chat/graphrag → F.1；Materials/GraphRAG 挂 gateway_f1）；非全部其它应用 / 非 certified + **停止**默认 deepen（`n06_query_gateway_freeze`） | Gateway 面足够；其它应用入口/certified 仍开放 | 见 gateway-contract + `phase2-unified-query-gateway-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N09 | Core 探针集已冻结（`n09_core_probe_freeze`）；跨租户套件含统一 Gateway fact/object_set 探针；K1–K70 + TripleStore SECURITY V2 加深证据保留；**停止**无等级 default mop 作为 Core 条件；空 tenant 仍兼容全量扫描；未宣称全域 0 泄漏 / N09 certified | Core 足够；全域深度开放 | 跨租户套件门槛门 + `phase2-cross-tenant-triplestore-evidence.md` |
| N13/校准 | ECE/`high_precision` 门槛 + 查询路径封顶（fact gateway）+ **显式 residual** opt-in `compute_ece_from_samples`（不可用诚实上报；非准确率宣称 / 非 certified）；Core 不以校准为阻塞；未达标诚实封顶 medium + **停止**默认 deepen（`n13_calibration_freeze`） | 校准封顶面足够；准确率宣称/certified 仍开放 | 附录 O + `phase2-calibration-pipeline-evidence.md` + `phase2-n13-ece-train-residual-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N23/OCS | DomainRouter 企业域扫描 + 词汇预注册 + 门槛地板；属 Operational；非企业全域完整 / 非 certified + **停止**默认 deepen（`n23_ocs_freeze`） | OCS 扫描面足够；企业全域完整/certified 仍开放 | §13.4 + `phase2-ocs-enterprise-scan-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N04/N12 | 写入硬门+transition + 配置驱动 reviewer 角色门（publish）；非部署 RBAC 真源 / 非 certified + **停止**默认 deepen（`n04_n12_write_rbac_freeze`） | 写入/角色门面足够；部署 RBAC 真源/certified 仍开放 | source_policy + `phase2-reviewer-rbac-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N05 | 三分类 rebuild_mode+reason + Fact→Wiki 派生页有条件重建；非 wiki_engine/FTS 全量 / 非 certified + **停止**默认 deepen（`n05_wiki_rebuild_freeze`） | Wiki 重建面足够；wiki_engine/FTS 全量/certified 仍开放 | rebuild-taxonomy + `phase2-wiki-rebuild-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N10 | 附录 O 校准门槛 + 域级 Exact-match gold 流水线（DomainRouter/显式域）+ **显式 residual** opt-in `judge_mode=llm` / `llm_judge_object_equiv`（不可用诚实上报；非准确率宣称 / 非 certified）+ **停止**默认 deepen（`n10_gold_eval_freeze`） | Gold 评测面足够；准确率宣称/certified 仍开放 | calibration + `phase2-knowledge-gold-eval-evidence.md` + `phase2-n10-llm-judge-residual-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N17 | 记录级语义运行时权威（validate/transition/FactLedger scan）；非 reference_policy 替换 / 非 semantic_cases 全量对 Fact Store / 非 certified + **停止**默认 deepen（`n17_record_semantics_freeze`） | 记录语义面足够；semantic_cases 全量/certified 仍开放 | `phase2-record-semantics-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N18 | 实现方 5 探针 + 部署侧 RBAC 真源（禁 reference_policy 作权威）；非召回/聚合/导出/缓存全路径 / 非 certified + **停止**默认 deepen（`n18_deployed_rbac_freeze`） | 部署 RBAC 面足够；召回全路径/certified 仍开放 | implementer-semantics + `phase2-deployed-rbac-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N19 | customer_action before/after + Fact/Query 统一审计 + put_fact/unified/query_facts(_gateway)/MaterialsChat/GraphRAG/Wiki-KB/裸 list/KB Q&A·CRAG/统一 knowledge_retrieve/`sys_wiki_context`/wiki_structured/`wiki_search_pages_api`/`sys_ontology_context`（域）/URN syscall+HTTP/`sys_graph_neighbors`/`sys_graph_query`/裸 `wiki_search_pages`/FDE clarify tenant/wiki_engine.search_pages(opt-in) 热路径 best-effort；非全部旁路强制 / 非 N24 总线全量 / 非 certified + **停止**默认 deepen（`n19_fact_query_audit_freeze`） | Fact/Query 审计面足够；全部旁路强制/certified 仍开放 | action-execution + `phase2-fact-query-wiki-engine-search-pages-hotpath-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N20 | L1+审批 + 知识面 L1>L2>L3 约束栈 + Gateway/put_fact/query_facts_gateway/MaterialsChat/GraphRAG/Wiki-KB/裸 list/`query_facts` list 热路径挂 n20_constraint；非 list→dict 改写 / 非 Lv4 / 非 certified + **停止**默认 deepen（`n20_constraint_layers_freeze`） | 约束分层面足够；list→dict/Lv4/certified 仍开放 | g2/function/action + `phase2-constraint-layers-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N21 | OCS/校准诚实锁 + Fact/object_set + Wiki/KB 查询形 + MaterialsChat RAG/trivial/cache_hit + GraphRAG + list 挂 n21_query；非改写 list 主返回类型 / 非 certified + **停止**默认 deepen（`n21_query_abstain_freeze`） | abstain/citations 面足够；list 主类型改写/certified 仍开放 | ocs/calibration + `phase2-query-abstain-citations-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N07/N22 | ObjectSet + link.traverse + retrieve/KB/CRAG + 裸 Wiki/GraphRAG + OKF/OWL/suggestions/offline 导出字段 ACL + EvolutionRunner + platform auto 身份透传 + 字段/ABox ACL 薄 UI + DELETE + preview + H.1 有界条件面（至 expr-lang A+B+C）+ **停止**默认 condition-op deepen（`n07_n22_h1_condition_freeze`）+ masked_properties + apply/list/get_h1 + 薄表单 + 薄矩阵 + per-role 矩阵（role_actions）+ 配置轴（h1_matrix_axes）；未宣称 certified / `$where`|`$expr` / 任意 RBAC 产品 | 有界 H.1 足够；certified/$where|$expr/任意 RBAC 仍开放 | ABox ACL + … + `phase2-abox-acl-h1-condition-freeze-evidence.md` |
| N08 | Registry Policy/Approval/Audit + kill switch；require_approval 强制入队；Lv4 误报门 v2（禁 0 样本假绿 + rollback）+ **显式 residual** opt-in `evaluate_bounded_lv4_auto_close` + **产品面第一刀** `evaluate_bounded_lv4_auto_close_product`（默认可用；仅 low；`lv4_product_surface=true`；非 full_action_lv4 / 非 certified）+ **停止**默认 N08 deepen（`n08_action_policy_freeze`） | Policy 面+有界闭环+产品面足够；certified/全量 Action Lv4 仍开放 | ActionRegistry + `phase2-action-policy-audit-evidence.md` + `phase2-lv4-false-positive-gate-evidence.md` + `phase2-n08-action-policy-freeze-evidence.md` + `phase2-n08-lv4-autoclose-residual-evidence.md` + `phase2-n08-lv4-autoclose-product-evidence.md` |
| N11/N14 | 本地双写对账 + 作业级切写授权（token）+ Raw↔Fact↔Index 全链路 deepen + **显式 residual** opt-in `attest_production_cutover_readiness` + **产品面第一刀** `attest_production_cutover_readiness_product`（默认可用；`prod_attest_product_surface=true`；非生产切写认证 / 非 certified）+ **停止**默认 deepen（`n11_n14_migration_freeze`） | 迁移/对账+产品面足够；生产切写认证/certified 仍开放 | migration + cutover-auth + `phase2-raw-fact-index-reconcile-evidence.md` + `phase2-n11-production-attest-residual-evidence.md` + `phase2-n11-production-attest-product-evidence.md` + `phase2-remaining-adr-freeze-evidence.md` |
| N24 | Package + Fact/Claim/Source revision + restore + audit + 审批式 restore + ActionExecution 桥接 + HTTP + 管理端薄 UI + 只读统一视图 + 统一审计 UI + 写总线 + Package/Action 热路径 + ActionStore 合流 + 物理 tenant_id + 存量回填 + Fact/Query 源流 fan-in + 总线热路径 + UI 流过滤 + UI materialize + UI bus suite/gate + UI 薄 append + UI append refs/payload + UI 事件详情/bus event_type 过滤 + **显式 residual** ops console 薄壳 + 有界导出 + **显式产品面**（默认可用 snapshot + ObjectType schema JSON + **表单字段编辑器** + 浏览器导出；`full_ops_console=true` / `schema_form_editor=true`；非 certified / 非自由布局设计器）+ **停止**默认 N24 deepen（`n24_unified_audit_freeze`） | 审计面+薄壳+有界导出+产品面（含表单字段编辑）；certified / 自由布局可视化设计器 / Full unconditional 仍开放 | 见 revision 系列 + `phase2-unified-audit-ui-event-detail-evidence.md` + `phase2-n24-unified-audit-freeze-evidence.md` + `phase2-n24-ops-console-residual-evidence.md` + `phase2-n24-ops-console-export-residual-evidence.md` + `phase2-n24-ops-console-product-evidence.md` + `phase2-n24-ops-console-schema-form-evidence.md` |
| SLO | 目标已登记；遥测已接线 + **停止**默认 SLO wiring deepen（`slo_telemetry_freeze`）；达标窗口 residual 已接线（`evaluate_slo_attainment_window`；`attainment_ok`≠certified）；**显式 residual** opt-in `evaluate_slo_alert_candidates`（不可用诚实上报；非 pager 投递 / 非 certified）；Full unconditional 未宣称 | 遥测/达标窗口/告警候选面足够；pager 投递/Full unconditional/certified 仍开放 | 本 ADR + `phase2-slo-target-evidence.md` + `phase2-slo-telemetry-wiring-evidence.md` + `phase2-slo-telemetry-freeze-evidence.md` + `phase2-slo-attainment-window-evidence.md` + `phase2-slo-alerting-residual-evidence.md` |

权威条目 note 以 [`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml) 为准；本表为人读汇总。  
未进本表、但仍有 catalog note 深度缺口的 exists 项，见 [`phase2-catalog-honesty-triage.md`](./phase2-catalog-honesty-triage.md)（仍开放 / 已过时 / 并入既有刀）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `exception_adr` path 非空且文件存在 | pass | catalog 槽位 |
| 结构门无 explicit-missing warning | pass | conformance pack 测 |
| certified 恒 false | pass | honesty |

## 明确未做

- 例外自动过期/关闭工作流
- 用本包冒充附录 N 全量符合或风险已接受签字
