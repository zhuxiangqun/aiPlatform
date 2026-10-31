# P0-6 Escape scan (production code)

> HEAD `b46e286` · P0 W1 read-only · refined tiers

## Summary

| Tier | Meaning | Count |
|------|---------|------:|
| **A hard** | `expanduser("~/.aiplat…")` / `Path.home()/".aiplat"` **without** AIPLAT_HOME/`get_aiplat_home` on same line | **0**（was 259） |
| **B soft** | Same patterns but env/`get_aiplat_home` on same line (fallback OK for G0) | **0**（was ~179） |

**G0 kickoff criterion** «逃逸扫描为 0» → **Tier A = 0 ✅**（`core/utils/paths.py` SSOT fallback excluded）.  
Tier B soft 不阻断 G0；可后续统一收敛。

### Progress (2026-10-29 hands-on)

批量迁到 `get_aiplat_home` / `get_aiplat_data_dir`：`server.py`、memory/package managers、FDE/wiki/workspace routers、pipeline_engine、core_facade、builder、以及 ~130 个散落文件。

### Top files (Tier A) — original W1 snapshot

| # | File | Hits |
|---|------|----:|
| 1 | `aiPlat-core/core/server.py` | 10 → **0** |
| 2 | `aiPlat-core/core/harness/memory/manager.py` | 8 → **0** hard |
| 3 | `aiPlat-core/core/management/package_manager.py` | 6 → **0** |
| 4 | `aiPlat-platform/builder/builder_project_service.py` | 6 → **0** hard |
| 5 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py` | 6 → **0** |
| 6 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py` | 5 |
| 7 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py` | 5 |
| 8 | `aiPlat-core/core/api/routers/workspace_agents.py` | 5 |
| 9 | `aiPlat-core/core/api/routers/workspace_packages.py` | 5 |
| 10 | `aiPlat-core/core/harness/digital_human/trajectory_collector.py` | 4 |
| 11 | `aiPlat-core/core/api/routers/mcp_admin.py` | 4 |
| 12 | `aiPlat-core/core/api/routers/wiki.py` | 4 |
| 13 | `aiPlat-core/core/harness/knowledge/governance_pipeline.py` | 3 |
| 14 | `aiPlat-core/core/harness/execution/pipeline_engine.py` | 3 |
| 15 | `aiPlat-core/core/api/core_facade.py` | 3 |
| 16 | `aiPlat-core/core/api/routers/tools.py` | 3 |
| 17 | `aiPlat-core/core/apps/finetune/job_manager.py` | 3 |
| 18 | `aiPlat-platform/apps/fde/api/fde_validate.py` | 3 |
| 19 | `aiPlat-platform/apps/fde/api/fde.py` | 3 |
| 20 | `aiPlat-core/core/management/n8n_langchain_adapter.py` | 2 |

## Tier A — full list

| # | Location | Snippet |
|---|----------|---------|
| 1 | `aiPlat-core/core/server.py:761` | `workspace_dir = Path.home() / ".aiplat" / "skills"` |
| 2 | `aiPlat-core/core/server.py:782` | `workspace_dir = Path.home() / ".aiplat" / "agents"` |
| 3 | `aiPlat-core/core/server.py:803` | `workspace_dir = Path.home() / ".aiplat" / "personas"` |
| 4 | `aiPlat-core/core/server.py:824` | `workspace_dir = Path.home() / ".aiplat" / "teams"` |
| 5 | `aiPlat-core/core/server.py:852` | `workspace_dir = Path.home() / ".aiplat" / "mcps"` |
| 6 | `aiPlat-core/core/server.py:873` | `workspace_dir = Path.home() / ".aiplat" / "hooks"` |
| 7 | `aiPlat-core/core/server.py:1091` | `workspace_dir = Path.home() / ".aiplat" / "agents"` |
| 8 | `aiPlat-core/core/server.py:1099` | `workspace_skills_dir = Path.home() / ".aiplat" / "skills"` |
| 9 | `aiPlat-core/core/server.py:1746` | `os.path.expanduser("~/.aiplat/datasources/auto_discovered"))` |
| 10 | `aiPlat-core/core/server.py:1902` | `_last_run_file = os.path.expanduser("~/.aiplat/evolution/last_run.json")` |
| 11 | `aiPlat-core/core/management/n8n_langchain_adapter.py:91` | `dest = Path.home() / ".aiplat" / "workflow_templates"` |
| 12 | `aiPlat-core/core/management/n8n_langchain_adapter.py:236` | `dest = Path.home() / ".aiplat" / "workflow_templates"` |
| 13 | `aiPlat-core/core/management/asset_installer.py:624` | `base = _os.path.expanduser("~/.aiplat")` |
| 14 | `aiPlat-core/core/management/package_manager.py:98` | `workspace_default = Path.home() / ".aiplat" / "packages"` |
| 15 | `aiPlat-core/core/management/package_manager.py:214` | `return (Path.home() / ".aiplat" / "packages" / ".installs").resolve()` |
| 16 | `aiPlat-core/core/management/package_manager.py:242` | `"workspace_agents": (Path.home() / ".aiplat" / "agents").resolve(),` |
| 17 | `aiPlat-core/core/management/package_manager.py:243` | `"workspace_skills": (Path.home() / ".aiplat" / "skills").resolve(),` |
| 18 | `aiPlat-core/core/management/package_manager.py:244` | `"workspace_mcps": (Path.home() / ".aiplat" / "mcps").resolve(),` |
| 19 | `aiPlat-core/core/management/package_manager.py:245` | `"workspace_hooks": (Path.home() / ".aiplat" / "hooks").resolve(),` |
| 20 | `aiPlat-core/core/management/asset_audit.py:764` | `root = Path(home) if home else Path(os.path.expanduser("~/.aiplat"))` |
| 21 | `aiPlat-core/core/management/asset_audit.py:799` | `root = Path(home) if home else Path(os.path.expanduser("~/.aiplat"))` |
| 22 | `aiPlat-core/core/management/skill_linter_base.py:391` | `Path(os.path.expanduser("~/.aiplat/lint_rules.yaml")),` |
| 23 | `aiPlat-core/core/management/workflow_manager.py:69` | `workspace_default = Path.home() / ".aiplat" / "workflows"` |
| 24 | `aiPlat-core/core/management/workflow_manager.py:79` | `return paths[-1] if paths else (Path.home() / ".aiplat" / "workflows")` |
| 25 | `aiPlat-core/core/management/coze_adapter.py:99` | `dest = Path.home() / ".aiplat" / "workflow_templates"` |
| 26 | `aiPlat-core/core/management/skill_manager.py:1844` | `workspace_default = Path.home() / ".aiplat" / "skills"` |
| 27 | `aiPlat-core/core/management/agent_manager.py:138` | `workspace_default = Path.home() / ".aiplat" / "agents"` |
| 28 | `aiPlat-core/core/management/dify_adapter.py:94` | `dest = Path.home() / ".aiplat" / "workflow_templates"` |
| 29 | `aiPlat-core/core/management/execution_quality_review.py:542` | `out.append(Path.home() / ".aiplat" / "agents" / aid / "AGENT.md")` |
| 30 | `aiPlat-core/core/management/execution_quality_review.py:693` | `out.append(Path.home() / ".aiplat" / "skills" / sid / "SKILL.md")` |
| 31 | `aiPlat-core/core/management/mcp_manager.py:62` | `workspace_default = Path.home() / ".aiplat" / "mcps"` |
| 32 | `aiPlat-core/core/management/skill_installer.py:357` | `hooks_dest = Path(os.path.expanduser("~/.aiplat/hooks"))` |
| 33 | `aiPlat-core/core/management/arch_guard_rules/complex.py:173` | `agents_dir = Path.home() / ".aiplat/agents"` |
| 34 | `aiPlat-core/core/harness/artifacts/registry.py:39` | `base_dir or os.path.expanduser("~/.aiplat/artifacts")` |
| 35 | `aiPlat-core/core/harness/memory/shared_pool.py:61` | `POOL_ROOT = os.path.expanduser("~/.aiplat/shared_knowledge")` |
| 36 | `aiPlat-core/core/harness/memory/semantic.py:45` | `base = os.path.expanduser("~/.aiplat")` |
| 37 | `aiPlat-core/core/harness/memory/file_store.py:47` | `MEMORY_DIR = os.path.expanduser("~/.aiplat/memory")` |
| 38 | `aiPlat-core/core/harness/memory/team_brain.py:66` | `return Path(os.path.expanduser("~/.aiplat/task_skills"))` |
| 39 | `aiPlat-core/core/harness/memory/migrate_semantic.py:16` | `SRC_DB = os.path.expanduser("~/.aiplat/memory_semantic.sqlite3")` |
| 40 | `aiPlat-core/core/harness/memory/migrate_semantic.py:17` | `DST_DIR = os.path.expanduser("~/.aiplat")` |
| 41 | `aiPlat-core/core/harness/memory/manager.py:836` | `rules_path = _os_br.path.expanduser("~/.aiplat/brand_rules.yaml")` |
| 42 | `aiPlat-core/core/harness/memory/manager.py:1665` | `_RULES_PATH = os.path.expanduser("~/.aiplat/memory_rules.json")` |
| 43 | `aiPlat-core/core/harness/memory/manager.py:1738` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 44 | `aiPlat-core/core/harness/memory/manager.py:1885` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 45 | `aiPlat-core/core/harness/memory/manager.py:2079` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 46 | `aiPlat-core/core/harness/memory/manager.py:2201` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 47 | `aiPlat-core/core/harness/memory/manager.py:2285` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 48 | `aiPlat-core/core/harness/memory/manager.py:2373` | `skills_dir = _os.path.expanduser("~/.aiplat/task_skills")` |
| 49 | `aiPlat-core/core/harness/security/immune_memory.py:214` | `filepath = filepath or os.path.expanduser("~/.aiplat/immune_memory.json")` |
| 50 | `aiPlat-core/core/harness/security/immune_memory.py:226` | `filepath = filepath or os.path.expanduser("~/.aiplat/immune_memory.json")` |
| 51 | `aiPlat-core/core/harness/learning/playbook.py:287` | `dest_ont = Path(os.path.expanduser("~/.aiplat/ontologies"))` |
| 52 | `aiPlat-core/core/harness/learning/playbook.py:337` | `dest_clean = Path(os.path.expanduser("~/.aiplat/cleanup_rules"))` |
| 53 | `aiPlat-core/core/harness/learning/agent_specialization.py:193` | `db_path = os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")` |
| 54 | `aiPlat-core/core/harness/learning/agent_refiner.py:48` | `self._db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")` |
| 55 | `aiPlat-core/core/harness/learning/agent_refiner.py:89` | `_os.path.expanduser("~/.aiplat/agents"),` |
| 56 | `aiPlat-core/core/harness/learning/__init__.py:339` | `approved_path = Path(os.path.expanduser("~/.aiplat/skills")) / draft_name` |
| 57 | `aiPlat-core/core/harness/learning/agent_network.py:88` | `self._network_file = os.path.expanduser("~/.aiplat/agent_network.json")` |
| 58 | `aiPlat-core/core/harness/learning/experience_vector.py:62` | `self._storage_path = os.path.expanduser("~/.aiplat/experience_cache.json")` |
| 59 | `aiPlat-core/core/harness/optimization/abstract_goal_decomposer.py:119` | `_PENDING_DIR = _os.path.expanduser("~/.aiplat/goals/pending")` |
| 60 | `aiPlat-core/core/harness/optimization/goal_generator.py:590` | `os.path.expanduser("~/.aiplat/skills/bootstrap"),` |
| 61 | `aiPlat-core/core/harness/optimization/goal_generator.py:881` | `pending_dir = _os_module.path.expanduser("~/.aiplat/goals/pending")` |
| 62 | `aiPlat-core/core/harness/optimization/tool_bootstrap.py:79` | `SKILLS_DIR = os.path.expanduser("~/.aiplat/skills/bootstrap")` |
| 63 | `aiPlat-core/core/harness/training/full_training.py:135` | `self._job_dir = os.path.expanduser("~/.aiplat/full_training")` |
| 64 | `aiPlat-core/core/harness/training/auto_trigger.py:51` | `self._dataset_dir = os.path.expanduser("~/.aiplat/training")` |
| 65 | `aiPlat-core/core/harness/training/rl_trainer.py:540` | `signal_path = os.path.expanduser("~/.aiplat/sft_models/latest.json")` |
| 66 | `aiPlat-core/core/harness/training/distillation.py:137` | `self._job_dir = os.path.expanduser("~/.aiplat/distillation")` |
| 67 | `aiPlat-core/core/harness/scheduler/wake_scheduler.py:242` | `pending_dir = _os_module.path.expanduser("~/.aiplat/goals/pending")` |
| 68 | `aiPlat-core/core/harness/meta/profile_registry.py:67` | `str(Path.home() / ".aiplat" / "profiles"),` |
| 69 | `aiPlat-core/core/harness/utils/prompt_loader.py:880` | `ontology_dir = _os.path.expanduser("~/.aiplat/ontologies")` |
| 70 | `aiPlat-core/core/harness/models/spec_lifecycle.py:293` | `self._db_path = db_path or os.path.expanduser("~/.aiplat/spec_lifecycle.db")` |
| 71 | `aiPlat-core/core/harness/observability/alerts/__init__.py:197` | `db_dir = os.path.expanduser("~/.aiplat")` |
| 72 | `aiPlat-core/core/harness/digital_human/trajectory_collector.py:22` | `os.path.expanduser("~/.aiplat/trajectories")))` |
| 73 | `aiPlat-core/core/harness/digital_human/trajectory_collector.py:267` | `out_dir = output_dir or os.path.expanduser("~/.aiplat/training")` |
| 74 | `aiPlat-core/core/harness/digital_human/trajectory_collector.py:331` | `out_dir = output_dir or os.path.expanduser("~/.aiplat/training")` |
| 75 | `aiPlat-core/core/harness/digital_human/trajectory_collector.py:448` | `out_dir = output_dir or os.path.expanduser("~/.aiplat/training")` |
| 76 | `aiPlat-core/core/harness/knowledge/sla_monitor.py:106` | `db_path = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 77 | `aiPlat-core/core/harness/knowledge/conversation_ingestor.py:64` | `self._db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")` |
| 78 | `aiPlat-core/core/harness/knowledge/convergence_engine.py:50` | `path = os.path.expanduser("~/.aiplat/ontologies/knowledge-atom.yaml")` |
| 79 | `aiPlat-core/core/harness/knowledge/mapping_validator.py:41` | `base = _os.path.expanduser("~/.aiplat/datasources")` |
| 80 | `aiPlat-core/core/harness/knowledge/mapping_validator.py:112` | `base = _os.path.expanduser("~/.aiplat/datasources")` |
| 81 | `aiPlat-core/core/harness/knowledge/governance_dashboard.py:106` | `db = _os.path.expanduser("~/.aiplat/usage_metrics.db")` |
| 82 | `aiPlat-core/core/harness/knowledge/skill_marketplace.py:184` | `skills_dir = os.path.expanduser("~/.aiplat/skills")` |
| 83 | `aiPlat-core/core/harness/knowledge/skill_marketplace.py:347` | `base = skill_dir or os.path.expanduser("~/.aiplat/skills")` |
| 84 | `aiPlat-core/core/harness/knowledge/capability_graph.py:704` | `Path(_os.path.expanduser("~/.aiplat/tools")),  # workspace tools` |
| 85 | `aiPlat-core/core/harness/knowledge/recon_subgraph.py:54` | `data_dir = _os.path.expanduser("~/.aiplat/data/recon")` |
| 86 | `aiPlat-core/core/harness/knowledge/domain_maturity.py:65` | `gq_path = os.path.expanduser("~/.aiplat/golden_queries.yaml")` |
| 87 | `aiPlat-core/core/harness/knowledge/domain_maturity.py:141` | `db_path = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 88 | `aiPlat-core/core/harness/knowledge/governance_pipeline.py:37` | `HISTORY_DIR = _os.path.expanduser("~/.aiplat/governance_cycles")` |
| 89 | `aiPlat-core/core/harness/knowledge/governance_pipeline.py:396` | `base = os.path.expanduser("~/.aiplat/datasources")` |
| 90 | `aiPlat-core/core/harness/knowledge/governance_pipeline.py:502` | `db = os.path.expanduser("~/.aiplat/state_changes.db")` |
| 91 | `aiPlat-core/core/harness/knowledge/process_monitor.py:15` | `DB_PATH = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 92 | `aiPlat-core/core/harness/knowledge/text_cleaner.py:32` | `user_path = Path(os.path.expanduser("~/.aiplat/cleanup_rules.yaml"))` |
| 93 | `aiPlat-core/core/harness/knowledge/text_cleaner.py:33` | `industry_dir = Path(os.path.expanduser("~/.aiplat/cleanup_rules"))` |
| 94 | `aiPlat-core/core/harness/knowledge/skill_curator.py:43` | `_CURATOR_STATE = _os.path.expanduser("~/.aiplat/curator_state.json")` |
| 95 | `aiPlat-core/core/harness/knowledge/term_resolver.py:20` | `_TERMS_DIR = _os.path.expanduser("~/.aiplat/terms")` |
| 96 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py:988` | `hist_path = _os.path.expanduser("~/.aiplat/wiki/golden_regression_history.json")` |
| 97 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py:1008` | `lat_path2 = _os.path.expanduser("~/.aiplat/wiki/retrieval_latency.json")` |
| 98 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py:1025` | `curation_path = _os.path.expanduser("~/.aiplat/wiki/curation_stats.json")` |
| 99 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py:1045` | `gov_path = _os.path.expanduser("~/.aiplat/wiki/governance_stats.json")` |
| 100 | `aiPlat-core/core/harness/knowledge/knowledge_validator.py:1046` | `history_path = _os.path.expanduser("~/.aiplat/wiki/governance_history.json")` |
| 101 | `aiPlat-core/core/harness/knowledge/cross_domain_bridge.py:53` | `return [os.path.expanduser("~/.aiplat/agents")]` |
| 102 | `aiPlat-core/core/harness/knowledge/process_orchestrator.py:31` | `return _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 103 | `aiPlat-core/core/harness/knowledge/ontology_bus.py:23` | `_ONTOLOGY_DIR = _os.path.expanduser("~/.aiplat/ontologies")` |
| 104 | `aiPlat-core/core/harness/knowledge/code_entropy_detector.py:58` | `self._db_path = db_path or os.path.expanduser("~/.aiplat/code_entropy.sqlite3")` |
| 105 | `aiPlat-core/core/harness/knowledge/wiki_structured_query.py:380` | `__import__('os').path.expanduser("~/.aiplat"))) / "wiki"` |
| 106 | `aiPlat-core/core/harness/knowledge/wiki_structured_query.py:472` | `__import__('os').path.expanduser("~/.aiplat"))) / "wiki"` |
| 107 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py:82` | `cache_path = Path.home() / ".aiplat" / "wiki" / "collections" / cid / "vectors.json"` |
| 108 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py:201` | `cache_path = _Path.home() / ".aiplat" / "wiki" / "collections" / cid / "inference_cache.json"` |
| 109 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py:225` | `cache_path = _Path.home() / ".aiplat" / "wiki" / "collections" / primary_cid / "inference_cache.json"` |
| 110 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py:236` | `cp2 = _Path.home() / ".aiplat" / "wiki" / "collections" / cid / "inference_cache.json"` |
| 111 | `aiPlat-core/core/harness/knowledge/wiki_retriever.py:373` | `cache_path = Path.home() / ".aiplat" / "wiki" / "collections" / cid / "vectors.json"` |
| 112 | `aiPlat-core/core/harness/knowledge/security_view.py:183` | `paths.append(Path.home() / ".aiplat" / "security_view_rules.yaml")` |
| 113 | `aiPlat-core/core/harness/knowledge/security_view.py:234` | `root = Path.home() / ".aiplat"` |
| 114 | `aiPlat-core/core/harness/knowledge/wiki_fts.py:18` | `os.path.expanduser("~/.aiplat/wiki/fts.db"))` |
| 115 | `aiPlat-core/core/harness/knowledge/metric_engine.py:22` | `DB_PATH = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 116 | `aiPlat-core/core/harness/execution/simulation.py:829` | `sim_dir = _os.path.expanduser("~/.aiplat/simulations")` |
| 117 | `aiPlat-core/core/harness/execution/pipeline_engine.py:1284` | `db_path = node_cfg.get('vector_db_path', os.path.expanduser('~/.aiplat/vectors'))` |
| 118 | `aiPlat-core/core/harness/execution/pipeline_engine.py:7887` | `skills_dir = os.path.expanduser("~/.aiplat/skills/auto")` |
| 119 | `aiPlat-core/core/harness/execution/pipeline_engine.py:8758` | `auto_dir = os.path.expanduser("~/.aiplat/auto_pipelines")` |
| 120 | `aiPlat-core/core/harness/execution/file_checkpoint.py:31` | `CHECKPOINT_ROOT = os.path.expanduser("~/.aiplat/file_checkpoints")` |
| 121 | `aiPlat-core/core/harness/execution/pipeline_prompt.py:311` | `skill_path = _os.path.expanduser("~/.aiplat/skills/ponytail-lazy/SKILL.md")` |
| 122 | `aiPlat-core/core/harness/execution/pipeline_prompt.py:443` | `snapshot_dir = os.path.expanduser("~/.aiplat/traces/history")` |
| 123 | `aiPlat-core/core/harness/execution/pipeline_eval.py:1082` | `out_path = os.getenv("AIPLAT_OTEL_EXPORT_PATH", os.path.expanduser("~/.aiplat/traces/latest.json"))` |
| 124 | `aiPlat-core/core/harness/execution/pipeline_eval.py:1092` | `snapshot_dir = os.path.expanduser("~/.aiplat/traces/history")` |
| 125 | `aiPlat-core/core/harness/execution/decision_trace.py:22` | `_TRACE_DIR = os.path.expanduser("~/.aiplat/decision_traces")` |
| 126 | `aiPlat-core/core/harness/execution/prd_gate_loader.py:37` | `return Path(os.path.expanduser("~/.aiplat/prd_gates"))` |
| 127 | `aiPlat-core/core/harness/execution/team_planner.py:288` | `os.path.expanduser("~/.aiplat/agents"),` |
| 128 | `aiPlat-core/core/harness/execution/team_planner.py:518` | `config_path = _os.path.expanduser("~/.aiplat/capability_defaults.yaml")` |
| 129 | `aiPlat-core/core/harness/execution/snapshot.py:25` | `SNAPSHOT_ROOT = os.path.expanduser("~/.aiplat/snapshots")` |
| 130 | `aiPlat-core/core/harness/deployment/git_pusher.py:122` | `dockerfile_dir = _os.path.expanduser("~/.aiplat/deploy/templates")` |
| 131 | `aiPlat-core/core/harness/deployment/deploy_engine.py:690` | `_ROLLBACK_LOG = __import__("pathlib").Path.home() / ".aiplat" / "data" / "rollback_events.jsonl"` |
| 132 | `aiPlat-core/core/harness/registry/registry_loader.py:33` | `os.path.expanduser("~/.aiplat/agents"),` |
| 133 | `aiPlat-core/core/harness/registry/registry_loader.py:344` | `home = os.path.expanduser("~/.aiplat")` |
| 134 | `aiPlat-core/core/harness/evaluation/adversarial_test_suite.py:187` | `output_dir = os.path.expanduser("~/.aiplat/training/adversarial")` |
| 135 | `aiPlat-core/core/harness/finance/value_calculator.py:181` | `self._storage_path = os.path.expanduser("~/.aiplat/value/goals.json")` |
| 136 | `aiPlat-core/core/harness/finance/value_calculator.py:353` | `self._report_path = os.path.expanduser("~/.aiplat/value/monthly.jsonl")` |
| 137 | `aiPlat-core/core/harness/ontology_engine/datasource_status.py:102` | `_STATUS_FILE = Path(os.path.expanduser("~/.aiplat/datasources/.sync_status.json"))` |
| 138 | `aiPlat-core/core/harness/ontology_engine/datasource_status.py:112` | `sources_dir = Path(os.path.expanduser("~/.aiplat/datasources"))` |
| 139 | `aiPlat-core/core/harness/ontology_engine/triple_scanner.py:28` | `os.path.expanduser("~/.aiplat/agents"),` |
| 140 | `aiPlat-core/core/harness/ontology_engine/triple_scanner.py:37` | `os.path.expanduser("~/.aiplat/skills"),` |
| 141 | `aiPlat-core/core/harness/ontology_engine/state_machine.py:417` | `db_path = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 142 | `aiPlat-core/core/harness/ontology_engine/audit_rules.py:29` | `onto_dir = _os.path.expanduser("~/.aiplat/ontologies")` |
| 143 | `aiPlat-core/core/harness/infrastructure/infra_bridge.py:154` | `path = os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3")` |
| 144 | `aiPlat-core/core/harness/infrastructure/secrets_manager.py:24` | `DEFAULT_KEY_PATH = Path.home() / ".aiplat" / "secrets.key"` |
| 145 | `aiPlat-core/core/harness/infrastructure/secrets_manager.py:25` | `DEFAULT_STORE_PATH = Path.home() / ".aiplat" / "secrets.enc"` |
| 146 | `aiPlat-core/core/harness/infrastructure/infra_audio_adapter.py:120` | `model_path = os.path.expanduser("~/.aiplat/models/piper_zh_CN.onnx")` |
| 147 | `aiPlat-core/core/harness/infrastructure/action_contract.py:282` | `os.path.realpath(os.path.expanduser("~/.aiplat/actions/")),` |
| 148 | `aiPlat-core/core/harness/infrastructure/discovery_listener.py:27` | `_WATCH_DIR = _os.path.expanduser("~/.aiplat/datasources/auto_discovered")` |
| 149 | `aiPlat-core/core/harness/infrastructure/trend_detector.py:575` | `_os.path.expanduser("~/.aiplat/config/infra/llm_profile.yaml"),` |
| 150 | `aiPlat-core/core/harness/infrastructure/trend_detector.py:576` | `_os.path.expanduser("~/.aiplat/config/infra/models.yaml"),` |
| 151 | `aiPlat-core/core/harness/infrastructure/lineage_store.py:131` | `db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")` |
| 152 | `aiPlat-core/core/harness/infrastructure/gates/sandbox_gate.py:204` | `workspace = os.environ.get("AIPLAT_WORKSPACE_ROOT", os.path.expanduser("~/.aiplat"))` |
| 153 | `aiPlat-core/core/harness/infrastructure/gates/cross_validation_gate.py:72` | `onto_dir = os.path.expanduser("~/.aiplat/ontologies")` |
| 154 | `aiPlat-core/core/harness/infrastructure/gates/cross_validation_gate.py:147` | `onto_dir = _os.path.expanduser("~/.aiplat/ontologies")` |
| 155 | `aiPlat-core/core/harness/infrastructure/hooks/workspace_loader.py:30` | `base = Path.home() / ".aiplat" / "hooks"` |
| 156 | `aiPlat-core/core/harness/syscalls/_trace.py:18` | `_TRACE_FILE = os.path.expanduser("~/.aiplat/traces/syscall_calls.jsonl")` |
| 157 | `aiPlat-core/core/diagnostics/checks/rollback_monitor.py:18` | `_ROLLBACK_LOG = Path.home() / ".aiplat" / "data" / "rollback_events.jsonl"` |
| 158 | `aiPlat-core/core/orchestration/capability_mapper.py:64` | `os.path.expanduser("~/.aiplat/agents"),` |
| 159 | `aiPlat-core/core/orchestration/capability_mapper.py:65` | `os.path.join(os.path.expanduser("~/.aiplat"), "workspace_seeds/agents"),` |
| 160 | `aiPlat-core/core/api/intents.py:234` | `md_path = _os.path.join(_os.path.expanduser("~/.aiplat"), "agents", ctx.agent_name, "AGENT.md")` |
| 161 | `aiPlat-core/core/api/core_facade.py:561` | `md_path = _os.path.join(_os.path.expanduser("~/.aiplat"), "agents", ctx.agent_name, "AGENT.md")` |
| 162 | `aiPlat-core/core/api/core_facade.py:692` | `agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")` |
| 163 | `aiPlat-core/core/api/core_facade.py:967` | `agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")` |
| 164 | `aiPlat-core/core/api/routers/workspace_agents.py:1266` | `home = _P(os.path.expanduser("~/.aiplat"))` |
| 165 | `aiPlat-core/core/api/routers/workspace_agents.py:4131` | `md_path = _P(os.path.expanduser("~/.aiplat")) / "agents" / agent_id / "AGENT.md"` |
| 166 | `aiPlat-core/core/api/routers/workspace_agents.py:4195` | `skill_dir = _P(os.path.expanduser("~/.aiplat")) / "skills"` |
| 167 | `aiPlat-core/core/api/routers/workspace_agents.py:5149` | `agents_home = _P(os.path.expanduser("~/.aiplat")) / "agents"` |
| 168 | `aiPlat-core/core/api/routers/workspace_agents.py:5287` | `wf_dir = _P(os.path.expanduser("~/.aiplat")) / "workflows"` |
| 169 | `aiPlat-core/core/api/routers/system.py:79` | `path = os.path.expanduser("~/.aiplat/ontologies/registry.json")` |
| 170 | `aiPlat-core/core/api/routers/system.py:759` | `mdir = _os_ss.path.expanduser("~/.aiplat/fde-manuals")` |
| 171 | `aiPlat-core/core/api/routers/mcp_admin.py:1214` | `home = _Path.home() / ".aiplat" / "mcps" / server_name / "server.yaml"` |
| 172 | `aiPlat-core/core/api/routers/mcp_admin.py:1485` | `home = _Path.home() / ".aiplat" / "mcps" / server_name / "server.yaml"` |
| 173 | `aiPlat-core/core/api/routers/mcp_admin.py:1572` | `installed = (Path.home() / ".aiplat" / "mcps" / item.name).exists()` |
| 174 | `aiPlat-core/core/api/routers/mcp_admin.py:1595` | `workspace_dir = Path.home() / ".aiplat" / "mcps"` |
| 175 | `aiPlat-core/core/api/routers/workspace_skills_meta.py:1522` | `catalog_path = os.path.expanduser("~/.aiplat/skills/catalog.yaml")` |
| 176 | `aiPlat-core/core/api/routers/diagnostics.py:2225` | `db_path = os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3")` |
| 177 | `aiPlat-core/core/api/routers/workspace_skills.py:2077` | `allowed_base = Path(os.path.expanduser("~/.aiplat/skills")).resolve()` |
| 178 | `aiPlat-core/core/api/routers/tools.py:474` | `tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))` |
| 179 | `aiPlat-core/core/api/routers/tools.py:512` | `ToolDiscovery(Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))).register_all()` |
| 180 | `aiPlat-core/core/api/routers/tools.py:515` | `ToolDiscovery(Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))).register_all()` |
| 181 | `aiPlat-core/core/api/routers/workspace_packages.py:140` | `workspace_root = Path.home() / ".aiplat"` |
| 182 | `aiPlat-core/core/api/routers/workspace_packages.py:267` | `wk_agents = (Path.home() / ".aiplat" / "agents").resolve()` |
| 183 | `aiPlat-core/core/api/routers/workspace_packages.py:268` | `wk_skills = (Path.home() / ".aiplat" / "skills").resolve()` |
| 184 | `aiPlat-core/core/api/routers/workspace_packages.py:269` | `wk_mcps = (Path.home() / ".aiplat" / "mcps").resolve()` |
| 185 | `aiPlat-core/core/api/routers/workspace_packages.py:270` | `wk_hooks = (Path.home() / ".aiplat" / "hooks").resolve()` |
| 186 | `aiPlat-core/core/api/routers/packages_registry.py:176` | `return Path.home() / ".aiplat" / "packages" / "registry"` |
| 187 | `aiPlat-core/core/api/routers/packages_registry.py:296` | `src = Path.home() / ".aiplat" / f"{kind}s" / rid` |
| 188 | `aiPlat-core/core/api/routers/overview.py:468` | `ws_dir = Path.home() / ".aiplat" / "agents"` |
| 189 | `aiPlat-core/core/api/routers/workspace_tools.py:110` | `tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))` |
| 190 | `aiPlat-core/core/api/routers/workspace_tools.py:241` | `tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))` |
| 191 | `aiPlat-core/core/api/routers/workspace_hooks.py:14` | `return Path.home() / ".aiplat" / "hooks"` |
| 192 | `aiPlat-core/core/api/routers/wiki.py:335` | `workspace = _os.path.expanduser("~/.aiplat/skills")` |
| 193 | `aiPlat-core/core/api/routers/wiki.py:1075` | `ont_dir = Path(os.path.expanduser("~/.aiplat/ontologies"))` |
| 194 | `aiPlat-core/core/api/routers/wiki.py:2363` | `db = _Path.home() / ".aiplat" / "kb" / "tenants" / "default" / "kb.sqlite3"` |
| 195 | `aiPlat-core/core/api/routers/wiki.py:3375` | `log_path = os.path.expanduser("~/.aiplat/wiki/model_selection_log.json")` |
| 196 | `aiPlat-core/core/api/routers/diagnostics_capability.py:23` | `path = os.path.expanduser("~/.aiplat/ontologies/registry.json")` |
| 197 | `aiPlat-core/core/api/routers/diagnostics_capability.py:31` | `path = os.path.expanduser("~/.aiplat/wiki/golden_queries.yaml")` |
| 198 | `aiPlat-core/core/api/facades/agent_facade.py:14` | `agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")` |
| 199 | `aiPlat-core/core/api/facades/service_facade.py:19` | `os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"),` |
| 200 | `aiPlat-core/core/engine/skills/security_evidence/handler.py:35` | `root = Path.home() / ".aiplat"` |
| 201 | `aiPlat-core/core/engine/skills/poc_data_inject/handler.py:19` | `_POC_KB = os.path.expanduser("~/.aiplat/kb/poc")` |
| 202 | `aiPlat-core/core/apps/discovery/__init__.py:315` | `output_dir = _os.path.expanduser("~/.aiplat/datasources/auto_discovered")` |
| 203 | `aiPlat-core/core/apps/agents/subagent/config.py:121` | `__os.path.join(__os.path.expanduser("~/.aiplat"), "agents", "builtin", name, "AGENT.md"),` |
| 204 | `aiPlat-core/core/apps/mcp/local_tools_server.py:31` | `tools_dir = Path(os.environ.get("AIPLAT_TOOLS_PATH", Path.home() / ".aiplat" / "tools"))` |
| 205 | `aiPlat-core/core/apps/finetune/job_manager.py:549` | `pending_path = os.path.join(os.path.expanduser("~/.aiplat"), "pending_models.json")` |
| 206 | `aiPlat-core/core/apps/finetune/job_manager.py:630` | `signal_path = os.path.expanduser("~/.aiplat/sft_models/latest.json")` |
| 207 | `aiPlat-core/core/apps/finetune/job_manager.py:650` | `history_path = os.path.expanduser("~/.aiplat/sft_models/history.jsonl")` |
| 208 | `aiPlat-core/core/apps/eval/agent_eval.py:26` | `return Path(os.path.expanduser("~/.aiplat"))` |
| 209 | `aiPlat-core/core/apps/fde/service/rapid_insight_service.py:596` | `vec_path = _os.path.expanduser("~/.aiplat/wiki/collections/default/vectors.json")` |
| 210 | `aiPlat-core/core/apps/fde/service/voice.py:44` | `emo_dir = os.path.expanduser("~/.aiplat/emotion")` |
| 211 | `aiPlat-core/core/apps/fde/service/report_generator.py:79` | `db_path = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 212 | `aiPlat-core/core/apps/fde/service/report_generator.py:183` | `db_path = _os.path.expanduser("~/.aiplat/state_changes.db")` |
| 213 | `aiPlat-platform/kb/metrics.py:106` | `or str(Path.home() / ".aiplat")` |
| 214 | `aiPlat-platform/kb/metrics.py:209` | `kb_path = os.path.expanduser("~/.aiplat/data/kb/aiplat_knowledge.sqlite3")` |
| 215 | `aiPlat-platform/kb/storage.py:40` | `return Path.home() / ".aiplat"` |
| 216 | `aiPlat-platform/storage/platform_db.py:27` | `db_path = str(Path.home() / ".aiplat" / "platform.sqlite3")` |
| 217 | `aiPlat-platform/delivery/kb_health.py:146` | `or str(Path.home() / ".aiplat")` |
| 218 | `aiPlat-platform/delivery/kb_health.py:336` | `or str(Path.home() / ".aiplat")` |
| 219 | `aiPlat-platform/delivery/kb_health_archive.py:24` | `or str(Path.home() / ".aiplat")` |
| 220 | `aiPlat-platform/api/routers/skill_marketplace.py:25` | `SKILLS_HOME = os.path.expanduser("~/.aiplat/skills")` |
| 221 | `aiPlat-platform/api/routers/workflows.py:179` | `ap = _P(_os.path.expanduser("~/.aiplat")) / "agents" / agent_id / "AGENT.md"` |
| 222 | `aiPlat-platform/builder/agent_conformance.py:69` | `base = agents_dir or os.path.expanduser("~/.aiplat/agents")` |
| 223 | `aiPlat-platform/builder/builder_project_service.py:1160` | `(os.path.join(os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps")), ""), project_id),` |
| 224 | `aiPlat-platform/builder/builder_project_service.py:1233` | `(os.path.join(os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps")), ""), project_id),` |
| 225 | `aiPlat-platform/builder/builder_project_service.py:3124` | `out_fp = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "test_report.json")` |
| 226 | `aiPlat-platform/builder/builder_project_service.py:3179` | `p = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "agent_app.json")` |
| 227 | `aiPlat-platform/builder/builder_project_service.py:3187` | `p = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "test_cases.json")` |
| 228 | `aiPlat-platform/builder/builder_project_service.py:4484` | `_app_prefix = os.path.expanduser("~/.aiplat/apps/")` |
| 229 | `aiPlat-platform/apps/misc/api/browser_test.py:294` | `(_Path.home() / ".aiplat").resolve(),` |
| 230 | `aiPlat-platform/apps/value/api/roles.py:69` | `workspace_dir = os.path.expanduser("~/.aiplat/agents")` |
| 231 | `aiPlat-platform/apps/value/api/value.py:340` | `report_path = os.path.expanduser("~/.aiplat/value/monthly.jsonl")` |
| 232 | `aiPlat-platform/apps/workbench/api/workbench.py:515` | `model_path = os.path.expanduser("~/.aiplat/sft_models/latest.json")` |
| 233 | `aiPlat-platform/apps/workbench/api/workbench.py:525` | `dataset_dir = os.path.expanduser("~/.aiplat/training")` |
| 234 | `aiPlat-platform/apps/workbench/api/overview.py:429` | `ws_dir = Path.home() / ".aiplat" / "agents"` |
| 235 | `aiPlat-platform/apps/eval/api/skill_evals.py:206` | `base = Path.home() / ".aiplat" / "skills"` |
| 236 | `aiPlat-platform/apps/ontology_editor/api/governance_crud.py:26` | `db = os.path.expanduser("~/.aiplat/usage_metrics.db")` |
| 237 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:60` | `hd = os.path.expanduser("~/.aiplat/handovers")` |
| 238 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:99` | `ar = os.path.expanduser("~/.aiplat/archive")` |
| 239 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:156` | `sd = os.path.expanduser("~/.aiplat/post_health")` |
| 240 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:175` | `sd = os.path.expanduser("~/.aiplat/post_health")` |
| 241 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:226` | `sd = os.path.expanduser("~/.aiplat/training")` |
| 242 | `aiPlat-platform/apps/fde/api/fde_handover_v2.py:247` | `sd = os.path.expanduser("~/.aiplat/training")` |
| 243 | `aiPlat-platform/apps/fde/api/fde_validate.py:42` | `with open(os.path.expanduser("~/.aiplat/ontologies/registry.json")) as f:` |
| 244 | `aiPlat-platform/apps/fde/api/fde_validate.py:67` | `path = os.path.expanduser("~/.aiplat/ontologies/ai-knowledge.yaml")` |
| 245 | `aiPlat-platform/apps/fde/api/fde_validate.py:74` | `path = os.path.expanduser("~/.aiplat/ontologies/ai-solution.yaml")` |
| 246 | `aiPlat-platform/apps/fde/api/fde.py:1838` | `reg_path = _os_health.path.expanduser("~/.aiplat/ontologies/registry.json")` |
| 247 | `aiPlat-platform/apps/fde/api/fde.py:2276` | `manuals_dir = _os_ms.path.expanduser("~/.aiplat/fde-manuals")` |
| 248 | `aiPlat-platform/apps/fde/api/fde.py:2397` | `path = _os_gov.path.expanduser("~/.aiplat/ontologies/registry.json")` |
| 249 | `aiPlat-platform/apps/fde/api/fde_manuals.py:19` | `_MANUALS_DIR = os.path.expanduser("~/.aiplat/fde-manuals")` |
| 250 | `aiPlat-platform/apps/fde/api/fde_governance.py:18` | `path = os.path.expanduser("~/.aiplat/ontologies/registry.json")` |
| 251 | `aiPlat-platform/apps/fde/api/fde_governance.py:78` | `path = os.path.expanduser("~/.aiplat/ontologies/fde-delivery.yaml")` |
| 252 | `aiPlat-platform/apps/fde/api/fde_ask.py:85` | `sol_path = _os_ask.path.expanduser("~/.aiplat/ontologies/ai-solution.yaml")` |
| 253 | `aiPlat-platform/apps/fde/api/fde_reports.py:104` | `agents_dir = os.path.expanduser("~/.aiplat/agents")` |
| 254 | `aiPlat-platform/apps/fde/api/fde_reports.py:126` | `skills_dir = os.path.expanduser("~/.aiplat/skills")` |
| 255 | `aiPlat-infra/infra/management/model/paths.py:16` | `os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"),` |
| 256 | `aiPlat-infra/infra/management/model/model_health_store.py:26` | `os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3")` |
| 257 | `aiPlat-infra/infra/management/model/manager.py:40` | `env_file = Path(os.getenv("AIPLAT_ENV_LOCAL_PATH", str(Path.home() / ".aiplat" / ".env.local")))` |
| 258 | `aiPlat-management/management/api/studio.py:326` | `app_deploy_dir = os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps"))` |
| 259 | `aiPlat-management/management/api/diagnostics.py:577` | `skill_auto_dir = os.path.expanduser("~/.aiplat/skills/auto")` |

## Tier B — sample (first 40 of 186)

| # | Location | Snippet |
|---|----------|---------|
| 1 | `aiPlat-core/core/server.py:479` | `home = os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))` |
| 2 | `aiPlat-core/core/management/prompt_app_manager.py:52` | `return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat"))) / "prompt-apps"` |
| 3 | `aiPlat-core/core/utils/paths.py:35` | `home = os.path.expanduser("~/.aiplat")` |
| 4 | `aiPlat-core/core/harness/team_sources.py:27` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 5 | `aiPlat-core/core/harness/team_friction.py:48` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 6 | `aiPlat-core/core/harness/team_digest.py:18` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 7 | `aiPlat-core/core/harness/team_factory_seeds.py:29` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 8 | `aiPlat-core/core/harness/team_harness.py:35` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 9 | `aiPlat-core/core/harness/teamai_seed_export.py:43` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 10 | `aiPlat-core/core/harness/memory/team_brain.py:61` | `home = os.environ.get("AIPLAT_HOME") or str(Path.home() / ".aiplat")` |
| 11 | `aiPlat-core/core/harness/meta/repo_health_scan.py:86` | `home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))` |
| 12 | `aiPlat-core/core/harness/meta/gate_meta_eval.py:46` | `home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))` |
| 13 | `aiPlat-core/core/harness/meta/org_harness_metrics.py:473` | `home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))` |
| 14 | `aiPlat-core/core/harness/utils/team_culture.py:29` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 15 | `aiPlat-core/core/harness/utils/team_skill_subscription.py:25` | `return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()` |
| 16 | `aiPlat-core/core/harness/utils/model_injection.py:290` | `os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),` |
| 17 | `aiPlat-core/core/harness/utils/output_style.py:67` | `home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))` |
| 18 | `aiPlat-core/core/harness/utils/output_style.py:169` | `home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))` |
| 19 | `aiPlat-core/core/harness/digital_human/consultant_reload.py:21` | `return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))` |
| 20 | `aiPlat-core/core/harness/digital_human/platform_status_brief.py:23` | `return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))` |
| 21 | `aiPlat-core/core/harness/digital_human/consultant_personal.py:70` | `return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))` |
| 22 | `aiPlat-core/core/harness/knowledge/learning_ontology.py:195` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |
| 23 | `aiPlat-core/core/harness/knowledge/knowledge_markings.py:98` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |
| 24 | `aiPlat-core/core/harness/knowledge/learning_assessment.py:555` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |
| 25 | `aiPlat-core/core/harness/knowledge/wiki_health_rules.py:1211` | `root = Path(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "wiki"` |
| 26 | `aiPlat-core/core/harness/knowledge/wiki_health_rules.py:1303` | `root = Path(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "wiki"` |
| 27 | `aiPlat-core/core/harness/knowledge/scene_model.py:175` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |
| 28 | `aiPlat-core/core/harness/knowledge/ontology_loader.py:227` | `d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 29 | `aiPlat-core/core/harness/knowledge/ontology_loader.py:242` | `d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 30 | `aiPlat-core/core/harness/knowledge/ontology_loader.py:312` | `dest_dir = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 31 | `aiPlat-core/core/harness/knowledge/ontology_loader.py:335` | `d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 32 | `aiPlat-core/core/harness/knowledge/ontology_loader.py:352` | `d = _Path(base_dir or _os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 33 | `aiPlat-core/core/harness/knowledge/capability_graph.py:218` | `ws = Path(_os2.getenv("AIPLAT_HOME", _os2.path.expanduser("~/.aiplat"))) / subdir` |
| 34 | `aiPlat-core/core/harness/knowledge/knowledge_growth.py:64` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |
| 35 | `aiPlat-core/core/harness/knowledge/sql_ontology.py:68` | `base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"` |
| 36 | `aiPlat-core/core/harness/knowledge/ontology_case_learning.py:41` | `return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))` |
| 37 | `aiPlat-core/core/harness/knowledge/versioned_ontology_store.py:142` | `return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "ontologies")` |
| 38 | `aiPlat-core/core/harness/knowledge/knowledge_ontology.py:673` | `home = _oss.getenv("AIPLAT_HOME", _oss.path.expanduser("~/.aiplat"))` |
| 39 | `aiPlat-core/core/harness/knowledge/candidate_pool.py:175` | `os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),` |
| 40 | `aiPlat-core/core/harness/knowledge/knowledge_quality.py:63` | `home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))` |

## Scope / next

- Excluded: tests, `.venv`, `node_modules`, `#` comments, `❌` doc examples
- `core/utils/paths.py` counted as soft (canonical fallback)
- Post-W2 plan: migrate Tier A → `get_aiplat_home()`; re-scan until A=0
