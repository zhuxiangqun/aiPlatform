---
doc_type: Index
title: 知识系统 v4.3.1 Phase 0 证据目录
status: active
authority: supporting
---

# 知识系统 v4.3.1 · Phase 0 证据

> 实施权威：[`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md`](../../../../docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md)  
> 标准包：[`docs/standards/knowledge-system/v4.3.1/`](../../../../docs/standards/knowledge-system/v4.3.1/)  
> **本目录是测量证据，不是第二份标准或实施方案。**  
> **试点认证状态（lock-service，2026-11-19）**：Core 朱鸿林 / Extended 朱莹 / Operational 朱莹 / Full 朱向群（conditional，SLO 已接线非达标）；未宣称准确率。

| 文件 | 内容 |
|------|------|
| [phase0-standard-pack-baseline.md](./phase0-standard-pack-baseline.md) | 标准 schema/语义校验结果（原始 `*.log` 被 `.gitignore`，以本摘要为准） |
| [phase0-asset-inventory.md](./phase0-asset-inventory.md) | 资产 / owner 盘点 |
| [phase0-conformance-gap-n24.md](./phase0-conformance-gap-n24.md) | 附录 N 24 项差距表（2026-11-16 刷新；SSOT 见 catalog） |
| [n24-conformance-catalog.yaml](./n24-conformance-catalog.yaml) | 附录 N 机器可读目录（证据包 SSOT） |
| [phase0-pilot-lock-service.md](./phase0-pilot-lock-service.md) | 试点域边界与 G0 |
| [phase1-g1-evidence.md](./phase1-g1-evidence.md) | Phase 1 G1（Fact Ledger） |
| [phase2-g2-evidence.md](./phase2-g2-evidence.md) | Phase 2 G2（L1 硬门 + Fact→Graph 可重建） |
| [phase2-wiki-readonly-evidence.md](./phase2-wiki-readonly-evidence.md) | Phase 2 Wiki 读模型硬门（试点人工写拦截） |
| [phase2-function-contract-evidence.md](./phase2-function-contract-evidence.md) | Phase 2 W5 FunctionContract（无副作用硬门 + L1） |
| [phase2-objectset-evidence.md](./phase2-objectset-evidence.md) | Phase 2 W6 ObjectSet（租户前置只读查询 + L1） |
| [phase2-agent-tool-evidence.md](./phase2-agent-tool-evidence.md) | Phase 2 W6 Agent Tool（object.query / function.call） |
| [phase2-link-traverse-evidence.md](./phase2-link-traverse-evidence.md) | Phase 2 W6 link.traverse（多跳只读 + L1） |
| [phase2-object-set-aggregate-tool-evidence.md](./phase2-object-set-aggregate-tool-evidence.md) | Phase 2 W6 object_set.aggregate 工具（只读 count） |
| [phase2-action-execute-tool-evidence.md](./phase2-action-execute-tool-evidence.md) | Phase 2 W6 action.execute 工具（ActionRegistry L1） |
| [phase2-sdk-evidence.md](./phase2-sdk-evidence.md) | Phase 2 W6 Knowledge SDK（ObjectType→Client / Facade） |
| [phase2-action-execution-evidence.md](./phase2-action-execution-evidence.md) | Phase 2 W7 ActionExecution（幂等 + before/after） |
| [phase2-objectset-acl-evidence.md](./phase2-objectset-acl-evidence.md) | Phase 2 W8 ObjectSet ABox ACL（实例/字段 + 跨租户负向） |
| [phase2-scenario-evidence.md](./phase2-scenario-evidence.md) | Phase 2 W9 Knowledge Scenario（模拟不写主事实 + 合并人审） |
| [phase2-ontology-package-evidence.md](./phase2-ontology-package-evidence.md) | Phase 2 W9 Ontology Package（版本/哈希校验 + 兼容 + 依赖锁定 + 回滚） |
| [phase2-confidence-calibration-evidence.md](./phase2-confidence-calibration-evidence.md) | W10 Confidence Calibration（附录 O 门槛 + 失败降级 medium） |
| [phase2-ocs-evidence.md](./phase2-ocs-evidence.md) | W10 OCS Completeness（§13.4 覆盖计分 + 门槛门；禁节点数档位） |
| [phase2-knowledge-migration-evidence.md](./phase2-knowledge-migration-evidence.md) | W10 Knowledge Migration（双写/对账/回滚演练；切写未授权） |
| [phase2-conformance-pack-evidence.md](./phase2-conformance-pack-evidence.md) | W10 Conformance / 认证证据包（N24 目录 + §9.4 槽位；非 24/24 认证） |
| [phase2-implementer-semantics-evidence.md](./phase2-implementer-semantics-evidence.md) | W10 N18 实现方语义测试（5 探针 + 门槛门；非全量认证） |
| [phase2-source-policy-evidence.md](./phase2-source-policy-evidence.md) | W3 N04 Source Policy / Conflict（策略登记 + 冲突不自动选边 + 人审；非全写入强制） |
| [phase2-fact-state-evidence.md](./phase2-fact-state-evidence.md) | W3 N12 Fact 状态机（review/lifecycle/claim + 审计；非裸 put_fact 唯一强制） |
| [phase2-claim-evidence-evidence.md](./phase2-claim-evidence-evidence.md) | Batch F2 N03 Claim 证据硬门+冲突记录（门槛门；非全量认证） |
| [phase2-slo-target-evidence.md](./phase2-slo-target-evidence.md) | Batch F1 §9.4 SLO 目标登记（非生产遥测达标） |
| [phase2-slo-telemetry-wiring-evidence.md](./phase2-slo-telemetry-wiring-evidence.md) | F1 deepen：生产 SLO 遥测接线（wiring≠attainment；Full 仍 conditional） |
| [phase2-wiki-kb-field-acl-evidence.md](./phase2-wiki-kb-field-acl-evidence.md) | N07/N22 deepen：Wiki/KB 统一检索字段 ACL（非全入口 certified） |
| [phase2-wiki-graphrag-field-acl-evidence.md](./phase2-wiki-graphrag-field-acl-evidence.md) | N07/N22 deepen：裸 Wiki + GraphRAG chunks 字段 ACL（非 certified / 非导出全路径） |
| [phase2-okf-export-field-acl-evidence.md](./phase2-okf-export-field-acl-evidence.md) | N07/N22 deepen：OKF 导出写盘字段 ACL（非 certified / 非 UI） |
| [phase2-owl-export-field-acl-evidence.md](./phase2-owl-export-field-acl-evidence.md) | N07/N22 deepen：OWL/RDF 导出 A-Box 字段 ACL（非 certified / 非 UI） |
| [phase2-owl-suggestions-offline-acl-evidence.md](./phase2-owl-suggestions-offline-acl-evidence.md) | N07/N22 deepen：suggestions OWL / offline_owl_review 身份透传（非 certified / 非 UI） |
| [phase2-evolution-runner-acl-evidence.md](./phase2-evolution-runner-acl-evidence.md) | N07/N22 deepen：EvolutionRunner suggestions OWL 落盘身份透传（非 certified / 非 UI） |
| [phase2-wiki-auto-identity-passthrough-evidence.md](./phase2-wiki-auto-identity-passthrough-evidence.md) | N07/N22 deepen：platform ingest/watch/vault → wiki_auto_update 身份透传（非 certified / 非伪造 cron 角色） |
| [phase2-field-acl-thin-ui-evidence.md](./phase2-field-acl-thin-ui-evidence.md) | N07/N22 deepen：字段 ACL 管理端薄 UI（非 certified / 非全量权限产品） |
| [phase2-abox-acl-thin-ui-evidence.md](./phase2-abox-acl-thin-ui-evidence.md) | N07/N22 deepen：ABox 实例 ACL 管理端薄 UI（非 certified / 非全量权限产品） |
| [phase2-abox-acl-delete-evidence.md](./phase2-abox-acl-delete-evidence.md) | N07/N22 deepen：ABox ACL DELETE + 薄 UI 删除（非 certified / 非全量权限产品） |
| [phase2-abox-acl-preview-evidence.md](./phase2-abox-acl-preview-evidence.md) | N07/N22 deepen：ABox ACL 按角色预览（非 certified / 非 H.1 condition 编辑器） |
| [phase2-abox-acl-condition-evidence.md](./phase2-abox-acl-condition-evidence.md) | N07/N22 deepen：ABox ACL H.1 condition 最小等值匹配（非完整策略编辑器） |
| [phase2-abox-acl-condition-ops-evidence.md](./phase2-abox-acl-condition-ops-evidence.md) | N07/N22 deepen：ABox ACL condition $eq/$ne/$in（非表达式语言 / 非 certified） |
| [phase2-abox-acl-masked-props-evidence.md](./phase2-abox-acl-masked-props-evidence.md) | N07/N22 deepen：ABox ACL H.1 masked_properties + 只读投影（非完整策略编辑器） |
| [phase2-abox-acl-h1-apply-evidence.md](./phase2-abox-acl-h1-apply-evidence.md) | N07/N22 deepen：ABox ACL H.1 薄导入 apply_h1_policy（非完整策略编辑器） |
| [phase2-exception-adr.md](./phase2-exception-adr.md) | Batch F1 §9.4 例外 ADR 包（partial 集中登记；非全量 ADR） |
| [phase2-datasource-raw-evidence.md](./phase2-datasource-raw-evidence.md) | Batch G1 N01 DataSourceConfig content_hash→Raw（非全连接器/非 certified） |
| [phase2-fact-revision-evidence.md](./phase2-fact-revision-evidence.md) | Batch G2 N24 Fact Revision 归档/抬号（非回滚 UI/非 certified） |
| [phase2-claim-revision-evidence.md](./phase2-claim-revision-evidence.md) | Batch H1 N24 Claim Revision 归档/抬号（非 Source/回滚 UI/非 certified） |
| [phase2-source-revision-evidence.md](./phase2-source-revision-evidence.md) | Batch H2 N24 Source Revision 归档/抬号（非回滚 UI/非 certified） |
| [phase2-revision-restore-evidence.md](./phase2-revision-restore-evidence.md) | Batch I1 N24 Revision Restore 程序化恢复（非回滚 UI/非 certified） |
| [phase2-revision-audit-evidence.md](./phase2-revision-audit-evidence.md) | Batch I2 N24 Revision Audit 账本内事件（非统一总线/非 certified） |
| [phase2-restore-approval-evidence.md](./phase2-restore-approval-evidence.md) | Batch I3 N24 审批式 Restore（非回滚 UI/非 certified） |
| [phase2-revision-action-bridge-evidence.md](./phase2-revision-action-bridge-evidence.md) | Batch I4 N24 Revision→ActionExecution 桥接（非全量总线/非 certified） |
| [phase2-revision-restore-http-evidence.md](./phase2-revision-restore-http-evidence.md) | Batch J1 N24 Revision Restore HTTP 薄路由（非管理端 UI/非 certified） |
| [phase2-revision-restore-ui-evidence.md](./phase2-revision-restore-ui-evidence.md) | Batch J2 N24 Revision Restore 管理端薄 UI（非全量总线/非 certified） |
| [phase2-unified-audit-view-evidence.md](./phase2-unified-audit-view-evidence.md) | Batch J3 N24 Package+Action+revision 只读统一视图（非写总线/非 certified） |
| [phase2-unified-audit-ui-evidence.md](./phase2-unified-audit-ui-evidence.md) | Batch J4 N24 Unified Audit 管理端薄 UI（非写总线/非 certified） |
| [phase2-unified-audit-bus-evidence.md](./phase2-unified-audit-bus-evidence.md) | Batch J5 N24 Unified Audit 写总线（非 ActionStore 合并/非 certified） |
| [phase2-unified-audit-hotpath-evidence.md](./phase2-unified-audit-hotpath-evidence.md) | Batch J6 N24 Package/Action 热路径写总线（非 ActionStore 合并/非 certified） |
| [phase2-unified-audit-action-store-evidence.md](./phase2-unified-audit-action-store-evidence.md) | Batch J7 N24 ActionStore.action_audit 汇入统一审计（非 certified） |
| [phase2-unified-audit-action-store-tenant-evidence.md](./phase2-unified-audit-action-store-tenant-evidence.md) | Batch J8 N24 ActionStore 物理 tenant_id（非 certified） |
| [phase2-unified-audit-action-store-tenant-backfill-evidence.md](./phase2-unified-audit-action-store-tenant-backfill-evidence.md) | Batch J9 N24 ActionStore tenant_id 存量回填（非 certified） |
| [phase2-cross-tenant-objectset-audit-evidence.md](./phase2-cross-tenant-objectset-audit-evidence.md) | Batch K1 N09 ObjectSet+UnifiedAudit 跨租户探针（非 Wiki/KB 全入口/非 certified） |
| [phase2-cross-tenant-wiki-kb-evidence.md](./phase2-cross-tenant-wiki-kb-evidence.md) | Batch K2 N09 Wiki/KB 跨租户探针（非 GraphRAG/非 certified） |
| [phase2-cross-tenant-graphrag-evidence.md](./phase2-cross-tenant-graphrag-evidence.md) | Batch K3 N09 GraphRAG 向量层跨租户（非图节点 ACL/非 certified） |
| [phase2-cross-tenant-graphrag-caller-evidence.md](./phase2-cross-tenant-graphrag-caller-evidence.md) | Batch K4 N09 CRAG/治理 GraphRAG tenant 透传（非 GraphIndex ACL/非 certified） |
| [phase2-cross-tenant-graphindex-evidence.md](./phase2-cross-tenant-graphindex-evidence.md) | Batch K5 N09 GraphIndex 图层跨租户（非全写入强制/非 certified） |
| [phase2-cross-tenant-graph-write-evidence.md](./phase2-cross-tenant-graph-write-evidence.md) | Batch K6 N09 extract→GraphIndex 写路径 tenant 强制（非 publish/snapshot/非 certified） |
| [phase2-cross-tenant-cross-domain-snapshot-evidence.md](./phase2-cross-tenant-cross-domain-snapshot-evidence.md) | Batch K7 N09 跨域写边/publish snapshot 租户分库（非 HTTP JWT 强制/非 certified） |
| [phase2-cross-tenant-ontology-editor-http-evidence.md](./phase2-cross-tenant-ontology-editor-http-evidence.md) | Batch K8 N09 ontology_editor publish/list HTTP tenant 注入（非全 CRUD/非 certified） |
| [phase2-cross-tenant-ontology-editor-crud-evidence.md](./phase2-cross-tenant-ontology-editor-crud-evidence.md) | Batch K9 N09 ontology_editor class/rollback tenant + 按租户清缓存（非 view/monitor/非 certified） |
| [phase2-cross-tenant-ontology-editor-side-crud-evidence.md](./phase2-cross-tenant-ontology-editor-side-crud-evidence.md) | Batch K10 N09 ontology_editor view/meta tenant + 按租户清缓存（非 monitor 物理 tenant/非 certified） |
| [phase2-cross-tenant-process-monitor-evidence.md](./phase2-cross-tenant-process-monitor-evidence.md) | Batch K11 N09 state_changes/process_monitor 物理 tenant（非 process_instances/非 certified） |

| [phase2-cross-tenant-process-instances-evidence.md](./phase2-cross-tenant-process-instances-evidence.md) | Batch K12 N09 process_instances + OntologyEngine tenant（非 auto_pipeline 强制/非 certified） |
| [phase2-cross-tenant-auto-ontology-pipeline-evidence.md](./phase2-cross-tenant-auto-ontology-pipeline-evidence.md) | Batch K13 N09 ingest→auto_ontology_pipeline tenant（非 staleness 多租户 KB/非 certified） |
| [phase2-cross-tenant-staleness-diagnostics-evidence.md](./phase2-cross-tenant-staleness-diagnostics-evidence.md) | Batch K14 N09 staleness/diagnostics 租户 KB 路径（非 cron 全租户/非 certified） |
| [phase2-cross-tenant-staleness-cron-evidence.md](./phase2-cross-tenant-staleness-cron-evidence.md) | Batch K15 N09 staleness cron/health 全租户枚举（非 garden·file·self_heal/非 certified） |
| [phase2-cross-tenant-staleness-garden-file-heal-evidence.md](./phase2-cross-tenant-staleness-garden-file-heal-evidence.md) | Batch K16 N09 garden/file/self_heal 租户扫描（非 metric 旁路/非 certified） |
| [phase2-cross-tenant-diagnostics-drift-identity-evidence.md](./phase2-cross-tenant-diagnostics-drift-identity-evidence.md) | Batch K17 N09 diagnostics drift 身份绑定（非 metric 旁路/非 certified） |
| [phase2-cross-tenant-metric-scoring-crud-evidence.md](./phase2-cross-tenant-metric-scoring-crud-evidence.md) | Batch K18 N09 metric/scoring/scenario/governance CRUD 租户（非 certified） |
| [phase2-cross-tenant-governance-maturity-evidence.md](./phase2-cross-tenant-governance-maturity-evidence.md) | Batch K19 N09 governance/maturity GraphIndex 租户透传（非 certified） |
| [phase2-cross-tenant-ontology-quality-evidence.md](./phase2-cross-tenant-ontology-quality-evidence.md) | Batch K20 N09 ontology quality GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-context-bus-health-evidence.md](./phase2-cross-tenant-context-bus-health-evidence.md) | Batch K21 N09 context_bus/system_health GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-evolver-seci-retrieval-evidence.md](./phase2-cross-tenant-evolver-seci-retrieval-evidence.md) | Batch K22 N09 evolver/SECI/retrieval/path/candidate GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-diagnostician-convergence-evidence.md](./phase2-cross-tenant-diagnostician-convergence-evidence.md) | Batch K23 N09 diagnostician/convergence/case/recon GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-wiki-graph-syscall-evidence.md](./phase2-cross-tenant-wiki-graph-syscall-evidence.md) | Batch K24 N09 wiki/graph syscall GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-wiki-ontology-engine-evidence.md](./phase2-cross-tenant-wiki-ontology-engine-evidence.md) | Batch K25 N09 wiki_ontology_engine GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-ontology-engine-evidence.md](./phase2-cross-tenant-ontology-engine-evidence.md) | Batch K26 N09 ontology_engine GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-builtin-handlers-evidence.md](./phase2-cross-tenant-builtin-handlers-evidence.md) | Batch K27 N09 builtin_handlers GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-fde-service-evidence.md](./phase2-cross-tenant-fde-service-evidence.md) | Batch K28 N09 FDE service GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-facade-system-infra-evidence.md](./phase2-cross-tenant-facade-system-infra-evidence.md) | Batch K29 N09 facade/system/eval/infra GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-skills-pipeline-router-evidence.md](./phase2-cross-tenant-skills-pipeline-router-evidence.md) | Batch K30 N09 skills/pipeline/router GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-platform-fde-api-evidence.md](./phase2-cross-tenant-platform-fde-api-evidence.md) | Batch K31 N09 platform FDE API wave1 GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-platform-fde-api-wave2-evidence.md](./phase2-cross-tenant-platform-fde-api-wave2-evidence.md) | Batch K32 N09 platform FDE API wave2 GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-handlers-scripts-evidence.md](./phase2-cross-tenant-handlers-scripts-evidence.md) | Batch K33 N09 handlers/scripts GraphIndex 租户（非 certified） |
| [phase2-cross-tenant-graphindex-ctor-evidence.md](./phase2-cross-tenant-graphindex-ctor-evidence.md) | Batch K34 N09 GraphIndex 直构 / branch DB 租户（非 certified） |
| [phase2-cross-tenant-scripts-ctor-evidence.md](./phase2-cross-tenant-scripts-ctor-evidence.md) | Batch K35 N09 scripts GraphIndex 直构租户（非 certified） |
| [phase2-cross-tenant-branch-registry-evidence.md](./phase2-cross-tenant-branch-registry-evidence.md) | Batch K36 N09 branch registry 租户键（非 certified） |
| [phase2-cross-tenant-branch-yaml-evidence.md](./phase2-cross-tenant-branch-yaml-evidence.md) | Batch K37 N09 branch YAML 租户前缀（非 certified） |
| [phase2-cross-tenant-fde-tracking-domain-evidence.md](./phase2-cross-tenant-fde-tracking-domain-evidence.md) | Batch K38 N09 FDE tracking domain 去硬编码（非 certified） |
| [phase2-cross-tenant-fde-terms-atom-domain-evidence.md](./phase2-cross-tenant-fde-terms-atom-domain-evidence.md) | Batch K39 N09 FDE terms/atom/kb domain 去硬编码（非 certified） |
| [phase2-cross-tenant-harness-atom-domain-evidence.md](./phase2-cross-tenant-harness-atom-domain-evidence.md) | Batch K40 N09 harness atom/kb/terms domain 去硬编码（非 certified） |
| [phase2-cross-tenant-competition-domain-evidence.md](./phase2-cross-tenant-competition-domain-evidence.md) | Batch K41 N09 competition domain 去硬编码（非 certified） |
| [phase2-cross-tenant-graphindex-ctor-domain-evidence.md](./phase2-cross-tenant-graphindex-ctor-domain-evidence.md) | Batch K42 N09 GraphIndex ctor domain 去硬编码（非 certified） |
| [phase2-cross-tenant-kb-domain-fallbacks-evidence.md](./phase2-cross-tenant-kb-domain-fallbacks-evidence.md) | Batch K43 N09 KB/tracking request fallbacks 去硬编码（非 certified） |
| [phase2-cross-tenant-kb-domain-defaults-evidence.md](./phase2-cross-tenant-kb-domain-defaults-evidence.md) | Batch K44 N09 KB domain 签名默认去硬编码（非 certified） |
| [phase2-cross-tenant-default-graph-domain-defaults-evidence.md](./phase2-cross-tenant-default-graph-domain-defaults-evidence.md) | Batch K45 N09 default graph domain 签名默认去硬编码（非 certified） |
| [phase2-cross-tenant-it-ops-domain-defaults-evidence.md](./phase2-cross-tenant-it-ops-domain-defaults-evidence.md) | Batch K46 N09 it-ops/data-gov domain 签名默认去硬编码（非 certified） |
| [phase2-cross-tenant-system-domain-defaults-evidence.md](./phase2-cross-tenant-system-domain-defaults-evidence.md) | Batch K47 N09 aiplat-system domain 签名默认去硬编码（非 certified） |
| [phase2-cross-tenant-icebreaker-config-evidence.md](./phase2-cross-tenant-icebreaker-config-evidence.md) | Batch K48 N09 icebreaker 业务域键配置外置（非 certified） |
| [phase2-cross-tenant-default-tenant-ssot-evidence.md](./phase2-cross-tenant-default-tenant-ssot-evidence.md) | Batch K49 N09 default tenant SSOT（knowledge 层，非 certified） |
| [phase2-cross-tenant-default-tenant-outer-evidence.md](./phase2-cross-tenant-default-tenant-outer-evidence.md) | Batch K50 N09 default tenant 外层签名默认（非 certified） |
| [phase2-cross-tenant-default-tenant-sql-literals-evidence.md](./phase2-cross-tenant-default-tenant-sql-literals-evidence.md) | Batch K51 N09 default tenant SQL/赋值字面量（非 certified） |
| [phase2-cross-tenant-default-collection-ssot-evidence.md](./phase2-cross-tenant-default-collection-ssot-evidence.md) | Batch K52 N09 default collection/profile SSOT（非 certified） |
| [phase2-cross-tenant-default-session-ssot-evidence.md](./phase2-cross-tenant-default-session-ssot-evidence.md) | Batch K53 N09 default session SSOT（非 certified） |
| [phase2-cross-tenant-default-tenant-runtime-fallbacks-evidence.md](./phase2-cross-tenant-default-tenant-runtime-fallbacks-evidence.md) | Batch K54 N09 default tenant 运行时回退（非 certified） |
| [phase2-cross-tenant-facade-tenant-runtime-fallbacks-evidence.md](./phase2-cross-tenant-facade-tenant-runtime-fallbacks-evidence.md) | Batch K55 N09 facade/diagnostics tenant 运行时回退（非 certified） |
| [phase2-cross-tenant-platform-tenant-runtime-fallbacks-evidence.md](./phase2-cross-tenant-platform-tenant-runtime-fallbacks-evidence.md) | Batch K56 N09 platform routes/kb/delivery tenant 运行时回退（非 certified） |
| [phase2-cross-tenant-apps-ontology-tenant-runtime-fallbacks-evidence.md](./phase2-cross-tenant-apps-ontology-tenant-runtime-fallbacks-evidence.md) | Batch K57 N09 apps/ontology tenant 运行时回退（非 certified） |
| [phase2-cross-tenant-loop-agent-tenant-runtime-fallbacks-evidence.md](./phase2-cross-tenant-loop-agent-tenant-runtime-fallbacks-evidence.md) | Batch K58 N09 loop/agent tenant+session 运行时回退（非 certified） |
| [phase2-cross-tenant-session-runtime-fallbacks-evidence.md](./phase2-cross-tenant-session-runtime-fallbacks-evidence.md) | Batch K59 N09 session 运行时回退加深（非 certified） |
| [phase2-cross-tenant-agents-pipeline-session-fallbacks-evidence.md](./phase2-cross-tenant-agents-pipeline-session-fallbacks-evidence.md) | Batch K60 N09 agents/pipeline session 运行时回退（非 certified） |
| [phase2-cross-tenant-integration-memory-session-fallbacks-evidence.md](./phase2-cross-tenant-integration-memory-session-fallbacks-evidence.md) | Batch K61 N09 integration/memory session 运行时回退（非 certified） |
| [phase2-cross-tenant-collection-namespace-fallbacks-evidence.md](./phase2-cross-tenant-collection-namespace-fallbacks-evidence.md) | Batch K62 N09 collection/namespace 运行时回退（非 certified） |
| [phase2-cross-tenant-domain-runtime-fallbacks-evidence.md](./phase2-cross-tenant-domain-runtime-fallbacks-evidence.md) | Batch K63 N09 domain_id 运行时回退（非 certified） |
| [phase2-cross-tenant-view-runtime-fallbacks-evidence.md](./phase2-cross-tenant-view-runtime-fallbacks-evidence.md) | Batch K64 N09 view_name 运行时回退（非 certified） |
| [phase2-cross-tenant-workspace-runtime-fallbacks-evidence.md](./phase2-cross-tenant-workspace-runtime-fallbacks-evidence.md) | Batch K65 N09 workspace_id 运行时回退（非 certified） |
| [phase2-cross-tenant-profile-tenant-env-fallbacks-evidence.md](./phase2-cross-tenant-profile-tenant-env-fallbacks-evidence.md) | Batch K66 N09 profile + AIPLAT_DEFAULT_TENANT 运行时回退（非 certified） |
| [phase2-cross-tenant-query-form-signature-defaults-evidence.md](./phase2-cross-tenant-query-form-signature-defaults-evidence.md) | Batch K67 N09 Query/Form/签名默认参数（非 certified） |
| [phase2-cross-tenant-builder-module-defaults-evidence.md](./phase2-cross-tenant-builder-module-defaults-evidence.md) | Batch K68 N09 builder module_id 默认（非 certified） |
| [phase2-cross-tenant-misc-label-defaults-evidence.md](./phase2-cross-tenant-misc-label-defaults-evidence.md) | Batch K69 N09 杂项 label 默认（非 certified） |
| [phase2-cross-tenant-runtime-default-mop-evidence.md](./phase2-cross-tenant-runtime-default-mop-evidence.md) | Batch K70 N09 运行时 default 漏网清扫（非 certified；本线终点） |
| [phase2-core-cert-path-evidence.md](./phase2-core-cert-path-evidence.md) | Core 可认证路径：等级映射 + core_ready + 人工徽章（朱鸿林已确认） |
| [phase2-extended-cert-path-evidence.md](./phase2-extended-cert-path-evidence.md) | Extended 可认证路径：N.3 六项 + extended_ready + 人工徽章（朱莹已确认） |
| [phase2-operational-cert-path-evidence.md](./phase2-operational-cert-path-evidence.md) | Operational 可认证路径：N.4 六项 + operational_ready + 人工徽章（朱莹已确认） |
| [phase2-full-cert-path-evidence.md](./phase2-full-cert-path-evidence.md) | 全量可认证路径：full_ready + 三级徽章 + 人工全量徽章（朱向群已确认，conditional） |

试点域：`lock-service` · 目标等级：Core（`core_ready` 可判定；**签字认证**见 `pilot-core-approval-record.pending.json`）· G0/G1/G2 测量通过 ≠ 附录 N 全量符合。
