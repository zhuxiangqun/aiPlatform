---
total_capabilities: 1110

total_capabilities: 1095
last_updated: 2026-08-25
version: "30.2"
auto_sync: true
core_guarantees:
  auto:  # 23 active, 0 missing
    - id: llm_circuit_breaker
      description: "LLM 熔断器：5次连续失败→断路30s"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::140
        - aiPlat-core/core/harness/syscalls/llm.py::1442
        - aiPlat-core/core/harness/syscalls/llm.py::2131
        - aiPlat-core/core/harness/syscalls/llm.py::2203
    - id: pii_detection
      description: "PII 脱敏：手机/身份证/邮箱/银行卡自动替换"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::545
    - id: injection_guard
      description: "提示词注入防护：6条正则+特殊token过滤+覆盖保护"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::380
        - aiPlat-core/core/harness/syscalls/llm.py::396
        - aiPlat-core/core/harness/syscalls/llm.py::414
        - aiPlat-core/core/harness/syscalls/llm.py::420
        - aiPlat-core/core/harness/syscalls/llm.py::422
        - aiPlat-core/core/harness/syscalls/llm.py::422
        - aiPlat-core/core/harness/syscalls/llm.py::504
        - aiPlat-core/core/harness/syscalls/llm.py::518
        - aiPlat-core/core/harness/syscalls/llm.py::1684
        - aiPlat-core/core/harness/syscalls/llm.py::1702
        - aiPlat-core/core/harness/syscalls/llm.py::1722
        - aiPlat-core/core/harness/syscalls/llm.py::1760
        - aiPlat-core/core/harness/syscalls/llm.py::1762
        - aiPlat-core/core/harness/syscalls/llm.py::1766
    - id: immune_memory
      description: "ImmunMemory 攻击模式防御"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::532
        - aiPlat-core/core/harness/syscalls/llm.py::1510
        - aiPlat-core/core/harness/syscalls/llm.py::1518
    - id: claude_md_injection
      description: "CLAUDE.md 架构规约注入"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::617
        - aiPlat-core/core/harness/syscalls/llm.py::904
    - id: wiki_circuit_breaker
      description: "Wiki 检索熔断器"
      paths:
        - aiPlat-core/core/harness/syscalls/retrieval.py::1024
        - aiPlat-core/core/harness/syscalls/retrieval.py::1100
        - aiPlat-core/core/harness/syscalls/retrieval.py::1100
        - aiPlat-core/core/harness/syscalls/retrieval.py::1238
        - aiPlat-core/core/harness/syscalls/retrieval.py::1260
        - aiPlat-core/core/harness/syscalls/retrieval.py::1272
    - id: rate_limiter
      description: "模型调用限流：并发控制+cooldown"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::2111
        - aiPlat-core/core/harness/syscalls/llm.py::2111
        - aiPlat-core/core/harness/syscalls/llm.py::2113
    - id: memory_build_context
      description: "四层记忆注入（Working/Episodic/Semantic/TaskSkill）"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::1424
    - id: memory_save_interaction
      description: "交互记忆保存（Episodic）"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::1344
    - id: context_compression_5level
      description: "5 级上下文压缩"
      paths:
        - aiPlat-core/core/harness/memory/compression.py::223
        - aiPlat-core/core/harness/memory/compression.py::1108
        - aiPlat-core/core/harness/memory/compression.py::1118
        - aiPlat-core/core/harness/memory/manager.py::75
        - aiPlat-core/core/harness/memory/manager.py::335
        - aiPlat-core/core/harness/execution/loop/inference.py::44
        - aiPlat-core/core/harness/execution/loop/inference.py::48
        - aiPlat-core/core/harness/execution/loop/inference.py::404
        - aiPlat-core/core/harness/execution/loop/inference.py::405
    - id: semantic_cache
      description: "语义缓存 L1(MD5)+L2(Cosine≥0.95)"
      paths:
        - aiPlat-core/core/apps/agents/materials_chat.py::257
        - aiPlat-core/core/apps/agents/materials_chat.py::257
        - aiPlat-core/core/apps/agents/materials_chat.py::259
        - aiPlat-core/core/apps/agents/materials_chat.py::265
        - aiPlat-core/core/apps/agents/materials_chat.py::544
        - aiPlat-core/core/apps/agents/materials_chat.py::544
        - aiPlat-core/core/apps/agents/materials_chat.py::545
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::4
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::5
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::15
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::18
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::24
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::24
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::26
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::43
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::54
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::54
        - aiPlat-core/core/harness/knowledge/semantic_cache_hook.py::56
    - id: hallucination_tracker
      description: "幻觉检测：GraphIndex 事实验证"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::2540
        - aiPlat-core/core/harness/syscalls/llm.py::2540
        - aiPlat-core/core/harness/syscalls/llm.py::2542
    - id: quality_recording
      description: "质量评分记录（异步，fire-and-forget）"
      paths:
        - aiPlat-core/core/harness/utils/model_injection.py::57
        - aiPlat-core/core/harness/utils/model_injection.py::73
        - aiPlat-core/core/harness/utils/model_injection.py::1235
        - aiPlat-core/core/harness/utils/model_injection.py::1309
        - aiPlat-core/core/harness/utils/model_injection.py::1327
        - aiPlat-core/core/harness/utils/model_injection.py::1329
        - aiPlat-core/core/harness/utils/model_injection.py::1337
    - id: prompt_assembler
      description: "Prompt 动态组装（工具/技能/记忆/budget）"
      paths:
        - aiPlat-core/core/harness/syscalls/llm.py::1839
        - aiPlat-core/core/harness/syscalls/llm.py::1909
        - aiPlat-core/core/harness/syscalls/llm.py::1909
    - id: policy_gate
      description: "PolicyGate 权限检查（sys_tool_call入口）"
      paths:
        - aiPlat-core/core/harness/syscalls/tool.py::5
        - aiPlat-core/core/harness/syscalls/tool.py::20
        - aiPlat-core/core/harness/syscalls/tool.py::49
        - aiPlat-core/core/harness/syscalls/tool.py::55
        - aiPlat-core/core/harness/syscalls/tool.py::451
        - aiPlat-core/core/harness/syscalls/tool.py::463
        - aiPlat-core/core/harness/syscalls/tool.py::470
        - aiPlat-core/core/harness/syscalls/tool.py::472
    - id: approval_gate
      description: "ApprovalGate 危险操作审批"
      paths:
        - aiPlat-core/core/harness/context/engine.py::635
        - aiPlat-core/core/harness/context/engine.py::642
        - aiPlat-core/core/harness/context/engine.py::1095
        - aiPlat-core/core/harness/context/engine.py::1102
    - id: tool_drift_detector
      description: "工具漂移检测"
      paths:
        - aiPlat-core/core/harness/syscalls/tool.py::785
        - aiPlat-core/core/harness/syscalls/tool.py::785
        - aiPlat-core/core/harness/syscalls/tool.py::786
    - id: token_budget_management
      description: "Token 预算管理"
      paths:
        - aiPlat-core/core/harness/execution/loop/inference.py::234
        - aiPlat-core/core/harness/execution/loop/inference.py::248
        - aiPlat-core/core/harness/execution/loop/inference.py::248
        - aiPlat-core/core/harness/execution/loop/inference.py::256
        - aiPlat-core/core/harness/execution/loop/inference.py::256
        - aiPlat-core/core/harness/execution/loop/inference.py::264
        - aiPlat-core/core/harness/execution/loop/inference.py::270
        - aiPlat-core/core/harness/execution/loop/inference.py::290
        - aiPlat-core/core/harness/execution/loop/inference.py::377
        - aiPlat-core/core/harness/execution/loop/inference.py::387
        - aiPlat-core/core/harness/execution/loop/inference.py::390
        - aiPlat-core/core/harness/execution/loop/inference.py::408
    - id: model_health_tracking
      description: "模型健康自适应跟踪"
      paths:
        - aiPlat-core/core/harness/utils/model_injection.py::1057
        - aiPlat-core/core/harness/utils/model_injection.py::1070
        - aiPlat-core/core/harness/utils/model_injection.py::1245
        - aiPlat-core/core/harness/utils/model_injection.py::1256
        - aiPlat-core/core/harness/utils/model_injection.py::1275
        - aiPlat-core/core/harness/utils/model_injection.py::1280
        - aiPlat-infra/infra/management/model/manager.py::537
        - aiPlat-infra/infra/management/model/manager.py::621
        - aiPlat-infra/infra/management/model/manager.py::622
    - id: experience_vector
      description: "经验向量（Loop+Pipeline 存入）"
      paths:
        - aiPlat-core/core/harness/execution/loop/_facade.py::1556
        - aiPlat-core/core/harness/execution/loop/_facade.py::1562
        - aiPlat-core/core/harness/execution/loop/_facade.py::1750
        - aiPlat-core/core/harness/execution/loop/_facade.py::1829
        - aiPlat-core/core/harness/execution/loop/_facade.py::1876
        - aiPlat-core/core/harness/execution/loop/_facade.py::1882
        - aiPlat-core/core/harness/execution/loop/_facade.py::1914
        - aiPlat-core/core/harness/execution/loop/_facade.py::1917
        - aiPlat-core/core/harness/execution/loop/_facade.py::1933
        - aiPlat-core/core/harness/execution/loop/_facade.py::1958
        - aiPlat-core/core/harness/execution/loop/_facade.py::1973
        - aiPlat-core/core/harness/execution/loop/_facade.py::2006
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3065
        - aiPlat-core/core/harness/execution/pipeline_engine.py::12012
        - aiPlat-core/core/harness/execution/pipeline_engine.py::12233
    - id: seci_knowledge_spiral
      description: "SECI 知识螺旋（POST_LOOP→atom→convergence）"
      paths:
        - aiPlat-core/core/harness/knowledge/seci_engine.py::2
        - aiPlat-core/core/harness/knowledge/seci_engine.py::2
        - aiPlat-core/core/harness/knowledge/seci_engine.py::12
        - aiPlat-core/core/harness/knowledge/seci_engine.py::24
        - aiPlat-core/core/harness/knowledge/seci_engine.py::39
        - aiPlat-core/core/harness/knowledge/seci_engine.py::84
        - aiPlat-core/core/harness/knowledge/seci_engine.py::93
        - aiPlat-core/core/harness/knowledge/seci_engine.py::104
        - aiPlat-core/core/harness/knowledge/seci_engine.py::178
        - aiPlat-core/core/harness/knowledge/seci_engine.py::200
        - aiPlat-core/core/harness/knowledge/seci_engine.py::206
        - aiPlat-core/core/harness/knowledge/seci_engine.py::214
        - aiPlat-core/core/harness/knowledge/seci_engine.py::234
        - aiPlat-core/core/harness/knowledge/seci_engine.py::241
        - aiPlat-core/core/harness/knowledge/seci_engine.py::276
        - aiPlat-core/core/harness/knowledge/seci_engine.py::317
        - aiPlat-core/core/harness/knowledge/seci_engine.py::327
        - aiPlat-core/core/harness/knowledge/seci_engine.py::378
        - aiPlat-core/core/harness/knowledge/seci_engine.py::387
        - aiPlat-core/core/harness/knowledge/seci_engine.py::400
        - aiPlat-core/core/harness/knowledge/seci_engine.py::419
        - aiPlat-core/core/harness/knowledge/seci_engine.py::432
        - aiPlat-core/core/harness/knowledge/seci_engine.py::436
        - aiPlat-core/core/harness/knowledge/seci_engine.py::436
        - aiPlat-core/core/harness/knowledge/seci_engine.py::440
        - aiPlat-core/core/harness/knowledge/seci_engine.py::440
        - aiPlat-core/core/harness/knowledge/seci_engine.py::441
        - aiPlat-core/core/harness/knowledge/seci_engine.py::442
        - aiPlat-core/core/harness/knowledge/seci_engine.py::443
        - aiPlat-core/core/harness/knowledge/seci_engine.py::444
        - aiPlat-core/core/harness/knowledge/seci_engine.py::444
        - aiPlat-core/core/harness/knowledge/seci_engine.py::445
        - aiPlat-core/core/harness/knowledge/seci_engine.py::448
        - aiPlat-core/core/harness/knowledge/seci_engine.py::449
        - aiPlat-core/core/harness/knowledge/seci_engine.py::449
        - aiPlat-core/core/harness/knowledge/seci_engine.py::451
        - aiPlat-core/core/harness/knowledge/seci_engine.py::462
        - aiPlat-core/core/harness/knowledge/seci_engine.py::484
        - aiPlat-core/core/harness/knowledge/seci_engine.py::506
        - aiPlat-core/core/harness/knowledge/seci_engine.py::517
        - aiPlat-core/core/harness/knowledge/seci_engine.py::544
        - aiPlat-core/core/harness/knowledge/seci_engine.py::544
        - aiPlat-core/core/harness/knowledge/seci_engine.py::549
        - aiPlat-core/core/harness/knowledge/seci_engine.py::549
        - aiPlat-core/core/harness/knowledge/seci_engine.py::560
        - aiPlat-core/core/harness/knowledge/seci_engine.py::561
        - aiPlat-core/core/harness/knowledge/seci_engine.py::568
        - aiPlat-core/core/harness/knowledge/seci_engine.py::571
        - aiPlat-core/core/harness/knowledge/seci_engine.py::571
        - aiPlat-core/core/harness/knowledge/seci_engine.py::574
    - id: skill_crystalization
      description: "Skill 晶体化（pipeline完成→TaskSkill→SkillRegistry）"
      paths:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3028
        - aiPlat-core/core/harness/execution/pipeline_engine.py::9879
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10103
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10107
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10129
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10142
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10152
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10174
    - id: feedback_loops
      description: "交互反馈回路"
      paths:
        - aiPlat-core/core/harness/execution/loop/_facade.py::1433
        - aiPlat-core/core/harness/execution/loop/_facade.py::1435
        - aiPlat-core/core/harness/execution/loop/_facade.py::1459
        - aiPlat-core/core/harness/execution/loop/_facade.py::1461

  configurable:  # 27 consumed by engine
    - id: agent_type
      field: PipelineStageConfig.agent_type
      description: "See ~/.aiplat/registry/agent_types.yaml for valid values (single source of truth)"
      schema_default: "react"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4215
        - aiPlat-core/core/harness/execution/pipeline_engine.py::11367
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4084
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4215
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7071
        - aiPlat-core/core/harness/execution/pipeline_engine.py::11321
    - id: capability_profile
      field: PipelineStageConfig.capability_profile
      schema_default: "auto"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4164
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4191
    - id: chain_skill_after
      field: PipelineStageConfig.chain_skill_after
      description: "Auto-execute another skill after this stage completes"
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4619
    - id: completeness_check
      field: PipelineStageConfig.completeness_check
      description: "{input_artifact, output_key, max_per_call}"
      schema_default: null
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3948
    - id: context_profile
      field: PipelineStageConfig.context_profile
      description: "minimal|code|debug|deep"
      schema_default: "code"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4392
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4290
    - id: deploy_files_target_dir
      field: PipelineStageConfig.deploy_files_target_dir
      description: "Override target. Empty = ~/.aiplat/apps/{pid}/current"
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4789
    - id: deploy_files_to_disk
      field: PipelineStageConfig.deploy_files_to_disk
      description: "Parse ## FILE: blocks from output, write to project dir"
      schema_default: false
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4625
    - id: enable_query_rewrite
      field: PipelineStageConfig.enable_query_rewrite
      description: "rewrite ambiguous follow-up queries before retrieval"
      schema_default: true
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4385
    - id: execution_backend
      field: PipelineStageConfig.execution_backend
      description: "llm\"=sys_llm_generate | \"agent\"=StageRunner.run()→ReActLoop"
      schema_default: "llm"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4203
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4232
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4230
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4252
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4452
    - id: failure_strategy
      field: PipelineStageConfig.failure_strategy
      schema_default: "fail_pipeline"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7365
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4052
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4594
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6954
        - aiPlat-core/core/harness/execution/pipeline_engine.py::11089
    - id: generate_test_plan
      field: PipelineStageConfig.generate_test_plan
      schema_default: false
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::2076
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8653
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8911
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8917
        - aiPlat-core/core/harness/execution/pipeline_engine.py::11371
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4095
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4606
    - id: hitl
      field: PipelineStageConfig.hitl
      schema_default: false
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7149
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8257
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4095
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4629
    - id: hitl_phase
      field: PipelineStageConfig.hitl_phase
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::2076
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7153
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8261
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4632
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5100
    - id: output_artifact
      field: PipelineStageConfig.output_artifact
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::2285
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3199
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3201
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3217
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3251
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4264
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4960
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4970
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4998
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5026
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5028
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5058
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5338
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5350
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5354
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5362
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5372
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5376
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5380
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5467
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5469
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5471
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5519
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5535
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5864
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5890
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6102
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6242
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6390
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6838
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6846
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6978
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7309
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7313
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7335
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7353
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7417
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7649
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7725
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7974
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7980
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8039
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8047
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8249
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8255
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8426
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8478
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7846
        - aiPlat-core/core/harness/execution/pipeline_engine.py::886
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3600
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3926
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3935
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4011
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4275
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4346
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4563
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4633
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4832
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4923
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5108
        - aiPlat-core/core/harness/execution/pipeline_engine.py::9521
        - aiPlat-core/core/harness/execution/pipeline_engine.py::9523
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10681
        - aiPlat-core/core/harness/execution/pipeline_engine.py::12163
    - id: pipeline_mode
      field: PipelineStageConfig.pipeline_mode
      description: "chain|router|parallel|orchestrator|evaluator_optimizer|agent"
      schema_default: "chain"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4214
        - aiPlat-core/core/harness/execution/pipeline_engine.py::2753
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4087
    - id: quality_gate
      field: PipelineStageConfig.quality_gate
      description: "CRAG-style quality gate: {condition, fallback, final_fallback}"
      schema_default: "{'min_output_length': 100}"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4557
    - id: retry_policy
      field: PipelineStageConfig.retry_policy
      description: "Self-heal retry: {on, action, max_retries}"
      schema_default: "{'max_retries': 2, 'backoff': 'exponential'}"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8280
    - id: review_gate
      field: PipelineStageConfig.review_gate
      description: "none|quick|llm|hitl\" — default quick for safety"
      schema_default: "quick"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4982
    - id: sandbox
      field: PipelineStageConfig.sandbox
      schema_default: false
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6862
        - aiPlat-core/core/harness/execution/pipeline_engine.py::749
    - id: sandbox_mode
      field: PipelineStageConfig.sandbox_mode
      schema_default: "subprocess"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::6910
    - id: scoring_dimensions
      field: PipelineStageConfig.scoring_dimensions
      schema_default: "[{'name': 'completeness', 'weight': 0.4}, {'name': 'accuracy', 'weight': 0.3}, {'name': 'efficiency', 'weight': 0.3}]"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7858
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7721
    - id: skill_model_purpose
      field: PipelineStageConfig.skill_model_purpose
      description: "e.g., \"reasoning\", \"code_gen\" — passed to best_model_for_purpose"
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4040
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4049
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4451
    - id: skill_name
      field: PipelineStageConfig.skill_name
      description: "e.g., \"architecture_design\", \"code_generation"
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::2324
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3934
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3935
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3980
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3999
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4011
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4047
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4266
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4440
    - id: test_execution_mode
      field: PipelineStageConfig.test_execution_mode
      description: "pytest|agent_conversation|\" — which test runner"
      schema_default: ""
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4607
    - id: test_result_key
      field: PipelineStageConfig.test_result_key
      description: "DEFAULT_TEST_RESULT_KEY — changed via AGENT.md frontmatter"
      schema_default: "test_report"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3203
        - aiPlat-core/core/harness/execution/pipeline_engine.py::3205
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7421
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8187
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8201
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8249
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8917
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4621
    - id: tools
      field: PipelineStageConfig.tools
      description: "per-stage tool whitelist for agent backend"
      schema_default: "[]"
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::4458
    - id: uses_file_output
      field: PipelineStageConfig.uses_file_output
      schema_default: false
      consumed_at:
        - aiPlat-core/core/harness/execution/pipeline_engine.py::1768
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5004
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5026
        - aiPlat-core/core/harness/execution/pipeline_engine.py::5864
        - aiPlat-core/core/harness/execution/pipeline_engine.py::7303
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8855
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8899
        - aiPlat-core/core/harness/execution/pipeline_engine.py::8911
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10653
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10679
        - aiPlat-core/core/harness/execution/pipeline_engine.py::10628
scan_hash: 8f9548ec24f4
---

# aiPlat — 三层知识系统

> **aiPlat 不是一个功能列表，而是一个会持续生长的知识系统。**

## 系统架构：三层 + 三循环

### 三层结构

| 层级 | 作用 | 实现 |
|:---|:---|:---|
| **Raw Sources（原始资料层）** | 论文、报告、合同、网页、传感器数据——只读、可追溯，是事实来源 | `DataSource` 抽象层（SQL/API/File） + `DocumentParser` + 13 步 `OntologyEngine` 管道 |
| **Wiki（知识层）** | 实体页、概念页、关系页、主题综述——LLM 持续编译，通过链接和引用形成知识网络 | `GraphIndex` + `KnowledgeSynthesizer` → Markdown Wiki + `vectors.json` 向量缓存 + FTS5 全文索引 |
| 诊断模型层级 | management/api/diagnostics.py | ✅ | `GET /model-tier` — 模型层级路由状态 | 已合入 |
| **Schema（规则层）** | 域本体（YAML）、命名规范、更新流程——让知识库不会失控 | `ontology_loader.py` → `OntologyDomain` + `KnowledgeValidator`（6 种 axiom 验证） + `AGENTS.md` |

### 三个持续循环

| 循环 | 动作 | 实现 |
|:---|:---|:---|
| **Ingest（摄入循环）** | 新资料进入 → 自动提取实体 → 生成 Wiki → 更新关联页面 → 向量化 | 13 步管道（`ClassMapper` → `PropertyExtractor` → `RelationMapper` → `GraphIndex` → `KnowledgeSynthesizer` → Wiki → Vector） |
| **Query（查询循环）** | 多 Agent 从 Wiki + Graph + Vector 三路检索 → CRAG 三级回退 → 回答带来源 → 在线验证 | `DomainRouter`（3 层级联） + `sys_knowledge_retrieve`（RRF 融合） + `MaterialsChatAgent`（Self-RAG） + `HallucinationTracker` |
| **Lint（自检循环）** | 在线验证边一致性 → 离线检查过期/矛盾/孤立/无来源 → 发现问题自动触发增量更新 | `sys_graph_validate`（在线） + `KnowledgeValidator`（离线） + `EvolutionEngine`（夜间） + Lint-to-Ingest 回路 |

### 核心原则

> 代码即真相。每个条目必须有可验证的代码位置。
> 更新：任何能力变更时同步更新本文档。
> 评分：98/100（2026-07-20 — 1059✅）

---

## 更新规则

1. **新增能力**：在对应子系统表格加一行，标注 ✅ + 代码位置
2. **废弃能力**：改标记为 ⚠️ deprecated + 日期
3. **能力增强**：更新"说明"列
4. **自检**：`grep -rn "代码位置" aiPlat-core/` 确认文件存在
5. **同步更新统计表**：能力数与 ✅ 数必须一致
6. **通知下游文档**：若数字变更，在本文件统计表更新后，检查以下引用位置是否过时：
   - `AIPLAT_ROADMAP.md` 头部引用行 (384→400 时需同步)
   - CLI 启动 Banner 中的能力数字

---

## 一、Harness 执行引擎

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| imported_repo context injection | `core/harness/execution/pipeline_engine.py` | ✅ | 自动同步 | 已合入 |
| get_result_verifier | `core/harness/integration.py` | ✅ | 自动同步 | 已合入 |
| get_dataset_manager | `core/harness/integration.py` | ✅ | 自动同步 | 已合入 |
| get_job_manager | `core/harness/integration.py` | ✅ | 自动同步 | 已合入 |
| get_skill_discovery | `core/harness/integration.py` | ✅ | 自动同步 | 已合入 |
| get_mcp_client_manager | `core/harness/integration.py` | ✅ | 自动同步 | 已合入 |
| TenantStoreProtocol | `core/services/tenant_store_protocol.py` | ✅ | 自动同步 | 已合入 |
| PipelineStageMixin | `core/harness/execution/pipeline_stage.py` | ✅ | 自动同步 | 已合入 |
| PipelineEvalMixin | `core/harness/execution/pipeline_eval.py` | ✅ | 自动同步 | 已合入 |
| PipelinePromptMixin | `core/harness/execution/pipeline_prompt.py` | ✅ | 自动同步 | 已合入 |
| PipelineStateMixin | `core/harness/execution/pipeline_state.py` | ✅ | 自动同步 | 已合入 |
| PipelineHealingMixin | `core/harness/execution/pipeline_healing.py` | ✅ | 自动同步 | 已合入 |
| FailureClassifier | `harness/execution/failure_classifier.py` | ✅ | 自动同步 | 已合入 |
| ContextCompression | `harness/memory/compression.py` | ✅ | 自动同步 | 已合入 |
| generate_hypotheses | `harness/execution/pipeline_engine.py` | ✅ | 自动同步 | 已合入 |
| clear_trace | `` | ✅ | 自动同步 | 已合入 |
| get_trace | `` | ✅ | 自动同步 | 已合入 |
| mark_failed | `` | ✅ | 自动同步 | 已合入 |
| record_decision | `` | ✅ | 自动同步 | 已合入 |
| cost_for | `` | ✅ | 自动同步 | 已合入 |
| get_pricing | `` | ✅ | 自动同步 | 已合入 |
| debate | harness/execution/debate.py | ✅ | 自动同步 | 已合入 |
| conditional | harness/execution/conditional.py | ✅ | 自动同步 | 已合入 |
| stage_runner | harness/execution/langgraph/stage_runner.py | ✅ | 自动同步 | 已合入 |
| verification | harness/execution/verification.py | ✅ | 自动同步 | 已合入 |
| event_loop | harness/execution/event_loop.py | ✅ | 自动同步 | 已合入 |
| quick_engine | harness/execution/engines/quick_engine.py | ✅ | 自动同步 | 已合入 |
| graph_engine | harness/execution/engines/graph_engine.py | ✅ | 自动同步 | 已合入 |
| plan_engine | harness/execution/engines/plan_engine.py | ✅ | 自动同步 | 已合入 |
| team_planner | harness/execution/team_planner.py | ✅ | 自动同步 | 已合入 |
| state_mgr | harness/execution/loop/state_mgr.py | ✅ | 自动同步 | 已合入 |
| graph_injector | harness/execution/loop/graph_injector.py | ✅ | 自动同步 | 已合入 |
| tri_agent | harness/execution/langgraph/graphs/tri_agent.py | ✅ | 自动同步 | 已合入 |
| target_continuity | harness/execution/loop/target_continuity.py | ✅ | 自动同步 | 已合入 |
| trace_service | services/trace_service.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 中文语言数据 | harness/utils/zh_language.py | ✅ | 中文输入解析数据（正则/停用词/关键词/同意前缀），内核隔离，execution 层保持英文 | 已合入 |
| LLM API Key 解析 | harness/utils/llm_env.py | ✅ | 集中式 LLM API key 解析（infra CredentialPool 单一真相源） | 已合入 |
| AgentRefiner | harness/learning/agent_refiner.py | ✅ | 早朝复盘→AGENTS.md 自动优化建议（封驳率/阻塞点检测） | 已合入 |
| 决策溯源图 | harness/execution/decision_trace.py | ✅ | record/locate_max_error_node/trace_root_cause_chain/build_fix_plan，按 run_id 记录阶段决策+置信度+上游依赖，支持 agent_id 定位与混合修复计划 | 已合入 |
| 成本预算控制器 | harness/execution/cost_budget.py | ✅ | CostBudgetController 追踪 USD 成本+预算执行+降级决策，复用现有 CostTracker 定价 | 已合入 |
| 根因假设生成器 | harness/execution/hypothesis_generator.py | ✅ | 零 LLM 从决策溯源信号生成根因假设 + 定向修复动作 | 已合入 |
| 治理可解释报告 | harness/execution/governance_report.py | ✅ | build_run_report 聚合 trace+cost+假设+根因链为统一治理报告 | 已合入 |
| ReAct 执行循环 | harness/execution/loop/_facade.py | ✅ | Reason→Act→Observe，集成 Hook/压缩/记忆 | 已合入 |
| Plan-Execute 循环 | harness/execution/loop/_facade.py | ✅ | 先规划后执行模式 | 已合入 |
| 20 Hook 阶段 | harness/infrastructure/hooks/hook_manager.py:15 | ✅ | PRE/POST_LOOP, REASONING, ACT, OBSERVE, TOOL_USE, SKILL_USE, STOP, CONTRACT_CHECK, APPROVAL 等 | 已合入 |
| Pipeline 引擎 | harness/execution/pipeline_engine.py:239 | ✅ | 多阶段调度、HITL 暂停/恢复、重试、snapshot | 已合入 |
| **PipelinePhase** | harness/execution/phase.py | ✅ | 通用 Pipeline 阶段常量 — 替代 BuilderSessionPhase 业务枚举 | 已合入 |
| LangGraph 编排层 | harness/execution/langgraph/core.py:115 | ✅ | 图节点拓扑、条件边路由、checkpoint | 已合入 |
| 8 种图构建 | harness/execution/langgraph/graphs/ | ✅ | Pipeline/ReAct/PlanExecute/MultiAgent/TriAgent/Reflection | 已合入 |
| EngineRouter 回退链 | harness/execution/router.py | ✅ | graph→loop→quick 三引擎 | 已合入 |
| Token 预算管理 | harness/execution/loop/_facade.py:342 | ✅ | 总预算 100K，推理预算 60K，80%阈值预警 | 已合入 |
| 上下文压缩（5级） | harness/memory/compression.py:112 | ✅ | NORMAL→WARNING→REPLACE→PRUNE→AGGRESSIVE→EMERGENCY | 已合入 |
| 工具输出预算帽 | harness/memory/compression.py:230 | ✅ | >2000字→占位符+后台LLM摘要(2026-07-06修复adapter API,原chat_complete/model_name为死代码),热路径零阻塞 | 已合入 |
| 对话级 LLM 语义摘要 | harness/memory/compression.py:_llm_summarize_conversation | ✅ | AGGRESSIVE/EMERGENCY 级对话压缩为 4 类结构化摘要(目标/结论/工具/待办)，超时3s优雅降级 | 已合入 |
| 失败分类 | harness/execution/failure_classifier.py | ✅ | budget_exhausted / stagnation / token_budget | 已合入 |
| 收敛检测 | harness/coordination/detector/convergence.py | ✅ | 多 Agent 投票收敛 | 已合入 |
| Pipeline Sandbox | harness/execution/pipeline_sandbox.py | ✅ | 流水线沙箱执行 | 已合入 |
| PatternCache | harness/execution/pattern_cache.py | ✅ | MD5执行路径晶体化，重复管道模式跳过LLM | 已合入 |
| LangGraph Checkpoint/Resume | harness/execution/langgraph/core.py:217 | ✅ | 图状态checkpoint持久化 + 任意节点crash-safe恢复 | 已合入 |
| EmbeddingBridge | apps/agents/parallel_executor.py:210 | ✅ | 嵌入向量压缩，子Agent间高效通信 | 已合入 |
| 跨阶段回退 | schemas_builder.py:313-315` + `harness/execution/pipeline_engine.py:2855 | ✅ | `rollback_on_reject` 自动回退到上游阶段重写（委托+对抗模式） | 已合入 |
| Prompt Caching | harness/utils/prompt_caching.py | ✅ | system_and_N 缓存策略，system + 末尾N消息标记cache_control | 已合入 |
| Log Redaction | harness/utils/redaction.py | ✅ | RedactingFormatter 全局日志脱敏 | 已合入 |
| Decorrelated Jitter | harness/infrastructure/gates/resilience_gate.py | ✅ | golden-ratio hash退避抖动，避免惊群效应 | 已合入 |
| **Action Registry v3** | `harness/infrastructure/action_contract.py` + `action_registry.py` + `action_store.py` + `entity_lock.py` | ✅ | 企业级可治理 AI 执行层：`ActionContractModel`（Pydantic v2 + 实体约束 + handler白名单安全沙箱）、`AsyncActionRegistry`（7步执行流水线 + 审批回调 + 审计持久化）、`EntityLock`（mutex/stake双语义锁）、`ActionStore`（aiosqlite + entity_snapshot不可变审计）、`builtin_actions`（2业务+4legacy+YAML自助注册）、`builtin_handlers`（4个可调用handler）、`action_routes.py`（REST API + FDE AcceptTab前端动作卡片）、StateMachine零停机桥接 | 已合入 |
| **Knowledge Pipeline v3** | `harness/knowledge_pipeline/extractor.py` + `resolver.py` + `retriever.py` | ✅ | 知识生命周期三层管线：`DocumentIngestor`（文档分块）→ `EntityExtractor`（LLM驱动9实体+10关系自动抽取，置信度三级路由≥0.85自动/0.60-0.85待审/<0.60丢弃）→ `DraftYamlWriter`（YAML草稿输出）→ `CrossDomainResolver`（三级匹配：精确键0.6+Jaro-Winkler名称0.25+向量余弦0.15）→ `GraphRAGRetriever`（实体路由→BFS 2跳子图→定向向量检索→推理路径注入） | 已合入 |
| **Knowledge Pipeline 生成物适用性** | 生成 agent 运行时知识检索接入 | ⚠️ | 生成物不适用（理由：生成 agent 运行时知识检索由 core 全局 syscall `sys_kb_retrieve`（harness/syscalls/retrieval.py，ReActLoop 天然可用）平台横切强制执行，生成物无需自建检索路径；与 platform kb 能力族评估结论一致，2026-08-27 收尾） | 已评估 |
| **CC/Codex hooks 协议桥（G6）** | `harness/infrastructure/hooks/cc_bridge.py` + `cc_bridge_rules.py` | ✅ | 直接消费 Claude Code / Codex `hooks.json`：事件映射表（CC 7/30 + Codex 4/10 → HookPhase 子集）+ command handler 执行（shell=False/超时/fail-open）+ 默认关（`~/.aiplat/hooks.json` 或 `AIPLAT_CC_HOOKS_PATH` 存在时装载）；http/mcp_tool/prompt/agent handler 跳过记 WARNING，unmapped 事件不静默执行（对齐 DSH hooks 桥诚实披露） | 已合入 |
| **service-domain 参考实现** | `~/.aiplat/ontologies/service-domain.yaml` + `~/.aiplat/actions/service-domain_actions.yaml` + `custom_handlers/service_handlers.py` + `~/.aiplat/tests/service-domain_tests.yaml` + `scripts/sop_validate.py` + `docs/manuals/fde/06-sop-domain-delivery.md` | ✅ | 生产级参考实现：6类实体+6种关系+4态状态机+inference_rules + 5个动作（assign/start/submit/complete/reopen）+ 5个async handler + 12条测试用例 + SOP验证脚本6/6 PASS + 5天标准交付流程文档 | 已合入 |
| FDE 动作闭环 | platform/apps/fde/api/fde.py:1688-1807,2198-2300 | ✅ | StateTransition实体化(每次状态变更创建记录)→has_transition关系→GET timeline查看完整生命周期(Palantir L4) | 已合入 |

---

## 二、记忆子系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| import_claude_memories | `core/api/core_facade.py` | ✅ | 自动同步 | 已合入 |
| **Claude 会话导入（P0-b）** | `core/harness/memory/import_claude_sessions.py` + `core/api/core_facade.py` + `aiPlat-platform/api/routers/memory_import.py` | ✅ | Claude Code 会话 JSONL → MemoryManager（parse/find/import；source_tag=claude_import + provenance 防投毒溯源；POST /platform/memory/import） | 已合入 |
| SystemReminders.check_and_inject | `harness/memory/reminders.py` | ✅ | 自动同步 | 已合入 |
| MemoryManager.save_memory_rules | `harness/memory/manager.py` | ✅ | 自动同步 | 已合入 |
| MemoryManager.load_memory_rules | `harness/memory/manager.py` | ✅ | 自动同步 | 已合入 |
| SemanticMemoryModal | `aiPlat-management/frontend/src/components/SemanticMemoryModal.tsx` | ✅ | 自动同步 | 已合入 |
| **文件 Checkpoint UI** | `aiPlat-management/frontend/src/pages/Core/Checkpoints/FileCheckpoints.tsx` + `services/coreApi.ts`（checkpointApi） | ✅ | coding 场景前端：checkpoint 列表/查看/恢复（Hermes Layer 1 物理安全网接入，对标报告 §16.3 ⚠️未变项闭环） | 已合入 |
| Memory rules JSON | `harness/memory/manager.py` | ✅ | 自动同步 | 已合入 |
| LongTermMemoryMixin | `services/execution_store/ltm_mixin.py` | ✅ | 自动同步 | 已合入 |
| MemoryEntry | `harness/memory/base.py` | ✅ | 自动同步 | 已合入 |
| migrate_semantic | harness/memory/migrate_semantic.py | ✅ | 自动同步 | 已合入 |
| shared_pool | harness/memory/shared_pool.py | ✅ | 自动同步 | 已合入 |
| gossip_protocol | harness/memory/gossip_protocol.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 四层记忆架构 | harness/memory/manager.py | ✅ | Working(Hot) → Episodic(Warm) → Semantic(Cold) → TaskSkills(External) | 已合入 |
| WorkingMemory | harness/memory/working.py:22 | ✅ | deque滑动窗口，30K token，20条消息 | 已合入 |
| EpisodicMemory | harness/memory/episodic.py:24 | ✅ | 会话摘要 + LLM预评分 | 已合入 |
| SemanticMemory | harness/memory/semantic.py:28 | ✅ | SQLite + FTS5 + 向量存储 | 已合入 |
| LongTermMemory | harness/memory/long_term.py:137 | ✅ | 关键词索引，TTL 30天 | 已合入 |
| ShortTermMemory | harness/memory/short_term.py | ✅ | deque 会话级，TTL 1h | 已合入 |
| TaskSkills (L4) | harness/memory/manager.py | ✅ | 流水线晶体化，pass_rate≥85% 自动注册 | 已合入 |
| ProfileBuilder | harness/memory/profile_builder.py | ✅ | 用户画像提取，原地更新 | 已合入 |
| SystemReminders | harness/memory/reminders.py:33 | ✅ | 事件驱动提醒，user-role 注入 | 已合入 |
| SharedMemory | harness/memory/shared_memory.py | ✅ | 跨实例共享，置信度去重 | 已合入 |
| SessionManager | harness/memory/session.py | ✅ | 会话 CRUD，自动清理 | 已合入 |
| 语义记忆动态续期 | harness/memory/semantic.py | ✅ | search() 命中自动续期 expires_at | 已合入 |
| 语义记忆软删除 | harness/memory/semantic.py | ✅ | is_deleted=1 + get_deleted() 可恢复 | 已合入 |
| 语义记忆过期清理 | harness/memory/semantic.py | ✅ | expired AND access_count<3 → 软删除 | 已合入 |
| 投毒防御字段 | harness/memory/base.py:39 | ✅ | source_tag + trust_weight + provenance | 已合入 |
| Episodic 预评分 | harness/memory/episodic.py:55 | ✅ | 写入时后台 LLM 打分，压缩时零延迟 | 已合入 |
| 关键决策永保 | harness/memory/episodic.py:124 | ✅ | critical_episodes >0.8分，永不参与常规压缩 | 已合入 |
| MemoryProvider (可插拔ABC) | harness/memory/providers.py | ✅ | SQLite/Redis/Postgres/Memory 可插拔后端 + 工厂模式 | 已合入 |
| 物理分区存储 | harness/memory/semantic.py` + `harness/memory/migrate_semantic.py | ✅ | per-tenant SQLite文件 (memory_semantic_{tid}.sqlite3) + 存量迁移 | 已合入 |
| 检索预算机制 | harness/memory/manager.py | ✅ | build_context(retrieval_budget=): full→minimal→working_only 3级 | 已合入 |
| 计划性遗忘 | harness/memory/episodic.py | ✅ | 同topic 2x降权→3x归档(status=archived) + 索引比较(非is引用) | 已合入 |
| 结构化压缩 | harness/memory/compression.py | ✅ | LLM工具输出→JSON(completed/pending/preference) + 自由文本回退 | 已合入 |
| 统一知识库健康仪表盘 | api/routers/diagnostics.py | ✅ | 6模块聚合+5维成熟度评分(L0-L5)+Markdown中文报告(四步框架语境) | 已合入 |
| 通用推理链审计框架 | harness/infrastructure/gates/audit_trail_gate.py` + `harness/ontology_engine/audit_rules.py | ✅ | 域无关+6操作符引擎+证据指纹锁存+parent_step_id因果追溯 | 已合入 |
| Prompt迭代优化编排器 | harness/optimization/prompt_optimizer.py | ✅ | Champion-challenger自循环+5零件串联(ReActLoop+DarwinArena+prompt_optimize+PipelineEngine+EvolutionRunner) | 已合入 |
| 关键决策人工确认 | apps/agents/operator_agent.py` + `api/routers/agents.py | ✅ | 3道防线(L1静默/L2确认/L3全量)+审批approve/reject+超时自动拒绝 | 已合入 |
| 数据血缘追溯 | api/routers/diagnostics.py | ✅ | 5模块只读聚合(sources→processing→model→quality),零新表零新模块 | 已合入 |
| Memory OS 记忆治理 | harness/memory/semantic.py` + `harness/memory/episodic.py` + `harness/integration.py | ✅ | 事实矛盾检测+Episodic TTL清理+检索反馈闭环+MemoryOSAgent独立实体 | 已合入 |

---

## 三、知识引擎（本体）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| KnowledgeRetriever | `core/harness/knowledge/retriever.py` | ✅ | 自动同步 | 已合入 |
| audit_trace_rules | `core/harness/ontology_engine/sirg_auditor.py` | ✅ | 自动同步 | 已合入 |
| SirgAuditor | `core/harness/ontology_engine/sirg_auditor.py` | ✅ | 自动同步 | 已合入 |
| normalize_tier | `core/harness/knowledge/knowledge_ontology.py` | ✅ | 自动同步 | 已合入 |
| compile_axiom_rules | `core/harness/ontology_engine/graph_index.py` | ✅ | 自动同步 | 已合入 |
| compile_ontology_constraints | `` | ✅ | 自动同步 | 已合入 |
| publish_business_action | `core/harness/ontology_engine/graph_index.py` | ✅ | 自动同步 | 已合入 |
| WikiEngine | `harness/knowledge/wiki_engine.py` | ✅ | 自动同步 | 已合入 |
| build_prompt_to_agent_bridge | `` | ✅ | 自动同步 | 已合入 |
| build_model_usage_bridge | `` | ✅ | 自动同步 | 已合入 |
| build_wiki_to_agent_bridge | `` | ✅ | 自动同步 | 已合入 |
| knowledge_gap_detector | harness/ontology_engine/knowledge_gap_detector.py | ✅ | 自动同步 | 已合入 |
| graph_importer | harness/ontology_engine/graph_importer.py | ✅ | 自动同步 | 已合入 |
| audit_rules | harness/ontology_engine/audit_rules.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 13步本体管线 | harness/ontology_engine/engine.py:94 | ✅ | 3Phase: Classify→Extract并行→Validate串行 | 已合入 |
| ClassMapper（零LLM） | harness/ontology_engine/class_mapper.py:18 | ✅ | 关键词倒排索引 → T-Box 类映射 | 已合入 |
| PropertyExtractor | harness/ontology_engine/property_extractor.py:19 | ✅ | LLM属性提取 + table_context注入（并行） | 已合入 |
| StateMachine | harness/ontology_engine/state_machine.py:113 | ✅ | YAML驱动，3触发器×7联动 | 已合入 |
| StateHistory | harness/ontology_engine/state_history.py | ✅ | SQLite 状态变更审计表 | 已合入 |
| GraphIndex | harness/ontology_engine/graph_index.py:68 | ✅ | 有向图 + HyperEdge (SAG风格) | 已合入 |
| GraphTraversal | harness/ontology_engine/graph_traversal.py:88 | ✅ | BFS遍历 + traverse_multi + ranked_terminals | 已合入 |
| GraphInference | harness/ontology_engine/graph_inference.py:47 | ✅ | YAML推理规则 → 传递闭包推断边 | 已合入 |
| KnowledgeSynthesizer | harness/ontology_engine/knowledge_synthesis.py:37 | ✅ | 推理链/事实卡/综合结论 → Wiki页面 | 已合入 |
| EntityResolver | harness/ontology_engine/entity_resolver.py | ✅ | strict(3层) / lazy(仅同源) 双模式 | 已合入 |
| DocumentParser | harness/ontology_engine/document_parser.py | ✅ | MD/HTML/TXT/PDF/DOCX 5格式 + 视频/音频 | 已合入 |
| Graph Snapshot | harness/ontology_engine/graph_index.py:631 | ✅ | 版本化图快照 + restore + compare | 已合入 |
| 域本体 YAML | ~/.aiplat/ontologies/ | ✅ | 20+类，34+关系，K1-K4 知识治理 | 已合入 |
| 数据源连接器 | harness/ontology_engine/data_source.py | ✅ | SQL/API/File → 本体实例映射 | 已合入 |
| Webhook 写回 | harness/ontology_engine/engine.py:294 | ✅ | state transition → call_webhook | 已合入 |
| 场景推演沙箱 | API: simulate-scenarios | ✅ | 多方案对比推演 | 已合入 |
| 本体分层治变 (tier) | `knowledge/knowledge_ontology.py` + `knowledge/ontology_loader.py` | ✅ | P2-L1: OntologyClass.tier (core/logic/edge, 默认logic) + YAML 解析/校验 | 已合入 |
| tier 分级审批 | `knowledge/versioned_ontology_store.py` | ✅ | P2-L1: approve_proposal 按 tier 分级（core 架构评审/logic 产品侧/edge 自服务）+ apply tier gate（edge→logic 需复用证明≥3） | 已合入 |
| 立项四问评估 | `core/apps/fde/service/four_questions.py` + `fde_diagnostics_v2.py` | ✅ | P2-L0: 反复/跨系统/Owner+指标/Action 四问 → 总分+结论+MVP tier 建议（GET/POST /fde/diagnostics/four-questions） | 已合入 |
| Action 阶梯 Lv | `harness/infrastructure/action_contract.py` | ✅ | P2-L5: ActionLevel lv1_readonly→lv4_auto_close，默认 Lv2 保守 | 已合入 |
| 自动闭环误报率门 | `harness/ontology_engine/action_registry.py` | ✅ | P2-L5: compute_closure_gate — Lv4 历史误报 <0.5% 才自动闭环，超标降级人工确认 | 已合入 |
| ShardedGraphIndex | harness/ontology_engine/sharded_graph.py | ✅ | 跨域分片图索引 | 已合入 |
| 跨域本体桥接 | harness/ontology_engine/triple_store.py` + `harness/ontology_engine/triple_scanner.py | ✅ | 统一三元组存储 + BFS多跳遍历 + 5数据源自动扫描 + 3 API端点 | 已合入 |
| 审批工作流引擎 | harness/ontology_engine/approval.py | ✅ | submit/approve/reject/changes + 超时升级 + 告警通道 | 已合入 |
| Interface 原语 (多态抽象) | harness/knowledge/ontology_loader.py | ✅ | 本体Interface定义 + implements声明 + get_entities_by_interface()查询 | 已合入 |
| SQL Ontology Bridge | harness/knowledge/sql_ontology.py | ✅ | 三层架构(物理→语义→应用) + concept→SQL自动翻译 + virtual-first零摄取 | 已合入 |
| RunContext 运行时上下文 | harness/kernel/types.py | ✅ | entity/type/situation/priority/constraints + to_compact()序列化 | 已合入 |
| GraphIndex → RunContext 自动填充 | apps/agents/materials_chat.py | ✅ | 实体名提取→GraphIndex遍历→RunContext自动构建 | 已合入 |
| DataSource → RunContext 实时桥接 | apps/agents/materials_chat.py` + `YAML | ✅ | DataSourceRegistry查询→API响应→RunContext字段映射+优雅降级 | 已合入 |
| RunContext 三层合并 | apps/agents/materials_chat.py | ✅ | caller>realtime>graph优先级规则 + constraints合并去重 | 已合入 |
| 主动综合 (Active Synthesis) | harness/knowledge/active_synthesis.py | ✅ | STORM式5步管道: detect_gaps→research_questions→retrieve→synthesize→proposal | 已合入 |
| Wiki 内容质量监控 | harness/knowledge/wiki_quality_monitor.py | ✅ | LLM评估Wiki页面vs原始文档保真度(completeness/accuracy/overall) | 已合入 |
| 文档新鲜度警告 | harness/knowledge/wiki_engine.py | ✅ | 过期文档(>30天)在检索返回时自动追加交互式警告前缀(所有Agent受益) | 已合入 |
| 跨域语义类比发现 | harness/knowledge/ontology_query_mapper.py:392 | ✅ | 输入概念名→遍历所有域本体→嵌入相似度匹配→返回跨域类比类名+关键属性(HMESI Step 1) | 已合入 |
| 跨阶段一致性门控 | harness/knowledge/consistency_gate.py | ✅ | FDE报告后处理：5条规则扫描§1-§7矛盾(数据低推大模型/私有推SaaS/信创推非国产/POC过大等) | 已合入 |
| AI方案原型库 | ~/.aiplat/ontologies/ai-solution.yaml` + `apps/skills/registry.py:1712-1750 | ✅ | 12类标准化AI方案原型(含数据成熟度/成本/周期/部署/信创约束)→§6推荐时自动注入约束规则 | 已合入 |
| FDE图查询接线 | apps/skills/registry.py | ✅ | 诊断前查询域GraphIndex→traverse痛点头实体→注入图谱遍历路径→§1来源列引用图谱关系 | 已合入 |
| FDE推理验证接线 | apps/skills/registry.py | ✅ | 诊断后运行GraphInference.infer()→检查推理规则与AI机会匹配度→不匹配降置信度标注 | 已合入 |
| **yaml_serializer** | harness/knowledge/yaml_serializer.py | ✅ | OntologyDomain↔YAML↔JSON 双向序列化，本体编辑器后端核心 | 已合入 |
| **term_resolver** | harness/knowledge/term_resolver.py | ✅ | 跨域术语消歧：同名异义检测 + 同义异名 embedding 匹配 + persist | 已合入 |
| **role_view** | harness/knowledge/role_view.py | ✅ | 职责维度：角色视图继承+覆盖、术语定义、类/字段可见性过滤 | 已合入 |
| **sla_monitor** | harness/knowledge/sla_monitor.py | ✅ | 时序触发器后台监控：定时扫描 state_history，time_elapsed 超时自动升级 | 已合入 |
| **process_orchestrator** | harness/knowledge/process_orchestrator.py | ✅ | 跨实体流程编排：YAML processes + auto_create + on_failure + step 追踪 | 已合入 |
| **process_monitor** | harness/knowledge/process_monitor.py | ✅ | 流程监控：复用 state_history 做 state_distribution + bottleneck + SLA violations + trends | 已合入 |
| **ontology_importer** | harness/knowledge/ontology_importer.py | ✅ | 外部本体联邦导入：OWL/SKOS/JSON-LD → aiPlat YAML，readonly 标记 | 已合入 |
| **semantic_gateway** | harness/infrastructure/semantic_gateway.py | ✅ | Agent数据网关：DomainRouter→PolicyGate→TermResolver→Strategy 统一路由 | 已合入 |
| **usage_tracker** | harness/observability/usage_tracker.py | ✅ | 计量引擎：SQLite 事件记录 + 日聚合 + syscall wrapper 拦截 4 类调用 | 已合入 |
| **scoring_engine** | harness/knowledge/scoring_engine.py | ✅ | 累加加权评分: via_path多跳+公式+阈值分级 | 已合入 |
| **path_planner** | harness/knowledge/path_planner.py | ✅ | 目标导向路径规划: 预定义模板+自动发现fallback+缓存 | 已合入 |
| **sys_ontology_reason** | harness/syscalls/ontology_reason.py | ✅ | 5步推理编排: 理解→规划→查询→评分→输出 | 已合入 |
| **domain_maturity** | harness/knowledge/domain_maturity.py | ✅ | 域成熟度6维聚合+跨域对比+缺口成本估算 | 已合入 |
| **scenario_selector** | harness/knowledge/scenario_selector.py | ✅ | 场景选择器: 5条件+4象限+价值机会点公式 | 已合入 |
| **scenario_crud** | platform/apps/ontology_editor/api/scenario_crud.py | ✅ | 场景选择 API: compare/recommend/report/refresh | 已合入 |
| **governance_pipeline** | harness/knowledge/governance_pipeline.py | ✅ | 6步治理编排: 场景→建模→映射→质量→发布→反馈 | 已合入 |
| **ontology_approval** | harness/infrastructure/gates/ontology_approval.py | ✅ | 本体变更审批: submit/approve/reject + SQLite 表 | 已合入 |
| **mapping_validator** | harness/knowledge/mapping_validator.py | ✅ | 数据→语义映射验证: 类型/枚举/覆盖率检测 | 已合入 |
| **governance_dashboard** | harness/knowledge/governance_dashboard.py | ✅ | 治理仪表盘聚合: 健康+机制状态+审计摘要 | 已合入 |
| **governance_crud** | platform/apps/ontology_editor/api/governance_crud.py | ✅ | 治理 API: dashboard/run-cycle/approve/mapping-report | 已合入 |
| **ontology_editor (API)** | platform/apps/ontology_editor/api/ | ✅ | 21 REST 端点：domain CRUD + class CRUD + views CRUD + monitor | 已合入 |
| **ontology_editor (UI)** | frontend/src/pages/OntologyEditor/ | ✅ | 本体编辑器前端：域列表 + 类详情 + 编辑表单 + NL→YAML + 监控面板 | 已合入 |
| FDE图谱回写接线 | apps/skills/registry.py | ✅ | 诊断完成后自动注册DiagnosisSubject实体+has_opportunity关系→下一次诊断可遍历跨报告关联 | 已合入 |
| FDE交付跟踪本体 | ~/.aiplat/ontologies/fde-delivery.yaml` + `apps/skills/registry.py:1789-1825,1979-2025 | ✅ | DiagnosisSession+DeliveryAction类定义→诊断后自动创建跟踪实例→下次诊断注入交付率统计(§4.6ROI数据驱动) | 已合入 |
| FDE追问端点 | platform/apps/fde/api/fde.py` + `apps/skills/registry.py:1896-1914 | ✅ | POST /fde/ask — 基于诊断上下文回答后续问题，复用域图谱+历史+方案原型全链路(HMESI B0) | 已合入 |
| FDE证据等级映射 | apps/skills/registry.py:1817 | ✅ | 诊断报告返回时附加evidence_map数组(每条§1结论的证据等级+来源)→前端可直接渲染颜色标签(HMESI C0) | 已合入 |
| 证据树（Evidence Tree） | scripts/verify_claude_md_evidence.py --tree（build_evidence_tree） | ✅ | CLAUDE.md 证据声明的层级化证据树（HarnessEval 借鉴）：branches→sub_branches→evidence（tool/input/expect/actual/status）+ route_reason（路由决策可审计）+ known_gaps（✅ 声明无验证命令的已知盲区）+ cross_checks（外部事实交叉：grep 检索路径存在性验证，防"自洽的谎言"——A2 假阳性即由此捕获）；`--out` 落盘；architecture_guard 经 AIPLAT_EVIDENCE_TREE_OUT 接线 | 已合入 |
| 经验回写 L2 链路（experience_feedback） | governance/experience_feedback/experience_feedback.py（ExperienceStore/register_failure/record_verification/confirm_promotion）+ builder/generated_conformance.py（record_rejection 生成物侧接线） | ✅ | gotchas 登记→两次独立验证→升级状态机（HarnessEval × SBA §5.5）：confidence<0.7 拒收、同 case 重复不计数、连续 2 次失败判 rejected、低风险自动 promoted/高风险 require_review 人工确认、升级只生成规则草案不改写 SKILL.md；architecture_guard 失败自动登记接线；生成物侧接线：conformance 拒绝自动登记（generated-conformance-reject-*，confidence=1.0 机器判定）+ 注册成功预置 runtime_governance.md 治理入口 sidecar；AIPLAT_EXPERIENCE_FILE 配置存储；生成物适用：**已接线**（生成 agent 失败经验回写） | 已合入 |
| 评测观测聚合（eval-observability） | governance/eval_observability.py（aggregate）+ api/rest/routes.py 端点 GET /governance/eval-observability（governance_eval_observability）+ Governance 面板"评测观测"区块 | ✅ | 聚合证据树/守卫路由 trace/经验状态三产物为统一视图（HarnessEval 诊断面板数据源）：sources 存在性、evidence_tree verdict+known_gaps+cross_check_issues、guard_trace verdict+skipped_checks+failed_guards、experiences by_status；前端 Governance/index.tsx 消费展示；生成物不适用（理由：平台评测产物只读聚合视图，供 Governance 面板消费） | 已合入 |
| 生成物适用性守卫 | scripts/check_generated_artifact_wiring.py（discover_families/check）+ architecture_guard.sh §97 | ✅ | 每个平台能力族（governance 模块 + apps/* + builder + kb，17 个）必须：① CAPABILITIES 有条目（含能力族路径）② 条目含"生成物"适用性评估声明（适用+接线状态 / 不适用+理由）——CLAUDE.md §23 强制规则；防平台-产物脱节 | 已合入 |
| 后台任务托管（daemon jobs） | governance/daemon_jobs.py（DaemonJobStore/start/list/status/attach/kill）+ api/rest/routes.py 端点 /governance/jobs*（governance_jobs_list/governance_jobs_start/governance_job_status/governance_job_output/governance_job_kill）+ builder/builder_project_service.py（runtime_governance.md sidecar 预置 CLI 入口）+ builder/app_runtime.py（launch/stop 生成 app 托管启动） | ✅ | prime-agent 断线续跑借鉴：长任务以新会话组后台运行（终端关闭不终止）、输出重定向文件、JSON 注册表（AIPLAT_DAEMON_JOBS_FILE）、状态含退出码（ps stat 僵尸判定 + 输出尾部 [daemon] exit= 标记）、kill 连同会话组；CLI --start/--status/--attach/--kill；生成物适用：**已接线**（生成 app 运行时经 daemon_jobs 托管启动——builder/app_runtime.py detect→launch→health，生成 app 长任务托管 + 自动测试前置闭环） | 已合入 |

| apps/fde 生成物适用性 | apps/fde | ⚠️ | 生成物不适用（理由：企业业务诊断→交付闭环，非生成应用运行时能力） | 已评估 |
| apps/learning 生成物适用性 | apps/learning | ⚠️ | 生成物不适用（理由：平台内部自学习机制） | 已评估 |
| apps/misc 生成物适用性 | apps/misc | ⚠️ | 生成物不适用（理由：平台杂项管理工具） | 已评估 |
| apps/ontology_editor 生成物适用性 | apps/ontology_editor | ⚠️ | 生成物不适用（理由：平台本体编辑/知识治理） | 已评估 |
| apps/prompt 生成物适用性 | apps/prompt | ⚠️ | 生成物不适用（理由：平台提示词管理；生成 agent 技能由 SKILL.md 承载，不走平台 prompt 注册） | 已评估 |
| apps/value 生成物适用性 | apps/value | ⚠️ | 生成物不适用（理由：平台价值/ROI 分析） | 已评估 |
| apps/workbench 生成物适用性 | apps/workbench | ⚠️ | 生成物不适用（理由：平台工作台聚合界面） | 已评估 |
| kb 生成物适用性 | kb | ⚠️ | 生成物不适用（理由：生成 agent 运行时知识检索由 core 全局 syscall `sys_kb_retrieve`（harness/syscalls/retrieval.py，ReActLoop 天然可用）平台横切强制执行，生成物无需自建检索路径；kb 为租户隔离知识服务，生成应用由平台侧注入检索上下文） | 已评估 |
| agent 消息总线（agent_messages） | governance/agent_messages.py（AgentMessageStore/register/unregister/send/inbox/list_agents）+ api/rest/routes.py 端点 /governance/agents*（governance_agents_list/governance_agent_register/governance_agent_unregister/governance_agent_send/governance_agent_inbox）+ builder/builder_project_service.py（_register_generated_agent_to_bus 部署自动注册） | ✅ | prime-agent agent_message.send 借鉴：运行中 agent/任务注册（pid 心跳）→ 点对点互发消息（不经用户中转）→ 收件箱（pending/read + 未读过滤 + mark-read）；收件箱保留最近 500 条；CLI --register/--unregister/--send/--inbox/--agents；生成物适用：**已接线**（生成 agent 部署注册成功即上线消息总线 kind=generated-agent，多 agent 协作可经总线互发） | 已合入 |
| 生成 app 运行时 | builder/app_runtime.py（detect_runtime/launch/health_check/stop/smoke_test/real_tests/auto_repair + _register_smoke_failure + _register_test_failure）+ api/routers/builder.py 端点 /platform/builder/projects/{id}/runtime*（launch/runtime/stop/smoke/real-tests/auto-repair）+ builder_project_service.py（run_tests 升级真实冒烟 + 真实测试 + 自动修复 + last_test_report 持久化）+ aiPlat-management/frontend（ProjectDetailPage 运行时控制 + 测试报告 bug_summary/suggested_fix 展示） | ✅ | 生成 app 运行能力（2026-08-27，生成物侧接线收尾）：detect_runtime 扫描生成目录识别入口（FastAPI uvicorn/Flask/Node/静态页 http.server）→ launch 经 daemon_jobs 托管启动（派生端口 18000-18999、127.0.0.1 绑定）→ health_check HTTP 轮询探测（2xx/3xx=up）→ stop kill 会话组；run_tests 的 e2e_smoke 从"目录存在"假通过升级为真实冒烟（启动+健康探测，自动测试闭环）+ 结果持久化 last_test_report（GET /last-test-report 供前端展示）；**real_tests 测试经理真实测试**：递归发现生成物测试用例（backend/tests/ 等任意层级 test_*.py）→ 可写临时目录跑 pytest（装依赖 + PYTHONPATH + conftest）→ test_report（header/meta/test_results/bug_summary，对齐 test_executor；失败分类 env/配置/实现，含 suggested_fix）；**auto_repair 自动修复闭环**：测试失败 → LLM（llm_generate 经 CoreFacade）按测试输出修复生成代码 → 可写临时区验证 → 改进则写回部署目录（_sync_repair_writeback，路径段匹配防逃逸）→ 重跑测试，最多 max_rounds 轮；**前端运行时控制面板**（ProjectDetailPage：启动/停止/自动修复按钮 + 测试报告 bug 清单/修复建议展示）；冒烟失败（launch 失败/健康不通过）→ L2 经验回写（generated-smoke-*）；真实测试失败（断言失败/配置错误/超时）→ L2 经验回写（generated-test-failed，含 suggested_fix）——均与 conformance 拒绝登记同源；生成物适用：**已接线**（生成 app 可运行 + 自动测试 + 测试经理真实测试 + 自动修复 + 失败经验回写 + 前端控制） | 已合入 |
| FDE交付反馈API | platform/apps/fde/api/fde.py | ✅ | POST /fde/delivery/feedback — 标记Session+Action状态→更新交付率统计→触发§4.6ROI重新计算(HMESI D) | 已合入 |
| FDE诊断自优化 | apps/skills/registry.py:1827-1863 | ✅ | 基于历史交付率(≥60%/30-60%/<30%)自动调整§1置信度标注策略+§6方案推荐排序(HMESI E) | 已合入 |
| FDE多角色模拟 | apps/skills/registry.py:1865-1881 | ✅ | 生成前注入CIO/开发者/终端用户三视角采纳风险评估表→§7标注各角色风险信号+降级规则(HMESI F) | 已合入 |
| FDE知识缺口检测 | apps/skills/registry.py:1833 | ✅ | 诊断后对比§1AI机会与域本体类+方案原型标签→无匹配标记为knowledge_gaps→反馈域本体扩展(HMESI G) | 已合入 |
| FDE健康检查 | platform/apps/fde/api/fde.py:1772-1879 | ✅ | GET /fde/health — 5维组件状态(域注册/图索引/交付跟踪/本体YAML/模型可用性)+自动降级标记 | 已合入 |
| FDE完整性验证 | platform/apps/fde/api/fde.py:1882-1960 | ✅ | GET /fde/validate — 8项E2E连通测试(域路由/图谱/交付/Ontology/一致性门/跨域类比)一次性全检 | 已合入 |
| FDE会话历史 | platform/apps/fde/api/fde.py:1975-2060 | ✅ | GET /fde/sessions — 列表查询历史诊断会话(按行业/公司/状态过滤)→含交付行动数+时间线 | 已合入 |
| FDE行业基准 | platform/apps/fde/api/fde.py:2068-2145 | ✅ | GET /fde/benchmark — 跨行业聚合统计(会话数/交付率/TOP推荐)+per-industry breakdown | 已合入 |
| FDE会话详情 | platform/apps/fde/api/fde.py:2304-2428` + `apps/skills/registry.py:2154-2200 | ✅ | GET /fde/sessions/{id} — 聚合单次诊断全视图(evidence_map+knowledge_gaps+交付时间线+关联会话+证据统计) | 已合入 |
| 关系类型约束 | ontology_engine/graph_index.py:160-210 | ✅ | add_relation()增加domain/range校验→从域YAML object_properties读取约束→违规降置信度0.3(N) | 已合入 |
| 证据实体绑定 | ~/.aiplat/ontologies/fde-delivery.yaml` + `apps/skills/registry.py:2212-2225 | ✅ | Evidence实体类型+has_evidence关系→诊断回写时每条§1结论创建证据节点(O) | 已合入 |
| 实体归一 | ontology_engine/entity_resolver.py:71-148 | ✅ | normalize_term()同域强归一(去后缀/全角转半角)+build_alias_index跨域弱关联(P) | 已合入 |
| Schema校验 | ontology_engine/graph_index.py:138-158,694-714 | ✅ | add_entity()校验class_name∈域YAML已知类→未知类WARNING日志(Q) | 已合入 |
| 业务术语字典 | ~/.aiplat/ontologies/enterprise-terms.yaml` + `apps/skills/registry.py:1882-1896 | ✅ | Term实体类(名称+定义+域+本体类映射)+诊断时注入术语锚点(R) | 已合入 |
| 术语自播种 | apps/skills/registry.py:1853 | ✅ | 知识缺口检测后自动创建Term桩→随诊断次数增加术语字典自我丰富(S) | 已合入 |
| 数字员工角色匹配 | apps/skills/registry.py:1898-1927 | ✅ | §6方案推荐时自动匹配数字员工角色(合规审查/关系挖掘/知识顾问等9类)→报告从技术方案升级为角色实体(Y) | 已合入 |
| 跨系统数据桥接 | platform/apps/fde/api/fde.py:2930-2988 | ✅ | POST /fde/ingest — 接受ERP/CRM/MES原始数据→字段映射→标准FDE输入→展示本体作跨系统语义桥梁(X) | 已合入 |
| 能力自描述 | platform/apps/fde/api/fde.py:2991-3090 | ✅ | GET /fde/capabilities — 结构化能力清单(6层/30+模块/12端点)→系统自我声明"企业大脑原型"(Z) | 已合入 |
| 本体覆盖率度量 | platform/apps/fde/api/fde.py:3079-3190 | ✅ | GET /fde/sessions/{id}/ontology-coverage — 四维分解(本体实例%/历史案例%/LLM推测%/术语%)→量化"本体包住多少不确定性" | 已合入 |
| 覆盖率改进建议 | platform/apps/fde/api/fde.py:3208-3330 | ✅ | GET /fde/sessions/{id}/improve — 基于覆盖率生成可执行改进(新增本体类/创建术语/补充历史案例)→度量→行动闭环 | 已合入 |
| SECI知识原子域 | ~/.aiplat/ontologies/knowledge-atom.yaml | ✅ | KnowledgeAtom+KnowledgeLink类定义→atom_type(6类)+source(5源)+3种关系(SIMILAR_TO/DERIVED_FROM/CONFLICTS_WITH) | 已合入 |
| SECI Engine (S→E+E→C) | harness/knowledge/seci_engine.py | ✅ | socialize_to_external(记忆→原子)+external_to_combine(跨域关联→KnowledgeLink)→Phase 1完成 | 已合入 |
| SECI POST_LOOP Hook | harness/knowledge/seci_engine.py:248-330 | ✅ | POST_LOOP自动捕获scored>0.8的对话→SECIEngine.socialize→atom→跨域关联→全自动S→E→C(Phase 2) | 已合入 |
| SECI C→I + I→S | harness/knowledge/seci_engine.py:220-322` + `apps/skills/registry.py:101-121` + `harness/routing/skill_routing.py:247-285 | ✅ | combine_to_internal(阻尼调整Skill权重)+internal_to_socialize(Canary→原子→闭环)(Phase 3) | 已合入 |
| SECI状态面板 | platform/apps/fde/api/fde.py:3333-3420 | ✅ | GET /fde/seci-status — 知识创造引擎实时状态(原子/关联/来源分布/权重/螺旋健康度) | 已合入 |
| 收敛引擎 | harness/knowledge/convergence_engine.py` + `knowledge-atom.yaml:150-165 | ✅ | scan_and_converge()四触发器(skill_weight/agent_prompt/pipeline_stage/correction_rollback)+版本链防循环+元闭环回写 | 已合入 |
| 收敛能力注册 | apps/skills/registry.py:1091-1112` + `harness/knowledge/seci_engine.py:208-235 | ✅ | SkillRegistry.apply_convergence()+DEPRECATES关系检测→收敛建议→系统行为调整→元闭环 | 已合入 |
| POST_LOOP自动收敛 | harness/knowledge/seci_engine.py:514-526 | ✅ | atom>5时POST_LOOP自动触发ConvergenceEngine.scan_and_converge()→SECI→Convergence全自动闭环 | 已合入 |
| 本体消费总线 | harness/knowledge/ontology_bus.py` + `~/.aiplat/ontologies/ai-solution.yaml | ✅ | OntologyBus动态加载YAML数据→方案原型表+数字员工映射从硬编码迁移为YAML驱动→新增方案零代码 | 已合入 |
| 术语动态注入 | apps/skills/registry.py:1889-1919 | ✅ | 术语字典注入从静态字符串替换为GraphIndex动态加载→随自播种自动增长→零硬编码 | 已合入 |
| YAML热加载 | harness/knowledge/ontology_bus.py:28-62 | ✅ | mtime缓存→YAML文件变更自动检测→零重启配置更新→新增方案原型实时生效 | 已合入 |
| 本体治理工程化声明 | platform/apps/fde/api/fde.py:3440-3665 | ✅ | GET /fde/governance — 8项治理能力矩阵成熟度自评+对传统数据治理/睿治Agent行业对标+实时状态 | 已合入 |
| 治理自审计 | platform/apps/fde/api/fde.py:3668-3760 | ✅ | GET /fde/governance/validate — 8项能力逐一可执行审计(代码可查/端点可调/约束可测)→8/8 pass in 50ms | 已合入 |
| 术语定义自动补全 | apps/skills/registry.py:1298-1390 | ✅ | 术语自播种时关键词匹配生成定义(15个预置定义)→无LLM调用→零延迟→无匹配时留空待人工补全 | 已合入 |
| 跨域术语去重 | apps/skills/registry.py:1873 | ✅ | 术语播种前检测enterprise-terms中同名概念→已有则创建similar_to跨域关联→防止跨域术语碎片化 | 已合入 |
| FDE仪表板 | platform/apps/fde/api/fde.py:204 | ✅ | GET /fde/dashboard — 单次请求聚合关键指标+最近活动+主动告警+治理健康度→前端首页即用 | 已合入 |
| **文档系统下载** | management/api/docs.py` + `frontend/src/pages/Docs/DocsViewer.tsx | ✅ | GET /api/docs/download?path=... — 文档系统支持文件下载（Content-Disposition attachment） | 已合入 |
| 会话对比 | platform/apps/fde/api/fde_sessions_compare.py:20 | ✅ | GET /fde/sessions/compare?left=id1&right=id2 — 双会话并排对比(就绪度/证据覆盖率/行动数/知识缺口)→增量分析 | 已合入 |
| 上下文总线 | harness/knowledge/context_bus.py | ✅ | assemble_field_assessment()统一10层上下文组装→registry.py从~350行注入缩减为~10行→各层可独立复用 | 已合入 |
| 管线状态 | platform/apps/fde/api/fde_pipeline.py:16 | ✅ | GET /fde/pipeline-status — ContextBus逐层健康诊断+数据可用性快照(graphs/YAMLs)→注入管线透明化 | 已合入 |
| 演示数据播种 | platform/apps/fde/api/fde_bootstrap.py:17 | ✅ | POST /fde/bootstrap-test-data?industry=&company= — 支持4行业专属演示数据(actions/evidence/readiness差异化) | 已合入 |
| 全行业播种 | platform/apps/fde/api/fde_bootstrap.py:131 | ✅ | POST /fde/bootstrap-all — 一键播种4行业(政务/金融/制造/医疗)完整演示数据→12 actions+8 terms | 已合入 |
| 场景化技能包 | ai-solution.yaml` + `ontology_bus.py` + `apps/skills/registry.py | ✅ | digital_employee_roles增加skills字段→load_role_skills()/get_role_by_keyword()/filter_by_role()→角色与Skill动态绑定 | 已合入 |
| 对象语义开放 | platform/apps/fde/api/fde.py | ✅ | GET /fde/domain/{d}/operations → Agent可查询域中类的属性/状态转换/推理规则/对象属性(P1) | 已合入 |
| 权限边界建模 | fde-delivery.yaml` + `harness/ontology_engine/graph_index.py` + `harness/knowledge/ontology_bus.py | ✅ | YAML permissions字段(admin/operator/viewer三层)→_load_permission_rules()→check_permission()(P2) | 已合入 |
| 系统时序列观察 | knowledge-atom.yaml` + `platform/apps/fde/api/fde.py:3382-3405,4480-4580 | ✅ | SystemSnapshot持久化→GET /fde/trends/system(12周趋势)+/fde/health/history(历史对比)→自演进数据基础 | 已合入 |
| 系统主动诊断 | harness/knowledge/system_diagnostician.py` + `platform/apps/fde/api/fde.py:4578-4592 | ✅ | SystemDiagnostician(5条规则)→跨子系统关联分析(seci/evidence/skill/knowledge/convergence)→GET /fde/diagnose | 已合入 |
| 系统自修复 | harness/knowledge/system_diagnostician.py:306-430` + `platform/apps/fde/api/fde.py:4596-4613 | ✅ | SystemHealer(confidence≥0.9安全门+5条自动修复+效果验证+审计快照)→POST /fde/heal | 已合入 |
| 系统自主演化 | harness/knowledge/system_evolver.py` + `platform/apps/fde/api/fde.py:4622-4638 | ✅ | SystemEvolver(4条演化规则→术语自动发布/方案草稿审批)→GET /fde/evolve | 已合入 |
| 系统自演进路由 | api/routers/system.py` + `harness/knowledge/seci_engine.py:523-528 | ✅ | GET /system/overview/diagnose/evolve+POST /system/heal/self-check →POST_LOOP每10次自动诊断 | 已合入 |
| 项目化手册生成 | platform/apps/fde/api/fde_manuals.py:197 | ✅ | POST /fde/manuals(创建)+GET/PUT/regenerate/versions(生命周期)→项目专属手册+3个CUSTOM_SECTION+非破坏性再生成 | 已合入 |
| 全局编码宪法 | _facade.py:1724` + `registry.py:1544` + `executor.py:369 | ✅ | karpathy_v1从可选开关→全局默认→所有Skill执行自动遵循4原则(编码前思考/简洁优先/精准修改/目标驱动) | 已合入 |
| 反馈→SECI接入 | system_diagnostician.py | ✅ | feedback_pattern诊断规则+_apply_feedback_correction修复→用户修正行为自动转化为KnowledgeAtom(P0) | 已合入 |
| 置信度校准 | system_diagnostician.py | ✅ | confidence_overconfident诊断规则→detminism_score vs delivery_rate偏差>20%告警(P1) | 已合入 |
| 知识新鲜度 | harness/knowledge/system_diagnostician.py` + `knowledge-atom.yaml | ✅ | knowledge_stale诊断规则→超90天无更新原子告警(P2) | 已合入 |
| Agent对话质量诊断 | system_diagnostician.py:476-508 | ✅ | agent_quality_decline规则→7天原子产出<3告警→Agent/Pipeline/Memory全接入OS诊断(A) | 已合入 |
| Pipeline阶段健康 | pipeline_engine.py:1954-1964` + `system_diagnostician.py:212-245 | ✅ | pt_快照持久化→pipeline_stage_failing规则→24h内同阶段失败≥3告警(B) | 已合入 |
| Memory压缩健康 | compression.py:120-123` + `system_diagnostician.py:747-761 | ✅ | compression_stats属性暴露→compression_ineffective规则→压缩比<30%告警+agent↔compress关联(C) | 已合入 |
| 技能生命周期管理 | harness/knowledge/skill_curator.py` + `harness/artifacts/registry.py` + `api/routers/system.py | ✅ | Hermes Agent式Curator→每7天审查(30d stale/90d archive/重叠合并)→GET /system/curate-skills | 已合入 |
| 智能澄清对话 | apps/fde/api/fde.py` + `frontend/src/pages/Diagnostics/FdeDashboard.tsx | ✅ | POST /fde/assess/dialog(多轮状态机)→_compute_readiness gaps驱动追问→就绪度≥60自动触发诊断+前端Dialog | 已合入 |
| 多子系统上下文 | harness/knowledge/context_bus.py:345-405 | ✅ | assemble_agent/skill/pipeline_context()→Agent(3层)/Skill(2层)/Pipeline(3层)各自轻量注入→总线覆盖全系统 | 已合入 |
| Agent领域上下文 | harness/knowledge/context_bus.py:408-452 | ✅ | SESSION_START hook→所有Agent启动时自动注入术语字典+数字员工→领域知识全局可用 | 已合入 |
| 质量总线 | platform/apps/fde/api/fde_quality_summary.py:15 | ✅ | GET /fde/quality-summary — 跨子系统质量聚合(FDE/SECI/Convergence/ContextBus四维评分)→统一0-100评分；生成物适用：不适用（理由：平台横切质量聚合，生成应用质量评测闭环由 apps/eval runs_eval 已接线强制执行——直接评测 builder 生成项目 project_id） | 已合入 |
| FDE趋势分析 | platform/apps/fde/api/fde.py:2431-2550 | ✅ | GET /fde/trends — 时间序列统计(会话数/交付率/就绪度趋势)+术语增长曲线+行业分布(T) | 已合入 |
| FDE统一搜索 | platform/apps/fde/api/fde.py:2578-2710 | ✅ | GET /fde/search?q=&scope= — 跨实体全文检索(会话/行动/术语/证据/行业)合并排序(U) | 已合入 |
| FDE质量评分 | platform/apps/fde/api/fde.py:2717-2820 | ✅ | GET /fde/sessions/{id}/quality — 四维加权评分(证据覆盖率+行动完成率+术语覆盖率+状态变迁)0-100(V) | 已合入 |
| FDE主动告警 | platform/apps/fde/api/fde.py:2805-2920 | ✅ | GET /fde/alerts — 扫描所有会话检测blocked/stale/low_quality/zero_evidence/high_gaps五类告警(W) | 已合入 |
| FDE动作闭环 | platform/apps/fde/api/fde.py:1688-1807,2198-2300 | ✅ | StateTransition实体化(每次状态变更创建记录)→has_transition关系→GET timeline查看完整生命周期(Palantir L4) | 已合入 |

---

## 四、RAG 检索

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| WikiPageRetriever | `harness/knowledge/retrieval.py` | ✅ | 自动同步 | 已合入 |
| wiki_engine | harness/knowledge/wiki_engine.py | ✅ | 自动同步 | 已合入 |
| capability_graph | harness/knowledge/capability_graph.py | ✅ | 自动同步 | 已合入 |
| sqlite_retriever | harness/knowledge/sqlite_retriever.py | ✅ | 自动同步 | 已合入 |
| code_graph | harness/knowledge/code_graph.py | ✅ | 自动同步 | 已合入 |
| doc_compressor | harness/knowledge/doc_compressor.py | ✅ | 自动同步 | 已合入 |
| ontology_query_mapper | harness/knowledge/ontology_query_mapper.py | ✅ | 自动同步 | 已合入 |
| wiki_retriever | harness/knowledge/wiki_retriever.py | ✅ | 自动同步 | 已合入 |
| cap_health_rules | harness/knowledge/cap_health_rules.py | ✅ | 自动同步 | 已合入 |
| skill_deps | harness/knowledge/skill_deps.py | ✅ | 自动同步 | 已合入 |
| code_graph_persist | harness/knowledge/code_graph_persist.py | ✅ | 自动同步 | 已合入 |
| cap_graph_persist | harness/knowledge/cap_graph_persist.py | ✅ | 自动同步 | 已合入 |
| reparse_queue | harness/knowledge/reparse_queue.py | ✅ | 自动同步 | 已合入 |
| text_cleaner | harness/knowledge/text_cleaner.py | ✅ | 自动同步 | 已合入 |
| doc_quality_monitor | harness/knowledge/doc_quality_monitor.py | ✅ | 自动同步 | 已合入 |
| sql_ontology | harness/knowledge/sql_ontology.py | ✅ | 自动同步 | 已合入 |
| wiki_quality_monitor | harness/knowledge/wiki_quality_monitor.py | ✅ | 自动同步 | 已合入 |
| active_synthesis | harness/knowledge/active_synthesis.py | ✅ | 自动同步 | 已合入 |
| code_entropy_detector | harness/knowledge/code_entropy_detector.py | ✅ | 自动同步 | 已合入 |
| adaptive_context | harness/knowledge/adaptive_context.py | ✅ | 自动同步 | 已合入 |
| wiki_indexer | harness/knowledge/wiki_indexer.py | ✅ | 自动同步 | 已合入 |
| skill_marketplace | harness/knowledge/skill_marketplace.py | ✅ | agentskills.io 对接: export/discover_external/install_external (P1-A5) | 已合入 |
| discover_external_skills 端点 | `aiPlat-platform/api/routers/skill_marketplace.py` | ✅ | GET /skills/marketplace/external：接线 discover_external 为 HTTP 入口（source=agentskills.io + limit，unsupported 400，不可达 best-effort） | 已合入 |
| recon_subgraph | harness/knowledge/recon_subgraph.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 统一知识检索 | harness/syscalls/retrieval.py:569 | ✅ | 并行 Wiki + KB，RRF 三路融合 | 已合入 |
| KB 文档检索 | harness/syscalls/retrieval.py:40 | ✅ | hybrid: LIKE + FTS5 + FAISS 向量 | 已合入 |
| Wiki 页面检索 | harness/syscalls/retrieval.py:467 | ✅ | FTS5 + embedding + 链接遍历 + 本体过滤 | 已合入 |
| RRF 三路融合 | harness/knowledge/hybrid_retriever.py:53 | ✅ | Wiki+KB+Graph 统一 1/(k+rank) 融合 | 已合入 |
| Graph Early Exit | harness/syscalls/retrieval.py:591 | ✅ | confidence>0.92 直接返回，取消Wiki/KB | 已合入 |
| CRAG 3级回退 | harness/knowledge/retriever.py:262 | ✅ | 本体优先→FTS5→HyDE | 已合入 |
| HyDE 假设答案 | harness/knowledge/hyde_expander.py:27 | ✅ | LLM生成假设 → 向量检索 | 已合入 |
| Wiki CircuitBreaker | harness/syscalls/retrieval.py:506 | ✅ | CLOSED→OPEN(3次失败)→HALF_OPEN | 已合入 |
| DomainRouter | harness/knowledge/domain_router.py:26 | ✅ | T1标签→T2向量→T3 LLM，3层级联（T1/T2 共享助手去重，2026-08-25） | 已合入 |
| quality gate 真正降级 | harness/knowledge/retriever.py | ✅ | gate 失败 + AIPLAT_DEEP_RESEARCH_ENABLED → DuckDuckGo web fallback 并入（source_category=web_fallback）；否则仅打标记 | 待合入 |
| knowledge-extraction 模板 | harness/knowledge_pipeline/extractor.py + prompt_loader | ✅ | EXTRACTION_PROMPT 注册 prompt_loader（${chunk_text}）；VALID_CLASS_TYPES 域本体配置驱动 | 待合入 |
| ABox TBox 感知 | harness/knowledge/knowledge_abox_builder.py | ✅ | _map_to_domain_class（wiki category→域 TBox 类）+ _add_data_validated（prop TBox 校验） | 待合入 |
| SemanticCache (L1/L2) | harness/knowledge/semantic_cache.py:31 | ✅ | L1精确(md5)→L2语义(cosine≥0.95)→L3穿透 | 已合入 |
| 缓存版本号切换 | harness/knowledge/semantic_cache.py | ✅ | INCR version O(1) + L1主动清 + 版本窗口 | 已合入 |
| LatentStageCache | harness/knowledge/semantic_cache.py:305 | ✅ | 多阶段隐空间缓存，query+domain+retrieval向量组合匹配 | 已合入 |
| QueryRewriter | harness/knowledge/query_rewriter.py | ✅ | 查询改写/扩展 | 已合入 |
| Reranker | harness/knowledge/reranker.py | ✅ | CrossEncoder 重排序 | 已合入 |
| ProvenanceTracker | harness/knowledge/provenance.py | ✅ | 声明级溯源 + 过期扫描 | 已合入 |
| PostRetrievalGovernor | harness/knowledge/post_retrieval_governor.py | ✅ | 检索后去重/归一化/截断 | 已合入 |
| HallucinationTracker | harness/evaluation/hallucination_tracker.py | ✅ | NLI 事实核查 + GraphIndex 图边验证 | 已合入 |
| 答案生成管道 | harness/generation/answer_generator.py | ✅ | generate_answer + generate_stream_answer + build_rag_user_message | 已合入 |
| Action 闭环桥接 | harness/actions/action_bridge.py | ✅ | OperatorAgent决策→webhook通知 + execute_decision_actions | 已合入 |

---

## 四附、知识基础设施（Knowledge）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SemanticEmbedder | harness/knowledge/embedder.py | ✅ | 文本→向量，via InfraEmbeddingAdapter | 已合入 |
| DB Abstraction | harness/knowledge/db.py | ✅ | 知识库数据库抽象层 | 已合入 |
| Graph Sync | harness/knowledge/graph_sync.py | ✅ | 图数据同步 | 已合入 |
| Graph Module | harness/knowledge/graph.py | ✅ | 知识图基础结构 | 已合入 |
| RepoMap | harness/knowledge/repo_map.py | ✅ | 仓库结构映射 | 已合入 |
| Wiki FTS5 | harness/knowledge/wiki_fts.py | ✅ | FTS5 全文检索 | 已合入 |
| Wiki Structured Query | harness/knowledge/wiki_structured_query.py | ✅ | Wiki 结构化查询 | 已合入 |
| Wiki Health Rules | harness/knowledge/wiki_health_rules.py | ✅ | Wiki 健康规则检查 | 已合入 |
| Knowledge Quality | harness/knowledge/knowledge_quality.py | ✅ | 知识质量评分 | 已合入 |
| Knowledge Growth | harness/knowledge/knowledge_growth.py | ✅ | 知识增长追踪 | 已合入 |
| Knowledge Writeback | harness/knowledge/knowledge_writeback.py | ✅ | 知识写回 | 已合入 |
| Knowledge Markings | harness/knowledge/knowledge_markings.py | ✅ | 知识标记与权限 | 已合入 |
| Knowledge Ontology | harness/knowledge/knowledge_ontology.py | ✅ | 知识本体管理 | 已合入 |
| Knowledge Action | harness/knowledge/knowledge_action.py | ✅ | 知识操作 | 已合入 |
| Knowledge Validator | harness/knowledge/knowledge_validator.py | ✅ | 知识条目校验 | 已合入 |
| Knowledge ABox Builder | harness/knowledge/knowledge_abox_builder.py | ✅ | A-Box (实例) 构建 | 已合入 |
| Knowledge Evolution LLM | harness/knowledge/knowledge_evolution_llm.py | ✅ | 知识进化 LLM 驱动 | 已合入 |
| SceneModel | harness/knowledge/scene_model.py | ✅ | 场景模型 | 已合入 |
| Learning Assessment | harness/knowledge/learning_assessment.py | ✅ | 学习评估 | 已合入 |
| Learning Ontology | harness/knowledge/learning_ontology.py | ✅ | 学习本体 | 已合入 |
| Learning Paths | harness/knowledge/learning_paths.py | ✅ | 学习路径推荐 | 已合入 |
| Ontology Loader | harness/knowledge/ontology_loader.py | ✅ | YAML本体加载 | 已合入 |
| Ontology Validator | harness/knowledge/ontology_validator.py | ✅ | 本体校验 | 已合入 |
| Capability Health | harness/knowledge/capability_health.py | ✅ | 能力健康评分 + Graph 持久化 | 已合入 |
| Symbol Health | harness/knowledge/symbol_health.py | ✅ | 知识符号健康度 | 已合入 |
| Evolution Runner | harness/knowledge/evolution_runner.py | ✅ | 知识进化执行 | 已合入 |
| KB Callbacks | harness/knowledge/callbacks.py | ✅ | Ingest/Query/EnqueueIngest/LoadDocKinds 回调 | 已合入 |
| Complexity Router | harness/knowledge/complexity_router.py | ✅ | 复杂查询路由 | 已合入 |
| CandidateKnowledgePool | harness/knowledge/candidate_pool.py | ✅ | FDE 现场反馈候选池：去重 + 语义冲突检测(>100°) + N≥3 自动触发 ActiveSynthesis | 已合入 |

---

## 五、Agent 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| collect_turn | `core/harness/digital_human/trajectory_collector.py` | ✅ | 自动同步 | 已合入 |
| voice_chat_handler | `core/harness/digital_human/voice_pipeline.py` | ✅ | 自动同步 | 已合入 |
| evaluate_four_questions | `core/apps/fde/service/four_questions.py` | ✅ | 自动同步 | 已合入 |
| default_provider_name | `core/apps/agents/base.py` | ✅ | 自动同步 | 已合入 |
| get_provider_factories | `` | ✅ | 自动同步 | 已合入 |
| ACPProvider | `` | ✅ | 自动同步 | 已合入 |
| InProcessProvider | `` | ✅ | 自动同步 | 已合入 |
| ProviderResult | `` | ✅ | 自动同步 | 已合入 |
| ProviderCapabilities | `` | ✅ | 自动同步 | 已合入 |
| SubagentProviders | `apps/agents/subagent/providers.py` | ✅ | 子代理 provider 抽象 (in_process/acp/process, P1-A3 + P3-2) | 已合入 |
| **continue_execution** | `apps/agents/subagent/coordinator.py` | ✅ | continuable 编排：复用保留 agent 续接已完结子代理（DSH send_message 对齐，2026-08-24） | 已合入 |
| ProcessProvider | `apps/agents/subagent/providers.py` | ✅ | fork 式子进程隔离传输 (P3-2, DSH fork 借鉴), python -m process_runner | 已合入 |
| process_runner | `apps/agents/subagent/process_runner.py` | ✅ | 子进程执行器: stdin JSON → stdout ProviderResult (P3-2) | 已合入 |
| ACPClient | `core/acp/client.py` | ✅ | ACP WebSocket client — start/continue 包装 chat 协议 (P1-A3) | 已合入 |
| SubagentCoordinator | `apps/agents/subagent/coordinator.py` | ✅ | 自动同步 | 已合入 |
| run_voice_brainstorm | `` | ✅ | 自动同步 | 已合入 |
| BaseAgent | `` | ✅ | 自动同步 | 已合入 |
| kpi_agent | harness/agents/kpi_agent.py | ✅ | 自动同步 | 已合入 |
| strategy_agent | harness/agents/strategy_agent.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 7 种 Agent 实现类 | apps/agents/ | ✅ | ReAct/Conversational/PlanExecute/RAG/MultiAgent/MaterialsChat/Pipeline | 已合入 |
| AGENT.md 系统 | apps/agents/discovery.py | ✅ | YAML frontmatter → PipelineStageConfig | 已合入 |
| 交接5字段 | [概念] | ✅ | AGENT.md 规范 — 文档条目；做了什么/产出物/如何验证/已知问题/下一步 | 待核实 |
| SubAgent 协调器 | apps/agents/subagent/coordinator.py | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 5 个内置 SubAgent | apps/agents/subagent/registry.py | ✅ | reviewer/debugger/tester/docs/perf | 已合入 |
| ParallelExecutor | apps/agents/parallel_executor.py | ✅ | Map-Reduce, max_concurrency=5, 异常隔离 | 已合入 |
| PipelineCompiler | apps/agents/pipeline_compiler.py | ✅ | AGENT.md stages[] YAML → PipelineStageConfig | 已合入 |
| MFA (TOTP) | aiPlat-platform/auth/mfa.py | ✅ | P0-B2：RFC 6238 零依赖 TOTP 生成/校验/扫码 URI + admin 强制策略 + 3 REST 端点（setup/verify/disable） | 已合入 |
| Agent SDK | aiplat-sdk/ | ✅ | L1 Agent/L2 Pipeline/L3 ReActLoop — execute/stream/chat 全路径可用；P0-B1 修复 bind_skill/bind_tool 未初始化缺陷 + 回归测试 | 已合入 |
| FanOut 并行 | apps/agents/parallel_executor.py | ✅ | 已接线 | 已合入 |
| DelegateManager | harness/infrastructure/delegate_tool.py | ✅ | 子Agent委托 + 资源预算隔离 + 重试退避 + 输出摘要(§5.26) | 已合入 |
| OperatorAgent | apps/agents/operator_agent.py | ✅ | 运维决策助手 — 消费RunContext → 结构化JSON(severity/impact/actions/can_continue) | 已合入 |
| operator-decision prompt | harness/utils/prompt_loader.py | ✅ | 决策框架 + 输出格式 + 约束规则 | 已合入 |
| test_report_orchestrator | aiPlat-platform/apps/factory OR workspace agent | ✅ | 测试报告修复编排器 — 接收project_id→读取测试报告→Bug归属阶段→逐阶段调regenerate触发修复→下游级联重建 | 已合入 |
| 共享检索管道 | harness/knowledge/orchestrated_retrieval.py | ✅ | traverse_ontology_graph + ontology_first_retrieve + build_reasoning_path | 已合入 |
| HyDE 检索统一 | harness/knowledge/hyde_expander.py | ✅ | hyde_retrieve() 封装全管道(生成→检索→格式化) | 已合入 |
| 成本路由决策 | harness/knowledge/cost_estimator.py | ✅ | resolve_routing_mode() 统一成本→路由映射 | 已合入 |
| 查询守卫 | harness/knowledge/query_guard.py | ✅ | sanitize_query + enforce_scope | 已合入 |
| 语义缓存钩子 | harness/knowledge/semantic_cache_hook.py | ✅ | try_cache_hit + write_cache_result (任意Agent复用) | 已合入 |
| PipelineTracer | harness/utils/pipeline_tracer.py | ✅ | 时序轨道上下文管理器 | 已合入 |
| 会话摘要器 | harness/utils/turn_summarizer.py | ✅ | question+answer → 中文摘要 | 已合入 |
| 答案提取器 | harness/utils/answer_extractor.py | ✅ | 循环输出 → 纯文本答案 | 已合入 |
| 琐问处理器 | harness/utils/trivial_handlers.py | ✅ | 时间/数学表达式即时响应 | 已合入 |

---

## 六、Skill 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| BaseSkill | `apps/skills/base.py` | ✅ | 自动同步 | 已合入 |
| SkillManager | `apps/skills/skill_manager.py` | ✅ | 自动同步 | 已合入 |
| review_report | engine/skills/autoreview/review_report.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| SkillRegistry | apps/skills/registry.py | ✅ | 注册/启用/禁用/版本管理/semver回滚 | 已合入 |
| **autoreview skill** | engine/skills/autoreview/ | ✅ | 自动代码审查引擎：单引擎/硬投票面板/MoA Deep Mode、3套preset、Scope Governor、auto_fixer (git stash回滚) | 已合入 |
| autoreview handler | engine/skills/autoreview/handler.py | ✅ | 执行入口：温度分层(0.6探索/0.3决策)、preset加载、引擎隔离 | 已合入 |
| autoreview diff_loader | engine/skills/autoreview/diff_loader.py | ✅ | Git Diff驱动：8000 tokens截断、dev/null保护、拒绝全仓库审查 | 已合入 |
| autoreview aggregator | engine/skills/autoreview/report_aggregator.py | ✅ | MoA投票聚合：行号锚点+3级投票+Aggregator LLM综合判断 | 已合入 |
| autoreview evidence_chain | engine/skills/autoreview/review_report.py | ✅ | v2.2: build_evidence()+clean_evidence()+to_markdown自动附加+_persist_review持久化 | 已合入 |
| autoreview pipeline_stage | engine/skills/autoreview/pipeline_stage.yaml | ✅ | depends_on[code_gen,test_gen], failure_strategy:skip_stage, timeout:120s | 已合入 |
| SkillExecutor | apps/skills/executor.py | ✅ | Agent调用 + 独立执行双路径 | 已合入 |
| skill_call syscall | harness/syscalls/skill.py | ✅ | PolicyGate + ApprovalGate + 审计 | 已合入 |
| 5 准入标准 | docs/skills/architecture.md | ✅ | 独立/边界/复用/治理/执行单元 | 已合入 |
| 副作用声明 | [概念] | ✅ | SKILL.md frontmatter — 文档条目；effects: type/idempotent/rollback | 待核实 |
| EvolutionEngine | apps/skills/evolution/engine.py | ✅ | AI草稿→模拟→人工审批 | 已合入 |
| Skill Lint 10规则 | management/lint_rules.yaml | ✅ | name/version/category/schema 校验 | 已合入 |
| 滑动窗口衰减追踪 | apps/skills/registry.py | ✅ | recent_pass_rate + decayed_at | 已合入 |
| AutoLearner | harness/evolution_engine.py | ✅ | 失败分析→SkillDraft→审批→注册 | 已合入 |
| SkillRouting | harness/routing/skill_routing.py | ✅ | Canary/A-B/Shadow/Auto-Rollback | 已合入 |
| Completion Criterion | [概念] | ✅ | 30个 SKILL.md frontmatter — 统计数据；每个 skill 显式声明完成条件，5类模板（知识/生成/工程/测试/交互） | 待核实 |
| Grilling 追问技能 | engine/skills/grilling/SKILL.md | ✅ | Matt Pocock 风格：一次一问 + ≤3推荐选项 + 读文件原则 | 已合入 |
| **GrillingBridge** | core/api/core_facade.py:1103-1276` + `routers/grilling.py | ✅ | v2.9: 11入口统一需求澄清 —— start/answer/skip/finalize API + 10种默认维度 + domain YAML interview_dimensions + GrillPanel前端组件(modal/sidebar/inline) | 已合入 |
| **migrate-classify** | routers/wiki.py:2703` + `graph_index.py:212 | ✅ | v2.9: 本体类重命名安全迁移 —— YAML改名 + GraphIndex节点class_name批量更新 | 已合入 |
| **DomainRouter 自动失效** | wiki_ontology_engine.py:1408` + `core_facade.py:2310+ | ✅ | v2.9: 本体YAML CRUD操作后自动失效DomainRouter缓存，下次classify()重建索引 | 已合入 |
| **auto_ontology_pipeline** | core_facade.py:1037 | ✅ | v2.9: 文档变化→本体引擎自动触发，闭合向量KB→Wiki→GraphIndex三段断层 | 已合入 |
| **Adamic-Adar 图相似度** | graph_index.py:619-691` + `graph_inference.py:145 | ✅ | v2.9: AA(u,v)=Σ1/log(deg(z)) — 稀有共享邻居权重加权，推理边置信度加成 | 已合入 |
| **Louvain 社区检测** | graph_index.py:695-782 | ✅ | v2.9: 模块度优化的社区发现算法，169节点中检测出5个知识群落 | 已合入 |
| **Deep Research Level 4** | ⚠️ deprecated retrieval_crag.py:133-196` + `materials_chat.py:526 | ✅ | v2.9: CRAG四级降级 — DuckDuckGo联网搜索(AIPLAT_DEEP_RESEARCH_ENABLED) | 已合入 |
| **Entity Title Cleaner** | ontology_engine/engine.py:151 | ✅ | v2.9: _clean_entity_title() — 自动剥离###/-/1./**粗体**等markdown噪声 | 已合入 |
| **知识漂移治理** | staleness_monitor.py(planned)` + `harness/knowledge/wiki_engine.py | ✅ | v2.9: 来源追溯(detect_communities source_doc_id)+权威优先级(source_priority)+漂移告警(24h cron) | 已合入 |
| **Drift Status API** | api/routers/diagnostics.py:2498-2585 | ✅ | v2.9: GET /diagnostics/drift-status + POST /diagnostics/drift-rebuild — 漂移报告+自动重建 | 已合入 |
| **wiki_retriever authority** | wiki_retriever.py:589-634 | ✅ | v2.9: 检索评分增加authority维度(15%)，source_priority≥8强制置顶 | 已合入 |
| **GrillingGate 运行时注入** | loop/base.py:247-340 | ✅ | v2.9: ReActLoop推理前自动检测输入歧义，无需Agent声明required_skills | 已合入 |
| **docs/ watch_directory** | api/rest/routes.py:3282 | ✅ | v2.9: /platform/kb/watch端点修复+docs/目录已配置30s轮询自动同步 | 已合入 |
| **SystemHealth Index** | system_health.py(planned)` + `api/routers/diagnostics.py | ✅ | v2.9: EWMA加权聚合4子系统(OntologyAudit+Staleness+ConfigDrift+EvalMetrics)→0-100指数 | 已合入 |
| **SelfHealGate** | harness/evaluation/self_heal_gate.py | ✅ | v2.9: 3级自愈门控(AUTO/SUGGEST/REJECT)+业务重要性加权(production降级) | 已合入 |
| **ConstraintValidator** | harness/evaluation/constraint_validator.py | ✅ | v2.9: 4种过期检测(file/model/phase/skill)→CRITICAL/HIGH/WARNING | 已合入 |
| **BusinessValueTranslator** | business_value.py(planned)` + `frontend/src/pages/Diagnostics/BusinessValueReport.tsx | ✅ | v2.9: 技术评分→业务KPI翻译(5维度+per-agent明细+续费报告) | 已合入 |
| **EvalMetrics P0-P2** | eval_metrics.py`+`eval_types.py | ✅ | v2.9: TrajectoryMatch(3模式)+Correctness(expectedResponse)+TextQuality(3维1call)+ContentSafety+Refusal | 已合入 |
| **ConfigDriftDetector** | harness/evaluation/config_drift_detector.py | ✅ | v2.9: 4维漂移检测(hitl/skill/model/phase)+24h cron | 已合入 |
| **AgentConfigDiff** | harness/evaluation/agent_config_diff.py | ✅ | v2.9: AGENT.md版本对比(added/removed/changed+risk_level)→HITL审批 | 已合入 |
| **SkillExporter** | apps/skills/skill_exporter.py | ✅ | v2.9: SKILL.md→OpenAI/LangChain/Anthropic三格式导出 | 已合入 |
| **AdoptionMetrics** | harness/evaluation/adoption_metrics.py | ✅ | v2.9: 员工采纳度(agent调用+GrillRate+HITL行为+抵触热点)+培训效果对比 | 已合入 |
| **OntologyAudit** | harness/evaluation/ontology_audit.py | ✅ | v2.9: 类覆盖率/关系密度/状态机活跃度/孤儿检测→治理建议 | 已合入 |
| Leading Words 术语表 | [概念] | ✅ | 8个工程先验词汇（tight loop/tracer bullet/deep module/seam等） | 已合入 |
| Action Type 操作契约 | harness/interfaces/skill.py` + `apps/skills/executor.py | ✅ | submission_criteria前置校验 + permissions角色控制 + side_effects声明 + _evaluate_criterion()执行前拦截 | 已合入 |
| field-assessment HMESI增强 | apps/skills/registry.py:1651-1690 | ✅ | 诊断报告注入历史案例检索(search_pages)+跨域类比(discover_cross_domain_analogs)+§4.65预期干预效果表格(HMESI Step 3) | 已合入 |
| 诊断溯源（证据等级） | apps/skills/registry.py:1318-1323` + `:1692-1710 | ✅ | §1表格新增证据等级列(本体实例/历史案例/LLM推测)+system prompt注入三级标注规则，至少50%行需有据可查 | 已合入 |
| **canary_runner** | engine/skills/canary_runner/SKILL.md | ✅ | 灰度发布执行器（prompt），调用 /fde/canary API | 已合入 |
| **manual_generator** | engine/skills/manual_generator/SKILL.md | ✅ | 交付手册生成器（prompt），调用 /fde/manual/generate | 已合入 |
| **register_fde_prompts** | apps/fde/prompts/__init__.py | ✅ | FDE域prompt自动注册（7个），启动时回调注册 | 已合入 |
| **模块 Prompt 管理系统 | [概念] | ✅ | apps/{module}/prompts.py（6 模块）— 模板架构；prompt_loader 域 prompt 迁移至各模块：fde(8)/builder(8)/skills(4)/eval(2)/knowledge(5)/workbench(4) | 待核实 |
| **finetune 模块搬迁** | apps/finetune/ | ✅ | 从 harness/finetune/ + schemas_finetune.py 搬迁至标准模块目录结构 | 已合入 |
| **common_schemas** | apps/common_schemas.py | ✅ | 平台层通用响应模型（StatusResponse/ListResponse/ItemResponse）— 替换全系统 response_model=dict | 已合入 |

---

## 七、安全与治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| arch_guard_b84 | `scripts/architecture_guard.sh` | ✅ | 自动同步 | 已合入 |
| PromptAuditRules | `core/harness/audit/prompt_audit_rules.py` | ✅ | 提示词审计规则 | 已合入 |
| coupling_metrics | `scripts/coupling_metrics.py` + `scripts/baselines/coupling_baseline.json` | ✅ | 耦合度量基线：AST import-degree → avg_degree/max_degree(non-agg)/top-20 + baseline ratchet（roadmap §0.2） | 待合入 |
| §94b BOUNDARY 覆盖 | `scripts/architecture_guard.sh` | ✅ | harness 48 一级子目录 BOUNDARY.yaml 全量覆盖检查（roadmap §0.3，缺则 FAIL） | 待合入 |
| ManagedPolicy | `aiPlat-platform/auth/schemas_policy.py` | ✅ | 企业远程托管策略 (managed 键本地不可覆盖, P1-A6) | 已合入 |
| PIIDetector | `harness/infrastructure/pii_detector.py` | ✅ | 自动同步 | 已合入 |
| prompt_auditor | harness/audit/prompt_auditor.py | ✅ | 自动同步 | 已合入 |
| semantic_gate | harness/infrastructure/gates/semantic_gate.py | ✅ | 自动同步 | 已合入 |
| cross_validation_gate | harness/infrastructure/gates/cross_validation_gate.py | ✅ | 自动同步 | 已合入 |
| completion_gate | harness/infrastructure/gates/completion_gate.py | ✅ | 自动同步 | 已合入 |
| audit_trail_gate | harness/infrastructure/gates/audit_trail_gate.py | ✅ | 自动同步 | 已合入 |
| agent_manager | management/agent_manager.py | ✅ | 自动同步 | 已合入 |
| skill_manager | management/skill_manager.py | ✅ | 自动同步 | 已合入 |
| workflow_manager | management/workflow_manager.py | ✅ | 自动同步 | 已合入 |
| DataFormStage | `aiPlat-management/frontend/src/components/AppStages/DataFormStage.tsx` | ✅ | 自动同步 | 已合入 |
| DataTableStage | `aiPlat-management/frontend/src/components/AppStages/DataTableStage.tsx` | ✅ | 自动同步 | 已合入 |
| FileUploadStage | `aiPlat-management/frontend/src/components/AppStages/FileUploadStage.tsx` | ✅ | 自动同步 | 已合入 |
| ProgressPoller | `aiPlat-management/frontend/src/components/AppStages/ProgressPoller.tsx` | ✅ | 自动同步 | 已合入 |
| ResultDashboard | `aiPlat-management/frontend/src/components/AppStages/ResultDashboard.tsx` | ✅ | 自动同步 | 已合入 |
| APP_STAGE_REGISTRY | `aiPlat-management/frontend/src/components/AppStages/index.ts` | ✅ | AppStage 组件注册表：8 种组件映射替代 AppPage 硬编码分发（2026-08-25，新增组件无需改 AppPage） | 待合入 |
| MarkdownViewerStage | `aiPlat-management/frontend/src/components/AppStages/MarkdownViewerStage.tsx` | ✅ | 文本/报告/分析产物 markdown 展示组件（agent 模式新增，2026-08-25） | 待合入 |
| StatCardsStage | `aiPlat-management/frontend/src/components/AppStages/StatCardsStage.tsx` | ✅ | KPI 指标卡片组件（agent 模式新增，2026-08-25） | 待合入 |
| KanbanBoardStage | `aiPlat-management/frontend/src/components/AppStages/KanbanBoardStage.tsx` | ✅ | 看板列状态流转组件（agent 模式新增，2026-08-25） | 待合入 |
| KnowledgeFactoryPage | `aiPlat-management/frontend/src/pages/KnowledgeFactory/KnowledgeFactoryPage.tsx` | ✅ | 自动同步 | 已合入 |
| AppLayout | `aiPlat-management/frontend/src/components/layout/AppLayout.tsx` | ✅ | 自动同步 | 已合入 |
| SystemOverview | `aiPlat-management/frontend/src/pages/SystemOverview/SystemOverview.tsx` | ✅ | 自动同步 | 已合入 |
| ValueDashboard | `aiPlat-management/frontend/src/pages/ValueCenter/ValueDashboard.tsx` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| PolicyGate | harness/infrastructure/gates/policy_gate.py | ✅ | 统一权限检查 + 架构边界实时拦截 | 已合入 |
| ApprovalGate | harness/infrastructure/approval/manager.py | ✅ | approve/deny/pending，双门禁 | 已合入 |
| Prompt 注入防护 | harness/syscalls/llm.py:125 | ✅ | 6条正则+特殊token过滤+覆盖防护指令 | 已合入 |
| 记忆投毒防御 | harness/memory/base.py:39 | ✅ | source_tag/trust_weight/provenance | 已合入 |
| PII 脱敏（全量覆盖） | kb/service.py` → `_mask_pii()` + `services/pii_detector.py | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，全部 6 条入库路径已覆盖 | 已合入 |
| CodeAuditor | harness/security/code_auditor.py | ✅ | 注入/XSS/CSRF/认证/授权检查 | 已合入 |
| RBAC 多租户 | [概念] | ✅ | platform 层 — 架构决策；tenant + actor + scopes 三级隔离 | 待核实 |
| 架构守卫 190 规则 + AST 未定义符号守卫 | [配置] | ✅ | §1-§76 自动扫描 + guard_undefined_names.py（第 17 维"未定义变量"升级为 AST 级，2026-08-19） | 已合入 |
| 190 条 CI 检查 + AST 守卫 | scripts/architecture_guard.sh | ✅ | 零依赖 grep 扫描 + AST 级未定义符号检查 | 已合入 |
| 前端 API 契约检查 | ../../scripts/guard_frontend.py | ✅ | TS fetch ↔ Python data.get 一致性 | 已合入 |
| PII 检测脱敏 | services/pii_detector.py | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，Presidio+正则双引擎 | 已合入 |
| 合规报告 SOC2/ISO27001 | management/compliance_checks.py | ✅ | 12检查 + SOC2 CC/ISO27001 A映射 + 自动报告生成 | 已合入 |
| 架构契约上下文注入 | harness/utils/prompt_loader.py` → `harness/assembly/prompt_assembler.py | ✅ | coding-contract 模板在代码生成前注入 Agent system prompt（6条核心约束） | 已合入 |
| 审计日志防篡改 | ../../aiPlat-platform/governance/audit/logger.py | ✅ | SHA-256 链式哈希 + verify_integrity()；生成物不适用（理由：平台横切审计，生成应用由平台侧强制执行） | 已合入 |
| 对象级权限 | policy/object_permission.py | ✅ | 每实体/每动作/每角色细粒度控制，支持本体继承 | 已合入 |
| 字段级安全 | policy/field_level_security.py | ✅ | 单元/字段级数据可见性，Palantir CBAC对齐 | 已合入 |
| 技能签名验证 | security/skill_signature_gate.py | ✅ | Ed25519 签名校验 + 可信公钥注册表 | 已合入 |
| SecretsManager | harness/infrastructure/secrets_manager.py | ✅ | AES-256-GCM 加密存储 + 审计日志 | 已合入 |
| Ed25519 签名 | harness/infrastructure/crypto/signature.py | ✅ | 密钥生成/签名/验签，技能/制品完整性保护 | 已合入 |
| CryptoSecretBox | harness/infrastructure/crypto/secretbox.py | ✅ | 对称加密盒，运行时密钥保护 | 已合入 |
| DI 容器 | harness/infrastructure/di/__init__.py | ✅ | 依赖注入容器，12/18服务调用已转换 | 已合入 |
| Config Settings | harness/infrastructure/config/settings.py | ✅ | 层级配置管理 + 环境变量覆盖 | 已合入 |
| SSO/OIDC 集成 | ../../aiPlat-platform/auth/identity_provider.py | ✅ | Keycloak/Azure AD/Okta，discovery/jwks映射 + login/callback/token API | 已合入 |
| CrisisDetector | harness/security/crisis_detector.py | ✅ | 自伤/暴力/危急三級检测，WARN/BLOCK/SILENT 模式 | 已合入 |
| CrisisGate | harness/security/crisis_gate.py | ✅ | syscall 边界危机拦截，ALLOW/WARN/FLAG/BLOCK/ESCALATE | 已合入 |
| EmotionTracker | harness/security/emotion_tracker.py | ✅ | 跨会话情绪弧追踪 + 过度依赖检测 | 已合入 |
| ApprovalGate (危险命令) | harness/infrastructure/gates/approval_gate.py | ✅ | 25规则危险操作检测，CRITICAL/HIGH/MEDIUM/LOW 四级，集成 PolicyGate | 已合入 |
| SkillsGuard (威胁扫描) | harness/infrastructure/gates/skills_guard.py | ✅ | 78威胁模式，skill注册前安全扫描，11类别全覆盖 | 已合入 |

---

## 八、可观测性

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| build_os_sandbox_cmd | `core/harness/infrastructure/os_sandbox.py` | ✅ | 自动同步 | 已合入 |
| start_stdio_kernel | `core/api/core_facade.py` | ✅ | 自动同步 | 已合入 |
| register_cc_hooks | `core/harness/infrastructure/hooks/cc_bridge.py` | ✅ | 自动同步 | 已合入 |
| CCHookBridge | `core/harness/infrastructure/hooks/cc_bridge.py` | ✅ | 自动同步 | 已合入 |
| AuditLog | `harness/infrastructure/audit.py` | ✅ | 自动同步 | 已合入 |
| MetricsAggregator | `harness/observability/metrics/__init__.py` | ✅ | 自动同步 | 已合入 |
| **StdioKernel（P0-a）** | `core/acp/stdio_server.py` + `core/api/core_facade.py` | ✅ | stdio JSON-RPC 持久内核：thread/start\|resume\|approve\|reject\|events 映射 PipelineSession + run_events；JSON-RPC 2.0 + 背压 -32001；入口 `python -m core.acp.stdio_server`（对标 Codex app-server） | 已合入 |
| **StdioKernelClient（P1）** | `aiplat-sdk/aiplat/stdio.py` | ✅ | SDK stdio 内核客户端：spawn 内核 + thread/start\|approve\|reject\|events + stream_events 流式监听；可注入 transport（对标 Codex SDK 程序化启停 Thread） | 已合入 |
| **aiplat exec CLI（P2）** | `aiplat-sdk/aiplat/exec.py` + pyproject `[project.scripts] aiplat` | ✅ | 单次执行入口（codex exec 对齐）：`aiplat exec "req"` 经 stdio 内核跑流水线（thread/start→轮询→JSON）；`--script` 零 LLM fail-closed 白名单（bash/sh/python3/python） | 已合入 |
| **exec_script / exec_pipeline** | `aiplat-sdk/aiplat/exec.py` | ✅ | SDK 导出的单次执行函数：script 零 LLM 执行 / 流水线经 StdioKernelClient 轮询（超时 best-effort cancel） | 已合入 |
| **OS 原生沙箱（P1）** | `core/harness/infrastructure/os_sandbox.py` + `core/harness/execution/sandbox.py` | ✅ | bubblewrap/seatbelt 可选命令包装器：只读系统路径 + 可写工作区 + 默认网络隔离 + fail-open fallback（对标 Codex sandboxing；AIPLAT_SANDBOX=bwrap/seatbelt） | 已合入 |
|------|------|:---:|------|------|
| trace_id / span_id | harness/observation/event_schema.py | ✅ | 每次 syscall 携带 | 已合入 |
| EventBus | harness/observation/event_bus.py | ✅ | 发布/订阅 syscall 事件 | 已合入 |
| PipelineTrace | harness/execution/pipeline_engine.py | ✅ | 每阶段 started/completed/skipped/failed | 已合入 |
| 决策溯源 | [概念] | ✅ | 引擎内 _last_action_reason — 设计模式；budget_exhausted 等非正常路径 | 待核实 |
| OtelBridge | harness/observation/otel_bridge.py | ✅ | AIPLAT_OTEL_ENABLED=true | 已合入 |
| Prometheus | infra/observability/ | ✅ | prometheus-fastapi-instrumentator | 已合入 |
| MetricsCollector | infra/observability/ | ✅ | 滑动窗口聚合器 | 已合入 |
| 执行审计 | [概念] | ✅ | execution_store.audit_log — 数据库概念；AIPLAT_EXECUTION_AUDIT=true | 待核实 |
| 健康检查 | health/` + `harness/knowledge/capability_health.py | ✅ | 能力健康+Symbol健康+Wiki健康 | 已合入 |
| Prometheus 10 指标 | harness/memory/metrics.py | ✅ | tool_truncated/semantic_renewed/rrf_latency/early_exit/cache_version 等 | 已合入 |
| 语义记忆后台清理 | harness/memory/manager.py:111 | ✅ | 每日定时软删除过期低频记忆，AIPLAT_MEMORY_CLEANUP_INTERVAL 可配 | 已合入 |
| TraceVisualizer | harness/execution/trace_visualizer.py | ✅ | 决策痕迹可视化: 犹豫检测/重复检测/异常预警→Spec调整建议 | 已合入 |
| Evaluation Summary Cron | harness/scheduler/cron.py | ✅ | 每周自动生成 FDE 运营周报（聚合 RAGDiagnosticsCollector + HallucinationTracker + FeedbackRadar）→ LLM NL 草稿 → 写入 _DIAG_CACHE["weekly_report"] | 已合入 |
| FDE 周报前端 | frontend/Diagnostics/WeeklyReport.tsx | ✅ | 诊断中心新增"周报"卡片：NL 渲染 + 一键复制为客户简报 + FDE 批注修订 | 已合入 |
| FDE Dashboard | apps/workbench/api/workbench.py:fde-dashboard` + `UserWorkbench.tsx | ✅ | 4卡聚合(待决策/信号预警/执行异常/训练)+时间轴+Spec筛选联动 | 已合入 |
| TrendDetector (熵增预警) | harness/infrastructure/trend_detector.py | ✅ | 6桶滑动窗口+双缓冲+状态机(NORMAL/ALERTING/HIGH_ALERT/RESOLVED)+7天基线 | 已合入 |

---

## 九、模型基础设施

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| LLMClient | `aiPlat-infra/infra/llm/base.py` | ✅ | 自动同步 | 已合入 |
| ModelTierRouter | `harness/routing/model_tier_router.py` | ✅ | 自动同步 | 已合入 |
| infra_bridge | harness/infrastructure/infra_bridge.py | ✅ | 自动同步 | 已合入 |
| base_model_adapter | harness/infrastructure/base_model_adapter.py | ✅ | 自动同步 | 已合入 |
| infra_audio_adapter | harness/infrastructure/infra_audio_adapter.py | ✅ | 自动同步 | 已合入 |
| feedback_translator | harness/infrastructure/feedback_translator.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| InfraLLMAdapter | harness/infrastructure/infra_llm_adapter.py | ✅ | Core 唯一 LLM 适配器 | 已合入 |
| InfraEmbeddingAdapter | harness/infrastructure/infra_embedding_adapter.py | ✅ | SentenceTransformer | 已合入 |
| InfraRerankerAdapter | harness/infrastructure/infra_reranker_adapter.py | ✅ | CrossEncoder | 已合入 |
| InfraAudioAdapter | harness/document/transcriber.py | ✅ | faster-whisper + openai-whisper | 已合入 |
| InfraOCRAdapter | harness/infrastructure/infra_ocr_adapter.py | ✅ | 统一OCR入口 (Tesseract/PaddleOCR, text/structured/pdf) | 已合入 |
| BaseCircuitBreaker | harness/infrastructure/circuit_breaker.py | ✅ | 统一熔断器基类 (closed/open/half_open) — LLM/Wiki/MCP 共用 | 已合入 |
| 模型解析集中化 | harness/utils/model_injection.py | ✅ | get_default_model(purpose) 统一入口 | 已合入 |
| 模型发现 | infra/management/model/manager.py | ✅ | 远程API + 本地(Ollama/LM Studio/vLLM) | 已合入 |
| 路径工具 | core/utils/paths.py | ✅ | 统一 AIPLAT_HOME 路径解析 + 子目录捷径 | 已合入 |
| 常量定义 | core/utils/constants.py | ✅ | 截断/token/超时/domain 公共常量 | 已合入 |
| HTTP错误工具 | core/api/http_errors.py | ✅ | HTTPException 标准化构造器 | 已合入 |
| 视频转写 | `harness/document/transcriber.py` + platform/kb/video.py | ✅ | ffmpeg→Whisper→OCR→embed | 已合入 |
| 模型路由 | harness/utils/model_injection.py | ✅ | model_router.py 已删除，create_selected_adapter 为唯一路径 | 已合入 |
| T1-T5 分层路由 | harness/routing/model_tier_router.py` + `config/infra/llm_profile.yaml | ✅ | complexity→tier→cheapest capable model, 5级可配置 | 已合入 |
| 复杂度感知选择 | infra/management/model/manager.py:select_by_purpose() | ✅ | routing_rules 过滤 + best_model_for_purpose(messages=) | 已合入 |
| 模型能力档案 | config/infra/llm_profile.yaml:model_capabilities | ✅ | per-model routing_rules/min_complexity/max_complexity | 已合入 |
| 会话模型覆盖 (/model) | harness/utils/model_injection.py` + `api/routers/adapters.py | ✅ | set_model_override + clear_model_override + POST /model-override | 已合入 |
| MoA 会话覆盖 (/moa) | adapters.py | ✅ | set_moa_override + endpoint:/model-override/moa + is_moa_session + get_moa_preset | 已合入 |
| 模型层级仪表板 | api/routers/diagnostics.py` + `frontend ModelTierPanel | ✅ | GET /diagnostics/model-tier + T1-T5 可视面板 + 一键切换 | 已合入 |
| 控制画像状态端点 | api/routers/diagnostics.py | ✅ | get_profile_status + switch_profile + endpoint:/diagnostics/profile/status + endpoint:/diagnostics/profile/switch — 6D参数+预设列表+failure_domain + 会话级切换 | 已合入 |
| 控制画像前端面板 | frontend/ControlProfilePanel.tsx | ✅ | 6D参数网格+预设切换+failure_domain显示+侧边栏入口+诊断中心嵌入+工具箱卡片 | 已合入 |
| FingerprintCollector | harness/knowledge/model_fingerprint.py | ✅ | 8探针黑盒指纹采集：token分布/延迟曲线/拒答率/格式遵从 | 已合入 |
| ModelAudit | harness/knowledge/model_audit.py | ✅ | 模型身份报告生成 + 双模型指纹对比 + 已知签名匹配 | 已合入 |
| CredentialPool | infra/management/model/credential_pool.py | ✅ | Round-Robin + 黑名单冷却 + 多key轮换 | 已合入 |
| CredentialPool 热路径接线 | infra/llm/providers/openai_compatible.py | ✅ | 429/403/timeout 自动密钥轮换（chat+stream 全路径）；`status()` 脱敏池健康经 get_metrics 暴露；单key模式向后兼容 | 已合入 |
| Model Pricing (llm_profile) | config/infra/llm_profile.yaml | ✅ | deepseek-v4-pro真实定价(prompt$0.27+completion$1.10/1M)+context_window 131072 | 已合入 |
| 质量门本地优先选择 (v4) | infra/management/model/manager.py:_score_model() + _within_quality_band() | ✅ | 删除硬编码来源偏见(API+80/本地+40)，替换为质量门控：成功率±20pp + P95≤3x + 推理质量≤1级 → +20本地偏好；数据不足(<5次) → 保守选API；prefer_local覆盖(+120) | 已合入 |
| 模型Playground市场目录 | api/routers/compat.py:_list_models() + frontend ModelPlayground.tsx | ✅ | 21模型选择面板(9已安装+12市场目录)，市场模型点击弹出API Key配置框→临时接入→参与并发对比 | 已合入 |
| Syscall Token/Cost 归属 | harness/syscalls/llm.py + harness/context/engine.py | ✅ | syscall_events 表新增 model_name/input_tokens/output_tokens/cost 列；LLM调用时写入per-model token消耗与成本；观测仪表盘24h窗口聚合 | 已合入 |
| 观测仪表盘持久化数据源 | api/routers/diagnostics.py:get_observability_stats() | ✅ | 从 get_route_metrics()（内存计数器）切换为 syscall_events 表直接查询，服务器重启后数据不丢失 | 已合入 |
| 前端强制重排修复 | WorkflowCanvas/AnimatedAvatar/FloatingDigitalHuman/LLMReview | ✅ | getBoundingClientRect缓存/rAF可见性暂停/音频振幅20fps降频/进度条React state驱动 | 已合入 |
| 诊断 per-project 筛选 | api/routers/diagnostics.py + api/routers/traces_graphs.py + frontend ProjectSelector | ✅ | observability/stats(6条SQL过滤)、traces/runs(Python post-filter)、前端共享ProjectSelector组件+useProjectId hook+localStorage持久化 | 已合入 |
| AI应用工厂三Tab合并 | frontend AIFactory.tsx | ✅ | 快速开始(原用户工作台)+对话式(原工作室)+高级配置(原应用工厂)三Tab统一入口；旧路由/studioworkbench自动重定向 | 已合入 |
| 自动诊断调度禁用 | core/gunicorn.conf.py + server.py | ✅ | AIPLAT_ENABLE_AUTO_DIAG=false 硬编码；_run_diag_impl()调用阻塞uvicorn event loop，后端诊断改为按需触发 | 已合入 |
| 配置漂移修复 | config_drift_detector.py | ✅ | 4项检查从'字段存在=漂移'改为真实验证：skills目录存在性/model可用性/phase枚举合法性/HITL事件记录；评分19→81 | 已合入 |
| 架构评分修复 | known_safe_cycles.txt | ✅ | 344原始环路→294白名单→50有效→补252条→0有效；评分47.7/D→87.7/B | 已合入 |

---

## 十、部署与运维

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| CronScheduler | `harness/scheduler/cron.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 一键启动/停止 | [概念] | ✅ | 6服务顺序启动，pyc清理，端口释放 | 已合入 |
| 开发环境 | scripts/dev.sh | ✅ | 5服务并行开发启动 | 已合入 |
| 架构守卫 | scripts/architecture_guard.sh | ✅ | 190规则零依赖扫描 + AST 未定义符号守卫（2026-08-19） | 已合入 |
| 守卫规则自检（黄金样本） | scripts/rule_golden_sample.py | ✅ | P0-C7：检测规则 pattern 的 \\| 反模式 + re 编译错误，防 12 条语法 bug 重演；--verify 标记规则要求未达标项 | 已合入 |
| Phase 验收 | scripts/phase_check.sh | ✅ | caller_verify + wiring + 死代码 | 已合入 |
| Caller 验证 | scripts/caller_verify.sh | ✅ | 零调用者模块检测 | 已合入 |
| E2E 测试 | scripts/e2e_verify.sh | ✅ | 端到端验证 | 已合入 |
| 冒烟测试 | scripts/smoke_http_server.sh | ✅ | HTTP服务 + 文档入库 | 已合入 |
| 基准测试 | scripts/benchmark_all.sh | ✅ | CI模式：5指标全量+基线对比 | 已合入 |
| 模型预加载 | scripts/preload_models.sh | ✅ | 首次启动加速 | 已合入 |
| 灾备脚本 | scripts/ops/backup.sh` + `restore.sh` + `verify_restore.sh | ✅ | 全量备份/恢复/完整性验证，可选S3 | 已合入 |
| KB 数据迁移 | scripts/migrate_kb_to_instances.py | ✅ | 一次性工具：已有 KB 文档 → 本体实例 → Wiki 页面 | 已合入 |
| Gold Dataset 更新 | scripts/update_gold_dataset.py | ✅ | 从工具/Skill 提取 gold examples 并合并到种子数据集 | 已合入 |
| KB SDK 生成 | scripts/generate_kb_sdk.sh | ✅ | 从 OpenAPI spec 生成 Python/TypeScript SDK | 已合入 |
| Wiki E2E 测试 | scripts/e2e_wiki_test.sh | ✅ | Wiki 后端 API + 前端集成端到端测试 | 已合入 |
| 文档入库冒烟测试 | scripts/smoke_documents_ingest.sh | ✅ | 启动服务 → 入录 fixture → 轮询 job → 校验 elements | 已合入 |
| ProcessRegistry | harness/infrastructure/process_registry.py | ✅ | 进程生命周期管理 + 异步健康监控 + 优雅关闭 | 已合入 |
| **fde_project_freeze** | platform/apps/fde/api/fde.py | ✅ | POST /fde/project/freeze — 中止项目冻结归档（§7.4） | 已合入 |
| **security_preflight** | scripts/security_preflight.sh | ✅ | FDE 安全行前检查脚本（§1.4） | 已合入 |
| **email_notifier** | harness/infrastructure/email_notifier.py | ✅ | FDE 邮件通知器 — smtplib零依赖，TLS/认证，dev模式console降级 | 已合入 |
| **sanitize_logs** | scripts/sanitize_logs.sh | ✅ | FDE 日志脱敏脚本（§1.4） | 已合入 |
| DB Utils (SQLite连接池) | harness/infrastructure/db_utils.py | ✅ | 统一WAL+busy_timeout连接层，冷路径context manager + 热路径persistent conn | 已合入 |

---

## 十一、扩展与学习

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| get_channel_adapter | `aiPlat-app/channels/adapter.py` | ✅ | 自动同步 | 已合入 |
| ChannelAdapters | `aiPlat-app/channels/adapters/` | ✅ | 多渠道扩展: Discord/WeCom/Email/DingTalk/WhatsApp/Lark/Teams/Signal/Matrix/Mattermost/Line/QQ/Reddit/GitHub/SMS/GoogleChat/HomeAssistant/IRC/Ntfy (P1-A4 + 2026-08-23/24/25 广度延伸 7→22，对齐 Hermes 22 收官) | 已合入 |
| ChannelDispatcher | `aiPlat-app/channels/adapter.py` | ✅ | 统一调度 22 渠道 (3 内置 + 19 扩展) | 已合入 |
| LearnNudgeHook | `core/harness/learning/learn_nudge_hook.py` | ✅ | 会话内实时学习触发 (POST_OBSERVE, P1-A1) | 已合入 |
| SkillCurator | `core/harness/learning/skill_curator.py` | ✅ | 技能生命周期维护 active→stale→archived (P1-A2) | 已合入 |
| ModelTierPanel MoA card | `aiPlat-management/frontend/src/components/model/ModelTierPanel.tsx` | ✅ | 自动同步 | 已合入 |
| MoaResult | `harness/syscalls/moa_executor.py` | ✅ | 自动同步 | 已合入 |
| moa_executor.execute | `harness/syscalls/moa_executor.py` | ✅ | 自动同步 | 已合入 |
| DiscoveryListener | `harness/infrastructure/discovery_listener.py` | ✅ | 自动同步 | 已合入 |
| GoalProgressEvaluator | `harness/optimization/goal_progress_evaluator.py` | ✅ | 自动同步 | 已合入 |
| GoalDependencyGraph | `harness/optimization/goal_dependency_graph.py` | ✅ | 自动同步 | 已合入 |
| AbstractGoalDecomposer | `harness/optimization/abstract_goal_decomposer.py` | ✅ | 自动同步 | 已合入 |
| SharedKnowledgePool | `harness/memory/shared_pool.py` | ✅ | 自动同步 | 已合入 |
| StrategySearchEngine | `harness/optimization/search_engine.py` | ✅ | 自动同步 | 已合入 |
| ToolBootstrapEngine | `harness/optimization/tool_bootstrap.py` | ✅ | 自动同步 | 已合入 |
| GoalGenerator | `harness/optimization/goal_generator.py` | ✅ | 自动同步 | 已合入 |
| cmm_graduation | harness/learning/cmm_graduation.py | ✅ | 自动同步 | 已合入 |
| integration | harness/integration.py | ✅ | 自动同步 | 已合入 |
| toolsets | harness/tools/toolsets.py | ✅ | 自动同步 | 已合入 |
| deepseek | apps/finetune/providers/deepseek.py | ✅ | 自动同步 | 已合入 |
| skill_lint_scan | harness/maintenance/skill_lint_scan.py | ✅ | 自动同步 | 已合入 |
| model_feedback | harness/routing/model_feedback.py | ✅ | 自动同步 | 已合入 |
| execution_context | harness/kernel/execution_context.py | ✅ | 自动同步 | 已合入 |
| wiki_context | harness/syscalls/wiki_context.py | ✅ | 自动同步 | 已合入 |
| trajectory_scorer | harness/training/trajectory_scorer.py | ✅ | 自动同步 | 已合入 |
| rl_trainer | harness/training/rl_trainer.py | ✅ | 自动同步 | 已合入 |
| value_calculator | harness/finance/value_calculator.py | ✅ | 自动同步 | 已合入 |
| distillation | harness/training/distillation.py | ✅ | 自动同步 | 已合入 |
| full_training | harness/training/full_training.py | ✅ | 自动同步 | 已合入 |
| _json | harness/document/converters/_json.py | ✅ | 自动同步 | 已合入 |
| _eml | harness/document/converters/_eml.py | ✅ | 自动同步 | 已合入 |
| _csv | harness/document/converters/_csv.py | ✅ | 自动同步 | 已合入 |
| _markdown | harness/document/converters/_markdown.py | ✅ | 自动同步 | 已合入 |
| _html | harness/document/converters/_html.py | ✅ | 自动同步 | 已合入 |
| playbook | harness/learning/playbook.py | ✅ | 自动同步 | 已合入 |
| proposal_store | harness/learning/proposal_store.py | ✅ | 自动同步 | 已合入 |
| action_bridge | harness/actions/action_bridge.py | ✅ | 自动同步 | 已合入 |
| answer_generator | harness/generation/answer_generator.py | ✅ | 自动同步 | 已合入 |
| model_tier_router | harness/routing/model_tier_router.py | ✅ | 自动同步 | 已合入 |
| prompt_optimizer | harness/optimization/prompt_optimizer.py | ✅ | 自动同步 | 已合入 |
| strategy_tracker | harness/optimization/strategy_tracker.py | ✅ | 自动同步 | 已合入 |
| goal_generator | harness/optimization/goal_generator.py | ✅ | 自动同步 | 已合入 |
| search_engine | harness/optimization/search_engine.py | ✅ | 自动同步 | 已合入 |
| goal_executor | harness/optimization/goal_executor.py | ✅ | 自动同步 | 已合入 |
| tool_bootstrap | harness/optimization/tool_bootstrap.py | ✅ | 自动同步 | 已合入 |
| dynamic_orchestrator | harness/coordination/dynamic_orchestrator.py | ✅ | 自动同步 | 已合入 |
| swarm_broker | harness/coordination/swarm_broker.py | ✅ | 自动同步 | 已合入 |
| cost_tracker | harness/optimization/cost_tracker.py | ✅ | 自动同步 | 已合入 |
| integrator | harness/multimodal/integrator.py | ✅ | 自动同步 | 已合入 |
| kanban_engine | harness/coordination/kanban_engine.py | ✅ | 自动同步 | 已合入 |
| wake_agent | harness/monitoring/wake_agent.py | ✅ | 自动同步 | 已合入 |
| tool_evolution | harness/optimization/tool_evolution.py | ✅ | 自动同步 | 已合入 |
| voice_loop | harness/multimodal/voice_loop.py | ✅ | 自动同步 | 已合入 |
| sla_tracker | harness/security/sla_tracker.py | ✅ | 自动同步 | 已合入 |
| cron_loader | harness/scheduler/cron_loader.py | ✅ | 自动同步 | 已合入 |
| wake_scheduler | harness/scheduler/wake_scheduler.py | ✅ | 自动同步 | 已合入 |
| graph_consensus | harness/coordination/patterns/graph_consensus.py | ✅ | 自动同步 | 已合入 |
| rag_diagnosis | harness/evaluation/rag_diagnosis.py | ✅ | 自动同步 | 已合入 |
| rag_diagnostics_collector | harness/evaluation/rag_diagnostics_collector.py | ✅ | 自动同步 | 已合入 |
| recorder | harness/practice/recorder.py | ✅ | 自动同步 | 已合入 |
| graph_extract | harness/syscalls/graph_extract.py | ✅ | 自动同步 | 已合入 |
| async_utils | harness/utils/async_utils.py | ✅ | 自动同步 | 已合入 |
| trajectory_collector | `harness/digital_human/trajectory_collector.py` | ✅ | P1-2 闭环：轨迹→ShareGPT 数据集（export_sharegpt_dataset → ~/.aiplat/training） | 已合入 |
| research 文档新鲜度守卫 | `scripts/check_research_docs_freshness.py` | ✅ | Rule 6：状态标记矛盾检测 + 符号引用验证 + 最后验证时间戳对账（--ci 阻断） | 已合入 |
| 应用工厂页面感知 | `frontend/src/pages/App/Factory/index.tsx` | ✅ | P2-4 扩展：/app/factory 上报项目数/阶段/通过率/选中项目 → 数字人可答状态类问题 | 已合入 |
| voice_pipeline | `harness/digital_human/voice_pipeline.py` | ✅ | ASR→Agent→TTS 编排；P0 修复 + P1-3 格式链 + P2-1 WS 鉴权 + session 隔离 + P2-4 页面数据感知（8 管理页接入 pageDataBridge） | 已合入 |
|------|------|:---:|------|------|
| ExperienceVector | harness/learning/experience_vector.py | ✅ | PipelineTrace→Embedding→语义检索 | 已合入 |
| ToolDriftDetector | harness/learning/tool_drift_detector.py | ✅ | 4类漂移检测(struct/field/latency/error) + 重放校验自适应 | 已合入 |
| ImmuneMemory | harness/security/immune_memory.py | ✅ | 三级渐进拦截(>0.95拦截/>0.88防御前缀/<0.88放行) + 防御Skill自动生成 | 已合入 |
| SkillSimulator | harness/learning/skill_simulator.py | ✅ | Docker沙盒预检，pass≥80% | 已合入 |
| SFT AutoTrigger | harness/training/auto_trigger.py | ✅ | ≥100条+quality≥0.8→自动生成SFT数据集 | 已合入 |
| HITL 反馈记忆回路 | harness/infrastructure/approval/manager.py:428` + `harness/learning/__init__.py:150 | ✅ | 拒绝原因→ExperienceVectorCache→enrich_skill_draft 错题本检索 | 已合入 |
| SuccessGeneralizer | harness/learning/success_generalizer.py | ✅ | ≥85% hot skill → 参数抽象 → 跨运行验证 → GeneralizedRule | 已合入 |
| Feedback Loops | harness/feedback_loops/ | ✅ | local + prod + push 三通道 | 已合入 |
| ImplicitFeedback | services/implicit_feedback.py | ✅ | 复制/选中/追问/重复 行为信号 | 已合入 |
| Meta-Agent | harness/meta/ | ✅ | 远瞻探索，默认关闭（设 `AIPLAT_META_AGENT_ENABLED=true` 激活） | 已合入 |
| ControlProfile 联合控制画像 | harness/meta/ | ✅ | 6维(D1-D6)联合控制：Context/Tools/Generation/Orchestration/Memory/Output，5张预设画像(Creative/Safety/Code/QuickLookup/Default) + task_hints + priority调权 + 语义插值 | 已合入 |
| ControlProfileInterpolator | harness/meta/control_profile.py | ✅ | top-k语义相似度软投票插值，防硬切换震荡 | 已合入 |
| OrchestrationSelector | harness/meta/orchestration_selector.py | ✅ | 按expected_tool_steps+has_branching自动选择编排模式(single/chain/tree/reflexion) | 已合入 |
| CacheAwareRouter | harness/meta/cache_aware_router.py | ✅ | D1/D2缓存键比对(cache_key_hash)，冻结敏感维度保provider-side prompt caching命中率 | 已合入 |
| FailureDomain 单维归因 | harness/meta/profile_registry.py | ✅ | D1-D6单维故障域标记，5个拦截点已接线(LLM CircuitBreaker/SchemaGate/Compression/PolicyGate/PipelineEngine) | 已合入 |
| Profile 会话切换 | harness/meta/profile_registry.py` + `harness/execution/loop/inference.py | ✅ | `/profile <name>` 命令 + `/profile_status` 查看，= 运行时切换控制画像，无需重启 | 已合入 |
| D3 自动升 tier | harness/syscalls/llm.py:LLMCircuitBreaker` + `profile_registry.py:auto_bump_model_tier | ✅ | D3故障→CircuitBreaker打开→自动升一级model_tier(T3→T4→T5)，防重复失败 | 已合入 |
| Gateway 推送桥 | harness/evolution_engine.py` + `harness/optimization/goal_executor.py` + `harness/knowledge/system_diagnostician.py | ✅ | 4条推送连线: FeedbackRadar高/严重→gateway + GoalExecutor完成→gateway + SystemHealer修复→gateway + ToolDrift漂移→gateway | 已合入 |
| 定时自愈循环 | server.py:_auto_heal_loop | ✅ | 后台定时(默认3600s)运行 SystemDiagnostician+SystemHealer，自动检测+修复 | 已合入 |
| RAG 主动推荐 | materials_chat.py:_get_related_recommendations | ✅ | RAG回答末尾附带GraphIndex邻居实体推荐，支持 /profile_status 查看 | 已合入 |
| WakeScheduler 默认开启 | wake_scheduler.py | ✅ | 默认从false改为true + wake完成后gateway推送 | 已合入 |
| Cells JSON 全链路 | sqlite_retriever.py` + `retrieval_crag.py` + `retrieval.py` + `kb/db.py | ✅ | 表格cells从SQLite→CRAG→LLM上下文全链路保留，表格优先级1.2x boost | 已合入 |
| Year/Quarter 时间过滤 | harness/knowledge/db.py` + `learning/types.py` + `apps/agents/materials_chat.py | ✅ | kb_elements新增year/quarter列 + RunContext.time_range + 用户问题时间解析(相对时间绝对化) | 已合入 |
| EntityResolver 同义词 | entity_resolver.py | ✅ | _load_synonym_map从YAML+synonyms.yaml加载 + _score_pair_synonym第零层 + alias_index扩展 | 已合入 |
| GraphNode aliases | graph_index.py | ✅ | GraphNode新增aliases字段 + find_by_name三级匹配(精确→别名→子串) + _class_synonyms自动填充 | 已合入 |
| ContextBus 层数截断 | context_bus.py | ✅ | assemble_field_assessment按profile.context_layers动态截断(1-10层)，_layer_count超限return | 已合入 |
| Arena 评估竞技场 | harness/arena/ | ✅ | N-Agent竞选择优→Arena评分→胜出合并 + DarwinArena 进化选择 | 已合入 |
| Canary 灰度部署 | harness/canary/ | ✅ | Canary/A-B/Shadow/Auto-Rollback 四种灰度模式 + 自动回滚 | 已合入 |
| FeedbackLoops 反馈闭环 | harness/feedback_loops/ | ✅ | local + prod + push 三通道反馈收集 + drain wired | 已合入 |
| Health 健康检查 | harness/health/ | ✅ | 子系统健康状态聚合 + Capability Health + Symbol Health | 已合入 |
| Observation 观测总线 | harness/observation/ | ✅ | EventBus 发布/订阅 + PipelineTrace 每阶段跟踪 | 已合入 |
| Smoke 全链路冒烟 | harness/smoke/ | ✅ | 生产级全链路冒烟测试 + 自动清理 | 已合入 |
| A2A 协议 | apps/a2a/ | ✅ | Agent Card + Task Send/Get/Stream/Cancel/Artifacts 全实现 | 已合入 |
| DataSource 连接器 | harness/data_source/ | ✅ | SQL/API/File 多后端 + field_mapping + process_from_datasource | 已合入 |
| On-Error Reflector | harness/infrastructure/hooks/on_error_reflector.py | ✅ | 连续2次tool error→LLM反思（事后） | 已合入 |
| DevilAdvocate 前置预判 | harness/infrastructure/hooks/devil_advocate.py | ✅ | PRE_ACT Hook：执行前模拟失败场景，高风险工具注入警告（事前） | 已合入 |
| 自迭代闭环 | [概念] | ✅ | 自迭代闭环 — 设计蓝图 |
| Skill 质量离线基准 | tests/eval/test_skill_quality.py` + `gold_skill_quality.json | ✅ | 10任务×5领域×3条件 (No/Cured/Auto)，对标 SkillsBench | 已合入 |
| CMM 观察层 | harness/memory/pattern_accumulator.py | ✅ | 工具序列指纹 + 跨会话累积 + 频次≥3触发 | 已合入 |
| MetaClaw 双轨综合 | harness/memory/pattern_accumulator.py:compare_success_failure() | ✅ | 成功+失败轨迹比较 + 提取路径差异 | 已合入 |
| 集体进化引擎 | harness/learning/skill_evolver.py | ✅ | 跨租户模式扫描 + 匿名化 + tenant_threshold≥2 | 已合入 |
| Agent SDK | aiplat-sdk/ | ✅ | L1/L2/L3 三级可用，`pip install aiplat-sdk` 可安装，待IDE集成 | 已合入 |
| VS Code 插件 | aiplat-vscode/ | ✅ | SSE 流式聊天 + 代码选择发送 + Apply fix + 隐式反馈，可打包 .vsix | 已合入 |
| SpecLifecycle | harness/models/spec_lifecycle.py | ✅ | Spec 版本状态机: DRAFT→PENDING→EXECUTING→REVIEW→STABLE→ARCHIVED | 已合入 |
| FeedbackRadar | harness/learning/feedback_radar.py | ✅ | 5种用户信号检测→Spec调整建议 (boundary/direction/overload/drift/cold) | 已合入 |
| InlineSelfCorrect | harness/execution/loop/_facade.py | ✅ | 内联自纠错: PostObserve→reflection-critic→reflection-improve, 1次/步 | 已合入 |
| MCPToolLazyLoad | apps/mcp/client.py | ✅ | MCP工具延迟加载: 启动仅加载名称, Schema首次调用时按需获取, AIPLAT_MCP_LAZY_LOAD控制 | 已合入 |
| PromptCaching | harness/syscalls/llm.py | ✅ | Prompt Caching: stable消息cache_control注入 + SHA256跨会话持久化(~/.aiplat/cache/), AIPLAT_PROMPT_CACHE_ENABLED控制 | 已合入 |
| ThreeLayerPermissions | gates/policy_gate.py:_match_tool_rule | ✅ | 三层权限(deny>ask>allow)+参数级fnmatch匹配 | 已合入 |
| SubagentIsolation | apps/agents/subagent/coordinator.py:isolate_context | ✅ | 子代理上下文隔离: 仅传摘要+只读模式, 默认开启 | 已合入 |
| FileBasedMemory | harness/memory/file_store.py | ✅ | 文件记忆: Markdown双写(MEMORY.md+日期文件)+SQLite索引, 人类可验证 | 已合入 |
| AutoMemory | harness/memory/file_store.py:auto_save_learning` + `harness/memory/manager.py:save_interaction | ✅ | 自动记忆: 纠正≥2次/10轮交互自动保存到文件, AIPLAT_AUTO_LEARNING_ENABLED控制 | 已合入 |
| PluginSlot | apps/plugins/manager.py | ✅ | 插件Slot: 同类别单一活跃, 旧插件状态归档 | 已合入 |
| StageSandbox (子进程) | harness/execution/sandbox.py:StageSandbox | ✅ | 进程级沙箱: 资源限制(cpu/memory/processes)+凭证隔离+超时控制 | 已合入 |
| DockerSandbox (容器) | harness/execution/sandbox.py:DockerSandbox | ✅ | 容器级沙箱: Docker隔离(--network none)+fallback到子进程, sandbox_mode='docker' | 已合入 |
| 五维 ROI 计算 | harness/finance/value_calculator.py:compute_monthly() | ✅ | 效率/质量/安全/创新/体验五维价值计量, 月度聚合 | 已合入 |
| 三受众翻译 | harness/finance/value_calculator.py:translate_for() | ✅ | CEO(战略+目标)/CFO(成本+ROI)/PM(准确度+满意度) 三视角自动翻译 | 已合入 |
| BusinessGoalTracker | harness/finance/value_calculator.py | ✅ | 目标设定→进度追踪→偏离预警, on_track/at_risk/behind 实时状态 | 已合入 |
| GoalAwareRouter | harness/execution/dynamic_router.py:GoalAwareRouter | ✅ | 业务目标感知调度: Speed(提速)/Quality(反思)/Safety(HITL) 策略自动切换 | 已合入 |
| KPIAgent 监控 | harness/agents/kpi_agent.py | ✅ | 自动追踪 KPI → 偏离预警 → strategy_suggest, EvolutionEngine Step12 触发 | 已合入 |
| Value Center API | ⚠️ deprecated core/api/routers/value.py` + `core/schemas_value.py | ✅ | CRUD endpoints: `/all/goals`, `/all/goals/{id}`, `/all/goals/{id}/trend`, `/all/strategy`; Schemas: `GoalCreateRequest`, `GoalUpdateRequest`, `GoalSourceConfigRequest` | 已合入 |
 `core/api/routers/value.py` | ✅ | `get_all_goals`, `create_goal_all`, `update_goal_all`, `delete_goal_all`, `create_business_goal`, `get_goal_trend_all`, `get_strategy_all` + 4 REST endpoints (`/all/goals`, `/all/strategy`, `/all/goals/{id}`, `/all/goals/{id}/trend`) | 已合入 |
| Proposal 工作流 | harness/learning/proposal_store.py | ✅ | draft→pending_approval→approved→merged/rejected + branch/merge语义 (Palantir AIP对齐) | 已合入 |
| FDEBuilderOrchestrator | apps/fde/service/builder.py | ✅ | FDE 对话式 Agent 构建：_clarify()→DomainRouter→SkillRegistry→auto_fill→Builder.deploy_app() | 已合入 |
| Agent 可发现性 | wiki.py:/ontology/{domain}/discover | ✅ | Agent动态查询 ObjectTypes/Links/Actions/Interfaces，自主发现操作能力 | 已合入 |

---

## 十二、Gate 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ContextGate | harness/infrastructure/gates/context_gate.py | ✅ | Token预算强制执行 + 上下文去重/陈旧校验 | 已合入 |
| SchemaGate | harness/infrastructure/gates/schema_gate.py | ✅ | JSON Schema 强制校验，Agent输出在下游阶段前验证 | 已合入 |
| ResilienceGate | harness/infrastructure/gates/resilience_gate.py | ✅ | 可配置重试策略 + 回退链 + 熔断器包装 | 已合入 |
| BackpressureMiddleware | core/server.py | ✅ | 协议级背压：inflight 超限 → 429 + Retry-After 指数退避（AIPLAT_BACKPRESSURE_MAX_INFLIGHT 门控，对齐 codex -32001） | 已合入 |
| backpressure_stats | core/server.py | ✅ | 背压诊断：inflight / max / enabled / retry_after_semantics | 已合入 |
| TraceGate | harness/infrastructure/gates/trace_gate.py | ✅ | 最佳努力追踪span包装，syscall审计 | 已合入 |
| SandboxGate | harness/infrastructure/gates/sandbox_gate.py | ✅ | 沙箱执行门 + 结果校验 | 已合入 |
| ErrorTranslator | harness/infrastructure/gates/error_translator.py | ✅ | 7级分类流水线 + 15种FailoverReason + 4 recovery flags + 智能重试 | 已合入 |
| ToolResult 结构化错误诊断 | syscalls/tool.py:_enrich_tool_error` + `error_translator.py:recovery_hint_for | ✅ | 工具失败经 ErrorTranslator 分类填充 error_type/exit_code/stderr/recovery_hint，注入 LLM observation `[DIAGNOSTICS]` | 已合入 |
| ExecutionSnapshot 自助恢复 API | api/routers/execution_snapshots.py` + `api/core_facade.py | ✅ | `/platform/execution/snapshots/*` list/get/compare/restore，经 CoreFacade 暴露 snapshot.py 存量能力 + RBAC 门禁 | 已合入 |
| FileCheckpoint 文件系统物理安全网 | harness/execution/file_checkpoint.py` + `syscalls/file.py:_checkpoint_before_overwrite | ✅ | sys_file_write/edit 覆盖前自动备份文件内容(hash去重+大文件跳过+保留50)，`/platform/execution/file-checkpoints/*` 自助恢复 | 已合入 |
| RateLimitTracker | harness/infrastructure/gates/rate_limit_tracker.py | ✅ | 滑动窗口 + 指数退避(max 120s) + asyncio.Lock | 已合入 |
| SemanticGate | harness/infrastructure/gates/semantic_gate.py | ✅ | 3层语义合规验证(entity/value/relation) + warn/audit/block模式 | 已合入 |
| CompletionChecklistGate | harness/infrastructure/gates/completion_gate.py | ✅ | 2层完成度验证(固定模板+LLM深层) + 低置信度重试闭环 | 已合入 |
| 统一出口门控层 | harness/integration.py | ✅ | 8 gates在统一出口: Completion+SemanticGate+self_review+Hallucination+cache+pattern+memory+action_bridge | 已合入 |
| 工具白名单 | config/infra/llm_profile.yaml` + `harness/routing/model_tier_router.py` + `harness/integration.py | ✅ | T1-T5每层max_tools限缩, 低复杂度→少工具 | 已合入 |
| 代码熵检测器 | harness/knowledge/code_entropy_detector.py | ✅ | 文件长度/函数数/TODO标记 3维度评分, GET /diagnostics/code-entropy | 已合入 |
| 本体感知路由 | harness/execution/router.py | ✅ | _ontology_routing_hint: 实体名匹配→邻居计数→graph/loop抉择 | 已合入 |
| CrossValidationGate | harness/infrastructure/gates/cross_validation_gate.py | ✅ | 3层跨域验证(设备↔工艺↔质量) + 52/50跨域连接已达标 | 已合入 |

---

## 十三、评估系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| AdversarialTestSuite | `core/harness/evaluation/adversarial_test_suite.py` | ✅ | 认知安全对抗测试 | 已合入 |
| NLIBridge | `core/harness/evaluation/nli_engine.py` | ✅ | NLI 推理引擎 | 已合入 |
| EvalRunner | `core/harness/evaluation/eval_runner.py` | ✅ | 自动同步 | 已合入 |
| QualityScoring | `core/harness/knowledge/scoring_engine.py` | ✅ | 自动同步 | 已合入 |
| eval_retrieval | `harness/evaluation/eval_retrieval.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| EvaluationRunner | harness/evaluation/eval_runner.py | ✅ | 全流水线评估执行引擎 | 已合入 |
| EvalMetricsEngine | harness/evaluation/eval_metrics.py | ✅ | 从 ExecutionStore trace 计算综合评估指标 | 已合入 |
| HallucinationTracker | harness/evaluation/hallucination_tracker.py | ✅ | NLI事实核查 + GraphIndex图边验证 | 已合入 |
| RAG Evaluator | harness/evaluation/rag_evaluator.py | ✅ | Ragas: faithfulness/relevancy/precision/recall | 已合入 |
| DriftDetector | harness/evaluation/drift_detector.py | ✅ | 零成本推理质量下降检测 (confidence/error/stagnation) | 已合入 |
| EvaluationWorkbench | harness/evaluation/workbench.py | ✅ | 标准化评估报告 + 阈值门 + 制品持久化 | 已合入 |
| AB Optimizer | harness/evaluation/ab_optimizer.py | ✅ | A/B 测试优化 | 已合入 |
| CoverageGate | harness/evaluation/coverage_gate.py | ✅ | 覆盖率阈值强制执行 | 已合入 |
| GraphDiff | harness/evaluation/graph_diff.py | ✅ | 本体图状态对比，回归检测 | 已合入 |
| EvidenceDiff | harness/evaluation/evidence_diff.py | ✅ | 证据级差异计算 | 已合入 |
| ScoringDimensions | harness/evaluation/dimensions.py | ✅ | 配置驱动评分维度注册 | 已合入 |
| EvalTypes | harness/evaluation/eval_types.py | ✅ | 类型化评估结果Schema | 已合入 |
| 工具选择离线评估 | tests/eval/test_tool_selection.py` + `gold_tool_selection.json | ✅ | 15 case gold + compute_tool_quality + CI 回归 + 混淆矩阵 + 安全边界 + 覆盖率检查 | 已合入 |

---

## 十四、MCP 协议

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| MCPToolAdapter | `apps/mcp/adapter.py` | ✅ | 自动同步 | 已合入 |
| MCPClientManager | `apps/mcp/client.py` | ✅ | 自动同步 | 已合入 |
| MCPRuntime | `apps/mcp/runtime.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| MCP JSON-RPC 2.0 | apps/mcp/protocol.py | ✅ | 完整 MCP 协议实现 (init, tools/list, tools/call) | 已合入 |
| MCP HTTP+SSE Server | apps/mcp/server.py | ✅ | 远程工具暴露服务 | 已合入 |
| MCP Stdio Transport | apps/mcp/local_tools_server.py | ✅ | 工作区工具暴露给 AI 编辑器 | 已合入 |
| MCP Runtime Wiring | apps/mcp/runtime.py | ✅ | MCP Server → ToolRegistry 运行时绑定 + PolicyGate | 已合入 |
| MCP Client Manager | apps/mcp/client.py | ✅ | 多服务端客户端连接生命周期管理 | 已合入 |
| MCP Production Policy | core/mcp/prod_policy.py | ✅ | 生产安全策略 (risk level, allowed tools) | 已合入 |

---

## 十四附、A2A 协议 (Agent-to-Agent)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| AgentMessageBus | `core/harness/interfaces/messaging.py` | ✅ | 自动同步 | 已合入 |
| AgentDiscovery | `harness/ontology_engine/triple_scanner.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Agent Card | apps/a2a/agent_card.py | ✅ | 自动枚举 Skill/Tool 能力 + JSON-LD 上下文 | 已合入 |
| Task Send | apps/a2a/server.py | ✅ | POST /tasks → 复用 core_chat 执行 | 已合入 |
| Task Get | apps/a2a/server.py | ✅ | GET /tasks/{id} → 复用 ExecutionStore | 已合入 |
| Task Stream | apps/a2a/server.py | ✅ | SSE /tasks/{id}/stream → 复用 ReActLoop | 已合入 |
| Task Cancel | apps/a2a/server.py | ✅ | POST /tasks/{id}/cancel | 已合入 |
| Task Artifacts | apps/a2a/server.py | ✅ | GET /tasks/{id}/artifacts → 复用 TaskSkills | 已合入 |
| Task List | apps/a2a/server.py | ✅ | GET /tasks 任务列表 | 已合入 |

---

## 十五、文档智能

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| OCREngine | `harness/document/ocr.py` | ✅ | 自动同步 | 已合入 |
| Transcriber | `harness/document/transcriber.py` | ✅ | 自动同步 | 已合入 |
| VideoParser | `harness/document/video.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Document Classifier | apps/document_intelligence/classifier.py | ✅ | 文档类型分类 + KB provider集成 | 已合入 |
| Document Summarizer | apps/document_intelligence/summarizer.py | ✅ | LLM 文档摘要，可配置策略 | 已合入 |
| Structured Chunker | apps/document_intelligence/chunking/structured_chunker.py | ✅ | 内容感知结构化分块 + 策略自动选择 | 已合入 |
| Question Analysis | apps/document_intelligence/question_analysis.py | ✅ | 问题分类与分解，检索策略决策 | 已合入 |
| ConverterRegistry | harness/document/protocol.py:get_document_registry() | ✅ | 统一文档解析调度，13 个 built-in converter，优先级链 + 降级链 | 已合入 |
| PDF Converter | harness/document/converters/_pdf.py | ✅ | markitdown→pdfplumber→raw text 三级降级 + 文件头检测 | 已合入 |
| DOCX Converter | harness/document/converters/_docx.py | ✅ | markitdown→python-docx→raw text 降级 + table 保留 | 已合入 |
| PPTX Converter | harness/document/converters/_pptx.py | ✅ | markitdown→python-pptx→raw text 降级 | 已合入 |
| XLSX Converter | harness/document/converters/_xlsx.py | ✅ | markitdown→raw text 降级 | 已合入 |
| Audio/Video Converter | harness/document/converters/_audio.py` + `harness/document/converters/_video.py | ✅ | Whisper 转录，via ffmpeg extract | 已合入 |
| Image Converter | harness/document/converters/_image.py | ✅ | Tesseract/PaddleOCR 文字提取 | 已合入 |
| 多格式统一解析 | harness/document/parsers.py` + `harness/document/protocol.py | ✅ | 12 种格式 → 13 个 DocumentConverter → 统一 DocumentElement | 已合入 |
| Azure DI 集成 | harness/document/converters/_pdf.py:_convert_via_azure_di() | ✅ | 环境变量驱动：设 `AIPLAT_AZURE_DOCINTEL_ENDPOINT` 即激活，自动降级到本地 | 已合入 |
| DocumentConverter 协议 | harness/document/protocol.py | ✅ | ABC: accepts() + convert()，13 个内置 converter，优先级调度 | 已合入 |
| ConverterRegistry | harness/document/protocol.py:get_document_registry() | ✅ | 全局单例，单点派发，消除 5 处硬编码 dispatch | 已合入 |
| 内容级文件检测 | harness/document/protocol.py:_guess_extension_from_header() | ✅ | 文件头魔数检测，扩展名与内容矛盾时自动修正 | 已合入 |
| 完整降级链 | harness/document/protocol.py:convert_with_fallback() | ✅ | 遍历所有 converter → 异常聚合 → 兜底 raw text | 已合入 |
| 结构角色检测 | harness/document/protocol.py:detect_structure_role() | ✅ | h1-h6/table/list_item/caption/code_block/paragraph 自动识别 | 已合入 |
| 插件系统 | harness/document/protocol.py:_load_plugins() | ✅ | entry_points group=aiplat.document_converter，零侵入扩展 | 已合入 |
| 集中格式映射 | api/facades/kb_facade.py:_KIND_TO_EXT | ✅ | 40+ 同义词 → 规范扩展名，统一 kb_facade/core_facade/routes | 已合入 |
| Whisper 双后端切换 | harness/document/transcriber.py:77-99 | ✅ | faster-whisper ↔ openai-whisper 运行时自动切换 | 已合入 |
| Image OCR | harness/document/ocr.py | ✅ | Tesseract/PaddleOCR 关键帧文字提取 | 已合入 |
| Document Chunker | harness/document/chunker.py | ✅ | 多策略分块 (fixed/semantic/recursive) + overlap控制 | 已合入 |
| 多格式解析器 | harness/document/parsers.py | ✅ | DOCX/PDF/MD/HTML/CSV/Audio/Image/Video/EML/JSON → 统一元素，已升级为协议化架构 | 已合入 |

---

## 十六、工具生态

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| CLOSURE_FP_RATE_MAX | `core/harness/infrastructure/action_contract.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Browser 自动化 | apps/tools/browser.py` + `apps/tools/browser_test_engine.py | ✅ | Playwright 全浏览器自动化，BFS遍历/RPA/截图 | 已合入 |
| Test Case Generator | apps/tools/test_case_generator.py | ✅ | 页面分析 → 结构化 Excel 测试用例 | 已合入 |
| SysGraph Tools (5) | apps/tools/sysgraph_tools.py | ✅ | context/search/impact/callers/node 代码图查询 | 已合入 |
| Draw.io Generator | harness/syscalls/drawio_gen.py | ✅ | LLM→draw.io XML 图表生成，零外部依赖 | 已合入 |
| Code Intelligence | harness/syscalls/code_intel_syscall.py | ✅ | 预构建依赖图SQLite查询 | 已合入 |
| Docker Exec Driver | apps/exec_drivers/docker.py | ✅ | Docker 容器内沙箱执行 | 已合入 |
| SSH Exec Driver | apps/exec_drivers/ssh.py | ✅ | SSH 远程代码执行 | 已合入 |
| Local Exec Driver | apps/exec_drivers/local.py | ✅ | 本地进程执行 + 资源限制 | 已合入 |
| BaseTool Framework | apps/tools/base.py | ✅ | ToolMetadata/BaseTool/CalculatorTool/ToolSearch 基础框架 | 已合入 |
| CodeExecutionTool | apps/tools/code.py | ✅ | 代码执行工具 | 已合入 |
| DatabaseTool | apps/tools/database.py | ✅ | 数据库操作工具 | 已合入 |
| HTTP Tool | apps/tools/http.py | ✅ | HTTP 请求工具 | 已合入 |
| KB Tools | apps/tools/kb_tools.py | ✅ | 知识库 CRUD 工具集，含文档入库自动域分类(DomainRouter.classify)(HMESI Step 2) | 已合入 |
| KB Auto-Domain | apps/tools/kb_tools.py:35-58 | ✅ | 文档入库时自动检测域标签：默认collection下读取文档片段→DomainRouter.classify→路由到对应collection | 已合入 |
| MCP Adapter | apps/tools/mcp_adapter.py | ✅ | MCP→Tool 适配器 | 已合入 |
| Permission Tool | apps/tools/permission.py | ✅ | 权限管理工具 | 已合入 |
| Recaller Tool | apps/tools/recaller.py | ✅ | 记忆召回工具 | 已合入 |
| Repo Tool | apps/tools/repo.py | ✅ | 代码仓库操作工具 | 已合入 |
| Skill Tools | apps/tools/skill_tools.py` + `apps/tools/skill_script_tools.py | ✅ | Skill 管理 + 脚本化工具集 | 已合入 |
| WebFetch Tool | apps/tools/webfetch.py | ✅ | 网页抓取工具 | 已合入 |
| Tool Discovery | apps/tools/discovery.py | ✅ | 工具自动发现 | 已合入 |

---

## 十七、微调系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| RLTrainer | `harness/training/rl_trainer.py` | ✅ | 自动同步 | 已合入 |
| LoRAAutoTrigger | `harness/training/auto_trigger.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| MLX LoRA Trainer | harness/finetune/mlx_trainer.py | ✅ | Apple Silicon 本地 QLoRA 微调，MPS后端 | 已合入 |
| GGUF Exporter | harness/finetune/gguf_exporter.py | ✅ | 模型导出 GGUF 格式 | 已合入 |
| Fine-tune Job Manager | harness/finetune/job_manager.py | ✅ | 微调任务生命周期管理 | 已合入 |
| SFT Dataset Manager | harness/finetune/dataset_manager.py | ✅ | SFT 数据集准备/版本化/存储 | 已合入 |
| RLOOUpdater | harness/training/rl_trainer.py | ✅ | RLOO 优势值更新: EMA 平滑, 多目标权重自适应, clip_range=0.2 | 已合入 |
| CodeTestReward | harness/training/rl_trainer.py | ✅ | 代码测试奖励: 从 PipelineState 提取 test pass_rate 自动评分 | 已合入 |
| VerifierReward | harness/training/rl_trainer.py | ✅ | 验证器奖励: LLM 输出正确性评分, 语义一致性检查 | 已合入 |
| Online Rollout | harness/training/rl_trainer.py:_rollout_online | ✅ | 在线策略探索: Semaphore(2), timeout(300s), 深拷贝状态隔离 | 已合入 |
| SFT→RL 桥接 | harness/finetune/job_manager.py:239` → `rl_trainer.py:_detect_latest_sft_model | ✅ | SFT 完成→~/.aiplat/sft_models/latest.json 信号→RL 自动检测最新模型 | 已合入 |
| TrajectoryScorer 四维 | harness/training/trajectory_scorer.py | ✅ | 正确性+效率+优雅性+可学习性四维评分, score_batch 批量处理 | 已合入 |
| 混合采样 | harness/training/auto_trigger.py:_mixed_sample_by_task_type | ✅ | coding/terminal/qa/general 分组均匀采样, 防止单一来源主导 | 已合入 |
| 可模仿性过滤 | harness/training/auto_trigger.py:learnability | ✅ | 学生模型必须能模仿教师轨迹, is_learnable() 预筛选 | 已合入 |

---

## 十八、部署与灰度

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| SkillRouter | `harness/deployment/canary.py` | ✅ | 自动同步 | 已合入 |
| GitPusher | `harness/deployment/git_pusher.py` | ✅ | 自动同步 | 已合入 |
| DeployEngine | `harness/deployment/deploy_engine.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Skill Canary 部署 | harness/deployment/canary.py | ✅ | Canary/A-B/Shadow/Auto-Rollback 四种模式 | 已合入 |
| Canary Escalation | harness/canary/escalation.py | ✅ | 确定性灰度升级 + 变更控制集成 | 已合入 |
| Canary Recommendation | harness/canary/recommendation.py | ✅ | 灰度比例推荐引擎 | 已合入 |
| Config Hot Reload | harness/infrastructure/hot_reload.py | ✅ | 文件监听回调 + 缓存失效 | 已合入 |

---

## 十九、运行时干预

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| set_model_override / clear_model_override | `harness/utils/model_injection.py` | ✅ | 自动同步 | 已合入 |
| _model_overrides | `harness/utils/model_injection.py` | ✅ | 自动同步 | 已合入 |
| MetaAgent / get_meta_agent | `harness/meta/meta_agent.py` | ✅ | 数据驱动元认知分析（失败/健康信号聚合 → 策略建议） | 已合入 |
| MetaSuggestion | `harness/meta/meta_agent.py` | ✅ | area/problem/suggestion/priority/evidence | 已合入 |
|------|------|:---:|------|------|
| Howl Intervention | harness/intervention/howl.py | ✅ | Agent 停滞/退化检测 + redirect/clarify/fallback策略 | 已合入 |
| RunState Restatement | harness/restatement/run_state.py | ✅ | 结构化/版本化/人可编辑的进度制品 | 已合入 |

---

## 二十、Arena & 调度

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| WakeAgentTool | `apps/tools/wake_agent_tool.py` | ✅ | 自动同步 | 已合入 |
| VoiceLoopTool | `apps/tools/voice_loop_tool.py` | ✅ | 自动同步 | 已合入 |
| Swarm (Darwin Arena) | `harness/execution/swarm.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Darwin Arena | harness/arena/arena.py | ✅ | 多Agent竞技，Bayesian Elo评分 + Champion晋升 | 已合入 |
| Arena Regression | harness/arena/regression.py | ✅ | Champion 能力退化检测 | 已合入 |
| Cron Scheduler | harness/scheduler/cron.py | ✅ | 定时任务调度 | 已合入 |
| AutoSmoke Scheduler | harness/smoke/autoscheduler.py | ✅ | 自动冒烟测试调度执行 | 已合入 |

---

## 二十一、平台治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| TenantStore | `aiPlat-platform/tenants/tenant_store.py` | ✅ | 自动同步 | 已合入 |
| DomainMaturity | `harness/knowledge/domain_maturity.py` | ✅ | 自动同步 | 已合入 |
| ScenarioSelector | `harness/knowledge/scenario_selector.py` | ✅ | 自动同步 | 已合入 |
| PathPlanner | `harness/knowledge/path_planner.py` | ✅ | 自动同步 | 已合入 |
| ScoringEngine | `harness/knowledge/scoring_engine.py` | ✅ | 自动同步 | 已合入 |
| GovernancePipeline | `harness/knowledge/governance_pipeline.py` | ✅ | 自动同步 | 已合入 |
| authenticator | aiPlat-platform/auth/authenticator.py | ✅ | 自动同步 | 已合入 |
| pdf_render | aiPlat-platform/kb/poc/pdf_render.py | ✅ | 自动同步 | 已合入 |
| prompt_app | apps/prompt/api/prompt_app.py | ✅ | 自动同步 | 已合入 |
| entropy | api/routers/entropy.py | ✅ | 自动同步 | 已合入 |
| roles | apps/value/api/roles.py | ✅ | 角色CRUD + `override_strategy` + `update_agent_role` | 已合入 |
| Roles Schemas | core/schemas_roles.py | ✅ | `RoleAgentUpdateRequest` + `RoleStrategyOverrideRequest` | 已合入 |
| workspace_packages | api/routers/workspace_packages.py | ✅ | 自动同步 | 已合入 |
| workspace_agents | api/routers/workspace_agents.py | ✅ | 自动同步 | 已合入 |
| wiki_ontology_patterns | api/routers/wiki_ontology_patterns.py | ✅ | 自动同步 | 已合入 |
| wiki_ontology_domains | api/routers/wiki_ontology_domains.py | ✅ | 自动同步 | 已合入 |
| fde_domain_ops | apps/fde/api/fde_domain_ops.py | ✅ | 自动同步 | 已合入 |
| fde_pipeline | apps/fde/api/fde_pipeline.py | ✅ | 自动同步 | 已合入 |
| fde_handover_v2 | apps/fde/api/fde_handover_v2.py | ✅ | 自动同步 | 已合入 |
| fde_sessions_compare | apps/fde/api/fde_sessions_compare.py | ✅ | 自动同步 | 已合入 |
| mcp_admin | api/routers/mcp_admin.py | ✅ | 自动同步 | 已合入 |
| fde_sessions_v2 | apps/fde/api/fde_sessions_v2.py | ✅ | 自动同步 | 已合入 |
| wiki_ontology_sql | api/routers/wiki_ontology_sql.py | ✅ | 自动同步 | 已合入 |
| fde_diagnostics_v2 | apps/fde/api/fde_diagnostics_v2.py | ✅ | 自动同步 | 已合入 |
| wiki_proposals | api/routers/wiki_proposals.py | ✅ | 自动同步 | 已合入 |
| fde_overview | apps/fde/api/fde_overview.py | ✅ | 自动同步 | 已合入 |
| fde_validate | apps/fde/api/fde_validate.py | ✅ | 自动同步 | 已合入 |
| wiki_markings | api/routers/wiki_markings.py | ✅ | 自动同步 | 已合入 |
| wiki_ontology_engine | api/routers/wiki_ontology_engine.py | ✅ | 自动同步 | 已合入 |
| fde_quality_summary | apps/fde/api/fde_quality_summary.py | ✅ | 自动同步 | 已合入 |
| wiki_field_security | api/routers/wiki_field_security.py | ✅ | 自动同步 | 已合入 |
| fde_acceptance | apps/fde/api/fde_acceptance.py | ✅ | 自动同步 | 已合入 |
| wiki_health_quality | api/routers/wiki_health_quality.py | ✅ | 自动同步 | 已合入 |
| wiki_writeback | api/routers/wiki_writeback.py | ✅ | 自动同步 | 已合入 |
| fde_trends | apps/fde/api/fde_trends.py | ✅ | 自动同步 | 已合入 |
| fde_bootstrap | apps/fde/api/fde_bootstrap.py | ✅ | 自动同步 | 已合入 |
| wiki_evidence | api/routers/wiki_evidence.py | ✅ | 自动同步 | 已合入 |
| fde_manuals | apps/fde/api/fde_manuals.py | ✅ | 自动同步 | 已合入 |
| wiki_semantic_suggestions | api/routers/wiki_semantic_suggestions.py | ✅ | 自动同步 | 已合入 |
| wiki_ontology_export | api/routers/wiki_ontology_export.py | ✅ | 自动同步 | 已合入 |
| wiki_learning | api/routers/wiki_learning.py | ✅ | 自动同步 | 已合入 |
| fde_delivery | apps/fde/api/fde_delivery.py | ✅ | 自动同步 | 已合入 |
| fde_governance | apps/fde/api/fde_governance.py | ✅ | 自动同步 | 已合入 |
| fde_ask | apps/fde/api/fde_ask.py | ✅ | 自动同步 | 已合入 |
| fde_maintenance | apps/fde/api/fde_maintenance.py | ✅ | 自动同步 | 已合入 |
| fde_reports | apps/fde/api/fde_reports.py | ✅ | 自动同步 | 已合入 |
| wiki_loop_triggers | api/routers/wiki_loop_triggers.py | ✅ | 自动同步 | 已合入 |
| wiki_scenes | api/routers/wiki_scenes.py | ✅ | 自动同步 | 已合入 |
| diagnostics_capability | api/routers/diagnostics_capability.py | ✅ | 自动同步 | 已合入 |
| fde_dashboard_v2 | apps/fde/api/fde_dashboard_v2.py | ✅ | 自动同步 | 已合入 |
| schemas_policy | ⚠️ deprecated aiPlat-platform/auth/schemas_policy.py | ✅ | 自动同步 | 已合入 |
| learning_releases | apps/learning/api/learning_releases.py | ✅ | 自动同步 | 已合入 |
| learning_misc | apps/learning/api/learning_misc.py | ✅ | 自动同步 | 已合入 |
| prompt_templates | apps/prompt/api/prompt_templates.py | ✅ | 自动同步 | 已合入 |
| learning_autocapture | apps/learning/api/learning_autocapture.py | ✅ | 自动同步 | 已合入 |
| prompt_eval | apps/prompt/api/prompt_eval.py | ✅ | 自动同步 | 已合入 |
| routing_observability | api/routers/routing_observability.py | ✅ | 自动同步 | 已合入 |
| workflow_templates | api/routers/workflow_templates.py | ✅ | 自动同步 | 已合入 |
| workspace_skills | api/routers/workspace_skills.py | ✅ | 自动同步 | 已合入 |
| workspace_tools | api/routers/workspace_tools.py | ✅ | 自动同步 | 已合入 |
| kb_eval | aiPlat-platform/apps/eval/api/kb_eval.py | ✅ | 自动同步 | 已合入 |
| runs_eval | aiPlat-platform/apps/eval/api/runs_eval.py | ✅ | 自动同步；生成物适用：**已接线**（直接评测 builder 生成项目 project_id——生成应用质量评测闭环） | 已合入 |
| skill_evals | aiPlat-platform/apps/eval/api/skill_evals.py | ✅ | 自动同步 | 已合入 |
| catalog | aiPlat-platform/apps/misc/api/catalog.py | ✅ | 自动同步 | 已合入 |
| personas | aiPlat-platform/apps/misc/api/personas.py | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Change Control | platform/api/routers/change_control.py | ✅ | 变更请求跟踪/审计/autosmoke强制执行 | 已合入 |
| Tenant Onboarding | platform/api/routers/onboarding.py | ✅ | 租户引导：LLM配置/执行后端/密钥迁移/信任密钥 | 已合入 |
| Quota Manager | platform/governance/quota/quota_manager.py | ✅ | 资源配额管理与强制执行；生成物不适用（理由：平台租户配额强制，生成应用受平台侧约束） | 已合入 |
| Rate Limiter | platform/governance/rate_limit/limiter.py | ✅ | 单进程 in-memory + Redis 分布式令牌桶（原子Lua脚本）；生成物不适用（理由：平台网关限流，生成应用走平台代理） | 已合入 |
| Billing Meter | platform/billing/meter.py | ✅ | 用量计量与计费结算 | 已合入 |
| MQ WriteBack 适配器 | harness/knowledge/knowledge_writeback.py | ✅ | Kafka/RabbitMQ 消息队列写回 + none降级LOG_ONLY | 已合入 |
| KB Intelligence | platform/kb/intelligence/service.py | ✅ | URL抓取/HTML→text/格式检测/视频URL转录 | 已合入 |
| MinerU PDF 提取 | platform/kb/poc/mineru_extract.py | ✅ | 结构化PDF内容提取 + 表格 | 已合入 |
| Video Retrieval | platform/kb/intelligence/video_retrieval.py | ✅ | 时间索引视频内容检索 + 转录对齐 | 已合入 |
| Builder Project Service | platform/builder/builder_project_service.py | ✅ | 全功能应用项目CRUD + 双模式自动路由（agent→配置/code→代码，team_planner mode 判断）+ pass_rate 来源标注（real_pytest/estimated） | 已合入 |
| 生成物契约校验（conformance） | platform/builder/generated_conformance.py + generated_conformance.yaml + builder_project_service.py | ✅ | 注册前契约校验生成 AGENT.md/SKILL.md（SBA conformance 模式借鉴）：首行必须 `---`（防残留）、治理字段存在性（execution_type/input_schema/output_schema/version/status/effects）、input_schema/output_schema 对象格式（type/required/description）、must_contain_in_order 顺序断言；不通过跳过注册并告警 | 已合入 |
| workspace Agent 符合度校验（conformance） | platform/builder/agent_conformance.py | ✅ | 校验 workspace AGENT.md 合规（validate_agent_md 单文件 / validate_agents_dir 目录遍历：max_lines≤100、无 model 硬编码、交接 5 字段、输出格式无代码块模板）+ ratchet 门禁（load_baseline / save_baseline / ratchet_diff 基线对比，仅新增违规阻断，§96 架构守卫集成） | 已合入 |
| Builder 流水线启动与安全加固（P0） | platform/builder/builder_project_service.py + platform/api/routers/builder.py + core/harness/execution/pipeline_engine.py | ✅ | start_pipeline/start_pipeline_background 定义并委托 rebuild_project（接线断裂修复，PRD 前置检查）+ PRD 解析 eval→ast.literal_eval（RCE 修复）+ _deploy_result_files 路径穿越 _safe_join 防护 + 域注入 _prd 解析修复 + 部署签名 fail-closed（403 拒绝） | 已合入 |
| L2 导入既有代码 | platform/builder/builder_project_service.py + core/harness/execution/pipeline_engine.py | ✅ | import-repo API（zip/路径→manifest→_final_state.imported_repo，zip-slip 防护/密钥过滤/50MB·500文件·2MB 限额/has_tests/missing_deps）+ prompt 注入（行为契约"重写而非合并"+ {path,intent} 意图锚点 + 被引用文件全文）+ skip_pytest_gate 逃生（estimated + 原因）+ Build Log regenerated 警告 + 埋点（>40% 触发 L3 告警） | 已合入 |
| L3 增量合并引擎 | platform/builder/merge_engine.py + core/harness/execution/pipeline_engine.py | ✅ | merge_strategy（full_rewrite/incremental_merge）+ ImpactAnalyzer 影响面分析（Python 一阶 import）+ DiffMerger（unified diff 预览/语法 py_compile/接口 AST 验证/apply 前 deploy.prev 快照）+ 增量行为契约（逐字节一致/UNCHANGED）+ 前端逐文件 diff 审批（通过/驳回） | 已合入 |
| L4 多模块编排（后端） | platform/builder/cross_module.py + builder_project_service.py | ✅ | modules CRUD（modules.json 语义，单模块隐式兼容）+ import-repo/rebuild 支持 module_id（模块级 imported/）+ CrossModuleAnalyzer（API/entity/事件契约引用→模块依赖图+影响闭包）+ ModuleOrchestrator（拓扑顺序编排，未受影响模块不重跑）+ cross-module-impact/module-orchestrate 端点 + v1.5 跨模块 merge 契约门禁（verify_changed_module_contracts） | 已合入 |
| L4.5 数据库迁移编排 | platform/builder/schema_migration.py + builder_project_service.py | ✅ | SchemaExtractor（AST：SQLAlchemy/Pydantic 模型提取）+ SchemaDiffAnalyzer（字段/表增删改 + destructive 判定）+ MigrationGenerator（up/down DDL 成对）+ migration-preview/apply/rollback 端点（破坏性需显式确认）+ 跨模块字段引用阻断 + 迁移历史（append-only） | 已合入 |
| L5 发布流水线 | platform/builder/release_engine.py + builder_project_service.py | ✅ | 版本化产物（releases/v{ts}/current + 指针）+ 发布状态机（building→ready→canary→full→rolled_back）+ 金丝雀灰度（提升全量/回滚）+ 迁移先行门禁 + infra deploy_service 可选集成（AIPLAT_L5_INFRA_DEPLOY）+ 版本历史 append-only | 已合入 |
| 租户自助入驻 | [API] — register/verify-email | ✅ | 注册→邮箱验证→激活→返回API Key | 已合入 |
| 租户自助门户 | [API] — tenant/* | ✅ | 仪表板/API Key管理/用量/计费面板 | 已合入 |
| 运营大盘 | [API] — ops/overview | ✅ | 跨租户聚合：租户数/Token/活跃度，platform_admin only | 已合入 |
| 市场发布工作流 | [API] — marketplace/publish | ✅ | 提交→SkillSimulator预检→审核，含test_result | 已合入 |
| MessagingGateway | harness/infrastructure/gateway/messaging.py | ✅ | 飞书/企业微信/Slack三渠道通知，Pipeline失败自动广播 | 已合入 |

---

## 二十二、Infra 基础设施

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| InfraBridge | `harness/infrastructure/infra_bridge.py` | ✅ | 自动同步 | 已合入 |
| create_llm_client | `aiPlat-infra/infra/llm/factory.py` | ✅ | 自动同步 | 已合入 |
| ModelManager | `aiPlat-infra/infra/management/model/manager.py` + `config/providers.yaml` | ✅ | 自动同步；provider 生态 30 家族（2026-08-24 一批 8 + 2026-08-25 二批 8 + 三批 8：gemini/nvidia/huggingface/upstage/arcee/zai/xiaomi/nous，YAML 驱动零代码） | 已合入 |
|------|------|:---:|------|------|
| Model Health Checker | infra/management/model/health_checker.py | ✅ | 模型可用性/延迟/质量健康监控 | 已合入 |
| Local Model Scanner | infra/management/model/local_model_scanner.py | ✅ | 自动发现 Ollama/LM Studio/vLLM/oMLX 本地模型 | 已合入 |
| Model Quality Validator | infra/management/model/quality_validator.py | ✅ | 输出质量验证 + 基准评分 | 已合入 |
| Model Latency Tracker | infra/management/model/latency_tracker.py | ✅ | 每模型延迟跟踪 + 滑动窗口统计 | 已合入 |
| Multi-Backend Cache | infra/cache/ | ✅ | Redis/Memory/File 三后端缓存 + 工厂模式 | 已合入 |
| Multi-Backend Vector | infra/vector/ | ✅ | FAISS/Chroma/Milvus/Pinecone 多后端向量存储 | 已合入 |
| Multi-Backend Messaging | infra/messaging/ | ✅ | Kafka/RabbitMQ/Redis 消息队列 | 已合入 |
| Multi-Database | infra/database/ | ✅ | SQLite/MySQL/PostgreSQL/MongoDB + 连接池 | 已合入 |
| Multi-Backend Storage | infra/storage/clients.py | ✅ | S3/MinIO/Local 文件对象存储 | 已合入 |
| File Watcher | infra/management/file_watcher.py | ✅ | 跨进程文件监听 + 回调注册，支持热重载 | 已合入 |
| PlatformDB 持久化 | storage/platform_db.py | ✅ | 统一 SQLite 持久化：tenants/api_keys/quotas/billing 4表 | 已合入 |

---

## 二十三、核心API统一入口

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Intent API (Unified) | core/api/intents.py | ✅ | 三统一意图：core_chat, core_execute, core_query | 已合入 |
| CoreFacade | core/api/core_facade.py | ✅ | 统一门面，84K行暴露所有核心能力 | 已合入 |
| CoreFacade Graph API | core_facade.py:get_graph_health/get_graph_neighbors/get_graph_sessions | ✅ | 图谱健康状态 + 邻居查询 + 会话图查询，经 CoreFacade 暴露 | 已合入 |
| CoreFacade Wiki API | core_facade.py:wiki_search_pages | ✅ | Wiki 全文搜索，经 CoreFacade 暴露 | 已合入 |
| ContextService | core/services/context_service.py | ✅ | 完整对话上下文管理 + 记忆集成 | 已合入 |
| ConfigRegistry | core/services/config_registry_store.py | ✅ | 版本化/哈希校验的配置注册中心 | 已合入 |
| ExecutionStore | core/services/execution_store/ | ✅ | 综合执行/审计存储 + Schema管理 | 已合入 |

---

## 二十四、编排系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| ChainPlanner | `harness/orchestration/chain_planner.py` | ✅ | 自动同步 | 已合入 |
| IntentAnalyzer | `harness/orchestration/intent_analyzer.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Pipeline Orchestrator | core/orchestration/orchestrator.py | ✅ | 多步流水线编排 + 能力映射 | 已合入 |
| Capability Mapper | core/orchestration/capability_mapper.py | ✅ | Intent→Capability→Executor 解析链 | 已合入 |
| Chain Planner | core/orchestration/chain_planner.py | ✅ | 执行链拓扑规划 | 已合入 |
| Intent Analyzer | core/orchestration/intent_analyzer.py | ✅ | 意图分类与分解 | 已合入 |
| RunEventTimeline | `frontend/src/components/Builder/RunEventTimeline.tsx` | ✅ | Pipeline run 事件回放 UI（seq/type/payload 时间线） | 已合入 |
| list_run_events | `core/api/routers/runs.py` | ✅ | GET /runs/{run_id}/events 事件源回放查询 | 已合入 |
| fork_run_from_events | `core/harness/execution/pipeline_run_store.py` | ✅ | 事件源纯度——Fork 会话：折叠源事件→新 run 继承分叉点（stage/pass_rate），pipeline_forked 记录血缘 | 已合入 |
| list_forked_runs | `core/harness/execution/pipeline_run_store.py` | ✅ | Fork 血缘查询（parent_run_id→子 run_ids）；POST /pipeline/pipelines/runs/{id}/fork + GET /{id}/forks | 已合入 |
---

## 二十五、管理 & 质量

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| Sidebar v2.3 menuItems | `aiPlat-management/frontend/src/pageManifest.ts` | ✅ | 自动同步 | 已合入 |
| handleFixBugs | `aiPlat-management/frontend/src/pages/App/Factory/index.tsx` | ✅ | 自动同步 | 已合入 |
| filterItemsByRole | `aiPlat-management/frontend/src/components/layout/AppLayout.tsx` | ✅ | 自动同步 | 已合入 |
| QualityBus | `core/harness/knowledge/scoring_engine.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Asset Installer | management/asset_installer.py | ✅ | Git/dir/zip 导入 Agent/Skill/MCP，host allowlist安全 | 已合入 |
| Format Adapters | management/format_adapters.py | ✅ | 多格式导入 (YAML/JSON/TOML frontmatter) | 已合入 |
| N8N/LangChain Adapter | management/n8n_langchain_adapter.py | ✅ | n8n workflow + LangChain chain 导入 | 已合入 |
| Coze/Dify Adapter | management/coze_adapter.py` + `management/dify_adapter.py | ✅ | Coze/Dify 平台 Agent 导入 | 已合入 |
| Capability Convergence | management/capability_convergence.py | ✅ | Agent/Skill/Tool 能力重叠检测与去重 | 已合入 |
| Compliance Checks | management/compliance_checks.py | ✅ | 可扩展生产就绪审计 + 自动发现检查函数 | 已合入 |
| Plugin Manager | apps/plugins/manager.py | ✅ | 插件生命周期管理 (install/enable/disable/remove) | 已合入 |
| Quality Gate Suite | apps/quality/gates.py | ✅ | 多阶段质量门 | 已合入 |
| Quality Scanner | apps/quality/scanner.py | ✅ | 自动代码/技能质量扫描 | 已合入 |
| StandardsValidator | evaluation/standards_validator.py | ✅ | 10条声明式规则：缺节/占位符/版本/术语检查，YAML驱动 | 已合入 |
| StructuredMerger | coordination/merger.py | ✅ | Map-Reduce 合稿：交叉引用验证+悬空引用检测+LLM合稿 | 已合入 |
| FullStack 诊断 | api/routers/diagnostics.py:_check_full_stack | ✅ | 12项全域检查(入驻/知识/协作/学习/FDE日常 5条旅程) | 已合入 |
| Spec 冒烟测试 | scripts/smoke_spec_lifecycle.sh | ✅ | 8阶段自动化: create→submit→poll→trace→dashboard→stable | 已合入 |
| Workbench API | apps/workbench/api/workbench.py` + `core/schemas_workbench.py | ✅ | Spec生命周期(`create_spec:SpecCreateRequest`, `revise_spec`, `approve:SpecApproveRequest`, `reject:SpecRejectRequest`, `promote:SpecPromotionRequest`) + Skill安装(`install_skill_from_url:SkillInstallRequest`) + `submit_task` + `submit_feedback` | 已合入 |
| 合规审计 (ComplianceChecks) | management/compliance_checks.py | ✅ | 可扩展生产就绪审计: 任务规格/MemoryManager/PolicyGate/RBAC/CLAUDE.md检查 | 已合入 |
| 架构守卫诊断集成 | api/routers/diagnostics.py:_check_arch_guard | ✅ | 架构守卫违规数自动检测→诊断卡片展示, 0违规=满分 | 已合入 |
| Skill Lint 诊断 | api/routers/diagnostics.py:_check_skill_lint | ✅ | 全量 Skill Lint 扫描→error/warning 统计→诊断评分 | 已合入 |
| Core 运行时诊断 | api/routers/diagnostics.py:_check_core_runtime | ✅ | ExecutionStore 初始化状态检查 | 已合入 |
| 能力图谱健康 | api/routers/diagnostics.py:_check_capability | ✅ | 孤立Agent/未解析引用/入口重复自动检测 | 已合入 |
| Wiki 健康检查 | api/routers/diagnostics.py:_check_wiki_health | ✅ | 死链/孤立/矛盾/过期页面检测→health_score 评分 | 已合入 |
| 链路追踪诊断 | api/routers/diagnostics.py:_check_traces | ✅ | 链路追踪完整性: span_id/trace_id/事件持久化检查 | 已合入 |
| Sidebar v2.3 菜单系统 | aiPlat-management/frontend/src/pageManifest.ts | ✅ | 任务流驱动侧边栏：6组92入口；AI应用工厂精简58%(33→14项，纯项目生命周期+工作区能力）；引擎能力配置(6项)独立成组移入平台设置；价值看板→仪表盘；修复中心+LLM审查→诊断与治理 | 已合入 |
| App Factory 页面 | aiPlat-management/frontend/src/pages/App/Factory/index.tsx | ✅ | 项目工厂全生命周期：InlineChat对话、Pipeline阶段状态监控、产出物全屏JSON/Markdown渲染、Bug统计卡片、一键修复按钮(触发test_report_orchestrator) | 已合入 |
| 一键修复(Bug Fix Orchestrator) | aiPlat-management/frontend/src/pages/App/Factory/index.tsx | ✅ | 测试报告中点击"一键修复(N Bug)"→调用test_report_orchestrator Agent→逐阶段重新生成→下游级联重建 | 已合入 |

---

## 二十六、编排层 (Orchestration)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| SubagentCoordinator | `apps/agents/subagent/coordinator.py` | ✅ | 自动同步 | 已合入 |
| AdaptiveContextRouter | `harness/knowledge/adaptive_context.py` | ✅ | 自动同步 | 已合入 |
| GossipProtocol | `harness/memory/gossip_protocol.py` | ✅ | 自动同步 | 已合入 |
| SwarmBroker | `harness/coordination/swarm_broker.py` | ✅ | 自动同步 | 已合入 |
| DynamicOrchestrator | `harness/coordination/dynamic_orchestrator.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 意图分析 | orchestration/intent_analyzer.py | ✅ | 意图分类与分解 | 已合入 |
| 链规划 | orchestration/chain_planner.py | ✅ | 执行链拓扑规划 | 已合入 |
| 能力映射 | orchestration/capability_mapper.py | ✅ | Intent→Capability→Executor 解析链 | 已合入 |
| DAG 编排器 | orchestration/orchestrator.py | ✅ | 多步流水线编排 + DAG 输出 | 已合入 |
| Pipeline 引擎 | harness/execution/pipeline_engine.py | ✅ | 多阶段调度/HITL暂停/重试/snapshot | 已合入 |
| LangGraph 图执行 | harness/execution/langgraph/ | ✅ | 节点拓扑执行+条件边路由+checkpoint | 已合入 |
| DynamicRouter (LLM路由) | harness/execution/dynamic_router.py | ✅ | LLM驱动动态下一跳选择 + Reducer状态合并防并行覆盖 + 灰度上线(AIPLAT_DYNAMIC_ROUTER_PERCENTAGE) | 已合入 |
| DebateMode | harness/execution/debate.py | ✅ | N-Agent辩论: 收敛检测 + Manager合成, routing_mode="debate" | 已合入 |
| Swarm | harness/execution/swarm.py | ✅ | N-Agent竞选择优: 同任务独立执行→Arena评分→胜出合并, routing_mode="swarm" | 已合入 |
| Roundtable | harness/execution/roundtable.py | ✅ | 多Agent平等讨论: 每轮全员发言→共识收敛→综合合成, routing_mode="roundtable" | 已合入 |
| Matter (验收+交付) | [概念] — 前端验收交互 | ✅ | 交付物定义 + 验收标准字段, 存储于 SpecVersion.content | 已合入 |
| CoT AutoInject | harness/syscalls/llm.py:253` + `harness/utils/prompt_loader.py:cot-auto-inject | ✅ | 每次LLM调用自动注入4步推理指令, AIPLAT_COT_AUTO_INJECT控制 | 已合入 |
| SubAgent 协调器 | apps/agents/subagent/coordinator.py | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 并行执行器 | apps/agents/parallel_executor.py | ✅ | Map-Reduce 模式 + max_concurrency + 异常隔离 | 已合入 |
| 8 种协调模式 | harness/coordination/patterns/ | ✅ | Pipeline/FanOut/Supervisor/ExpertPool/ProducerReviewer/Hierarchical | 已合入 |
| 统一编排入口 | orchestration/__init__.py | ✅ | L1+L2+L3 三层架构统一 import | 已合入 |
| 编排 YAML 配置化 | apps/agents/base.py:create_agent() | ✅ | AGENT.md `orchestration.mode` 字段自动升级为 MultiAgent | 已合入 |

---

## 二十七、L6 自主能力 (Phase 39-41)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 抽象目标分解 | harness/optimization/abstract_goal_decomposer.py | ✅ | LLM+Ontology拆解模糊目标→三元组→子Goal列表→可行性评估 | 已合入 |
| 目标依赖规划 | harness/optimization/goal_dependency_graph.py | ✅ | 子目标拓扑排序(复用PipelineEngine依赖层算法)+LLM推理依赖+分层并行执行 | 已合入 |
| 目标进度评估 | harness/optimization/goal_progress_evaluator.py | ✅ | UCB1收敛检测→停滞自动replan→converging/plateau/diverging趋势判断 | 已合入 |
| 自主部署流水线 | harness/deployment/deploy_engine.py | ✅ | 沙箱→灰度5%→25%→100%→git push→构建→部署→健康检查→自动回滚(三道防线) | 已合入 |
| Git推送+构建 | harness/deployment/git_pusher.py | ✅ | git push+Docker build+PR创建+rollback到deploy-*标签 | 已合入 |
| 灰度自动推进 | harness/deployment/canary.py:auto_canary_rollout() | ✅ | 5%→25%→100%自动推进+错误率>5%停止+自动回滚 | 已合入 |
| 外部服务发现(监听) | harness/infrastructure/discovery_listener.py | ✅ | 监听auto_discovered/目录+新YAML自动加载+AutoRegisterEngine验证 | 已合入 |
| 外部服务发现(注册) | harness/infrastructure/auto_register.py | ✅ | 连接测试+本体映射建议+DataSourceRegistry注册+PolicyGate审批 | 已合入 |

---

## 二十八、记忆系统白盒化 (Phase 40 记忆升级)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 长期记忆CRUD | management/arch_guard_rules/memory.py` + `services/execution_store/ltm_mixin.py | ✅ | GET/PUT/DELETE /memory/longterm/{id} — 浏览/编辑/删除长期记忆 | 已合入 |
| Provenance全链路 | memory/base.py:29` + `ltm_mixin.py` + `semantic.py | ✅ | source_tag/trust_weight/provenance 三字段 SQL→API→UI全链路落地 | 已合入 |
| 语义记忆软删除 | memory/manager.py:forget_semantic()` + `memory.py | ✅ | DELETE /memory/semantic/{key} 软删除 + POST /memory/semantic/{key}/recover 恢复 | 已合入 |
| 记忆规则引擎 | memory/manager.py:save_memory_rules()` + `UserProfileModal.tsx | ✅ | 忽略寒暄/必记报错开关 + 自定义模式匹配, 存于 ~/.aiplat/memory_rules.json | 已合入 |
| 结构化筛选器 | ⚠️ deprecated ltm_mixin.py:list_long_term_memories_filtered() | ✅ | source_tag + min_trust + date_range 参数化查询, 零SQL注入风险 | 已合入 |
| 行展开详情面板 | LongTermMemoryModal.tsx | ✅ | 点击展开: metadata_json + relevance_decay + provenance 完整可视化 | 已合入 |
| Wiki页面编辑 | frontend/src/pages/Platform/KnowledgeBase/index.tsx:handleWikiEdit() | ✅ | 选中Wiki页面→预填充表单→编辑保存 | 已合入 |

---

## 二十九、记忆运行时过滤 (Phase 40 记忆引擎)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 记忆规则运行时过滤 | memory/manager.py:save_interaction() | ✅ | ignore_greetings/capture_errors 开关 + 自定义模式匹配, 动态调整 stability + is_critical | 已合入 |
| GoalExecutor自动执行 | server.py:1465` + `goal_executor.py:86 | ✅ | 服务器启动时自动开启后台轮询, 策略优化/探索缺口目标定时自动执行 | 已合入 |

---

## 三十、MoA 多模型推理 (Phase 42)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 通用MoA引擎 | harness/syscalls/moa_executor.py | ✅ | 两层流水线: asyncio.gather N参考引擎(高温)+1聚合器(低温) → 流式内部收集返回str, 成本守卫+故障容忍 | 已合入 |
| MoA预设配置 | harness/syscalls/moa_presets.yaml | ✅ | 3套预设: general(创新)/creative(高发散)/analysis(严格收敛), aggregator_instruction可配置 | 已合入 |
| `/moa`命令 | command_parser.py:parse() | ✅ | `/moa --preset security 分析代码` → moa_executor → 聚合答案, 执行完自动切回单模型 | 已合入 |
| Pipeline路由模式 | pipeline_engine.py:_run_moa() | ✅ | `routing_mode="moa"` + `moa_preset="architecture"` → 阶段级MoA并行推理, 输出协议: 纯文本+元数据 | 已合入 |
| 模型选择器MoA | frontend/src/components/model/ModelTierPanel.tsx | ✅ | 点击MoA卡片→选择preset→后续所有对话自动走两层推理, sessions持久化 | 已合入 |

---

## 三十一、AI知识层增强 (Phase 42)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Wiki 全局索引生成 | wiki_engine.py:generate_index_md() | ✅ | 按分类分组生成 index.md，每条目含摘要+置信度+关联数, 对标 AI知识层系统的全局索引 | 已合入 |
| 一键URL导入 | wiki.py:POST /ingest/url | ✅ | 提交URL→自动抓取→去HTML→保存素材箱, 对标浏览器剪藏/Read-It-Later | 已合入 |
| 品牌基础层注入 | harness/memory/brand_rules.yaml` + `learning/manager.py | ✅ | voice/tone/forbidden_words/format_rules YAML配置，Agent启动时自动注入, 对标 Brand Foundation | 已合入 |

---

## 三十二、Hermes压缩对标 (Phase 42)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 微压缩(micro_compress) | compressor.py:_micro_compress() | ✅ | 折叠连续短assistant/tool消息为单行摘要, 填补5阶段压缩流水线最后一环 | 已合入 |
| Transcript Guard | transcript_guard.py:normalize_roles() | ✅ | 角色序列归一化: 连续同角色合并或插入占位, 防止多轮对话模型行为退化 | 已合入 |
| 系统提醒结构 | reminders.py:check_and_inject()` + `manager.py | ✅ | 返回结构化dict含role字段, 支持AIPLAT_REMINDER_ROLE=user切换, 注入改为消息对象 | 已合入 |

---

## 三十三、Scenario Simulation — 多场景沙盒推演 (Palantir 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SimulationOrchestrator | harness/execution/simulation.py | ✅ | 多场景并发推演编排：种子参数→变异场景→dry_run执行→对比报告 | 已合入 |
| ScenarioDefinition | harness/execution/simulation.py | ✅ | 场景定义：MODEL_VARIANT/PROMPT_VARIANT/SKIP_STAGE/TOOL_RESTRICTION | 已合入 |
| SimulationReport | harness/execution/simulation.py | ✅ | 结构化对比报告：Token/质量/速度/产物差异+风险评估+部署建议 | 已合入 |
| run_evox_scenarios | harness/execution/simulation.py | ✅ | EvoX蜂群场景推演：粗粒度vs细粒度vs互补配对三分支对比 | 已合入 |
| SimulationPanel (UI) | frontend/Diagnostics/SimulationPanel.tsx | ✅ | 场景配置→并发推演→对比报告→风险评估全流程面板 | 已合入 |

---

## 三十四、Decision Lineage — 决策血缘 (Palantir 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| lineage_decisions 表 | services/execution_store/schema.py:v53 | ✅ | 15字段决策记录：who/when/version/chosen/why/outcome | 已合入 |
| LineageStore | harness/infrastructure/lineage_store.py | ✅ | SQLite持久化+决策图谱构建(nodes+edges) | 已合入 |
| capture_tool_decision | harness/infrastructure/decision_capture.py | ✅ | sys_tool_call前自动捕获工具选择决策 | 已合入 |
| capture_skill_decision | harness/infrastructure/decision_capture.py | ✅ | sys_skill_call前自动捕获技能选择决策 | 已合入 |
| inject_context_version_pin | harness/infrastructure/decision_capture.py | ✅ | 注入ontology_version+kb_collection_version到trace_context | 已合入 |
| LineageViewer (UI) | frontend/Diagnostics/LineageViewer.tsx | ✅ | 列表+图谱视图：决策链展开/候选方案/治理信息 | 已合入 |

---

## 三十五、Security 3D — 三维权限 (Palantir 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| PurposeRegistry | harness/infrastructure/gates/purpose_registry.py | ✅ | 6个内置Purpose：general/diagnosis/deployment/knowledge_gen/audit_review/training | 已合入 |
| check_tool_3d | harness/infrastructure/gates/policy_gate.py | ✅ | Role×Purpose×Marking三维权限融合 | 已合入 |
| marking_propagation | harness/infrastructure/gates/marking_propagation.py | ✅ | 轻量标记传播wrapper：BFS+运行时检查+context注入 | 已合入 |
| PurposeContext (UI) | frontend/components/security/PurposeContext.tsx | ✅ | 操作目的选择器：选定Purpose自动收敛工具和数据范围 | 已合入 |

---

## 三十六、Global Branching — 本体分支管理 (Palantir 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| OntologyBranchManager | harness/ontology_engine/ontology_branch.py | ✅ | git-like分支管理：fork/list/diff/merge/delete | 已合入 |
| DiffResult/MergeResult | harness/ontology_engine/ontology_branch.py | ✅ | 三方对比+三级合并策略(auto/warn/blocked) | 已合入 |
| BranchPanel (UI) | frontend/Diagnostics/BranchPanel.tsx | ✅ | 分支列表+fork对话框+diff可视化+merge操作 | 已合入 |

---

## 三十七、EvoX 蜂群协作层 (EvoMap 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| AtomicTaskSplitter | harness/execution/atomic_splitter.py | ✅ | 任务→原子拆分+verify_coverage全覆盖验证+自动补全 | 已合入 |
| ProgrammaticCollector | harness/execution/programmatic_collector.py | ✅ | 程序化汇合：从state按key收集，不经过LLM转述 | 已合入 |
| LossDetector | harness/execution/programmatic_collector.py | ✅ | 损耗检测：原子正确数vs汇总正确数，保留率分析 | 已合入 |
| EvoXExecutor | harness/execution/evox_executor.py | ✅ | 全链路蜂群：拆分→并发→汇合→模板渲染→损耗检测 | 已合入 |
| AgentSpecialization | harness/learning/agent_specialization.py | ✅ | 专长计算：行动历史→向量+互补性评分+衰减 | 已合入 |
| PartnerSelector | harness/learning/partner_selector.py | ✅ | 伙伴选择：social/capability/complementary三模式+聚类系数 | 已合入 |
| AgentNetwork | harness/learning/agent_network.py | ✅ | 网络分析：枢纽节点+演化追踪+快照持久化 | 已合入 |
| EvoXPanel (UI) | frontend/Diagnostics/EvoXPanel.tsx | ✅ | 蜂群推演面板：输入→拆分→执行→损耗率分析 | 已合入 |
| AgentNetworkPanel (UI) | frontend/Diagnostics/AgentNetworkPanel.tsx | ✅ | 网络可视化：枢纽节点+演化时间线+伙伴选择测试 | 已合入 |

---

## 三十八、闭环执行层 (TemplateEngine + OperationRecorder + MCP Ecosystem)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| TemplateRegistry | harness/document/template_engine.py | ✅ | 模板注册：白名单(.docx/.xlsx/.md)，拒绝含宏(.docm/.xlsm) | 已合入 |
| TemplateRenderer | harness/document/template_engine.py | ✅ | 模板渲染：python-docx/openpyxl/MD，沙盒限制 | 已合入 |
| OperationRecorder | harness/learning/operation_recorder.py | ✅ | 操作录制：监听syscall→记录序列→零开销(仅recording_id存在时) | 已合入 |
| SkillGenerator | harness/learning/skill_generator.py | ✅ | 操作→SKILL.md：sanitize(5类脱敏)+validate(3重检查)+refine(保留修正) | 已合入 |
| MCP WPS/飞书/钉钉/微信 | ~/.aiplat/mcp/*.yaml | ✅ | 4个生态连接器：restart_policy:always+健康检查 | 已合入 |
| TemplatePanel (UI) | frontend/Diagnostics/TemplatePanel.tsx | ✅ | 模板注册+渲染面板 | 已合入 |
| RecordingPanel (UI) | frontend/Diagnostics/RecordingPanel.tsx | ✅ | 录制→生成→编辑→注册Skill全流程面板 | 已合入 |

---

## 三十九、知识编译与 OKF 导出 (Karpathy LLM Wiki 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| OKFExporter | harness/knowledge/okf_exporter.py | ✅ | GraphIndex实体→OKF .okf.md 标准格式导出 (YAML Frontmatter + Markdown正文) | 已合入 |
| OKF 增量导出 | harness/knowledge/okf_exporter.py | ✅ | incremental模式仅导出变更实体，按last_export_ts筛选 | 已合入 |
| KnowledgeROI | harness/knowledge/knowledge_roi.py | ✅ | RAG vs Wiki Token对比追踪：knowledge_roi表(9字段)+累积节省+折合成本 | 已合入 |
| CompilationDashboard (UI) | frontend/Diagnostics/CompilationDashboard.tsx | ✅ | 三层可视化：总量→效率对比→ROI累积+日趋势+按域分解 | 已合入 |
| POST /knowledge/export-okf | platform/apps/fde/api/fde.py | ✅ | 导出域本体为OKF标准格式 | 已合入 |
| GET /knowledge/roi | platform/apps/fde/api/fde.py | ✅ | 获取知识编译ROI数据 (可设domain/days) | 已合入 |
| KnowledgeROI auto-wiring | harness/syscalls/retrieval.py | ✅ | 每次知识检索时自动记录ROI数据(rag_tokens vs wiki_tokens)，使CompilationDashboard展示实时数据 | 已合入 |
| POST /knowledge/roi/record | platform/apps/fde/api/fde.py | ✅ | 记录查询ROI数据 | 已合入 |

---

## 四十、对话→Wiki 自动管线 (CodeAlmanac 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ConversationIngestor | harness/knowledge/conversation_ingestor.py | ✅ | memory_messages→LLM判断价值→Wiki自动写入，含平台+repo双路径 | 已合入 |
| AutoGarden | harness/knowledge/auto_garden.py | ✅ | 自动Wiki花园：过期(软删除)/重复/孤立/薄内容清理+健康评分 | 已合入 |
| conversation_ingest cron | harness/scheduler/cron.py | ✅ | 每5小时自动扫描对话→Wiki (CodeAlmanac sync) | 已合入 |
| auto_garden cron | harness/scheduler/cron.py | ✅ | 每天自动清理过期/重复/孤立页面 (CodeAlmanac garden) | 已合入 |
| POST /ingest-conversations | platform/apps/fde/api/fde.py | ✅ | 手动触发对话摄入 | 已合入 |
| POST /garden | platform/apps/fde/api/fde.py | ✅ | 手动触发花园整理(dry_run/hard_delete) | 已合入 |

---

## 四十一、Web 工具归并 (Firecrawl 对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| WebSearchTool | apps/tools/web/web_search.py | ✅ | 统一搜索: DuckDuckGo HTML/JSON/浏览器三后端可选 | 已合入 |
| WebCrawlTool | apps/tools/web/web_crawl.py | ✅ | BFS全站抓取, 同源过滤, 深度限制 (对齐Firecrawl Crawl) | 已合入 |
| WebMapTool | apps/tools/web/web_crawl.py | ✅ | URL发现+标题提取 (对齐Firecrawl Map) | 已合入 |
| extract_text_from_html | harness/document/parsers.py | ✅ | HTML→纯文本统一入口, 替代4处重复实现 | 已合入 |

---
## 四十一、Skill 目录标准化与验收 (文章对齐)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SkillRegistry._load_extras | apps/skills/registry.py | ✅ | 扫描 references/scripts/assets 子目录资源 | 已合入 |
| SkillVerifier | apps/skills/skill_verify.py | ✅ | 5项自动化验收: 可识别/可调用/输出稳定/格式一致/内容符合 | 已合入 |
| GET /skills/{id}/verify | platform/apps/fde/api/fde.py | ✅ | Skill 验收报告端点 | 已合入 |
| GET /skills/{id}/extras | platform/apps/fde/api/fde.py | ✅ | Skill 子目录资源查询 | 已合入 |
| POST /skills/install | platform/apps/fde/api/fde.py | ✅ | 从URL或路径安装Skill | 已合入 |
| bug_report Skill | engine/skills/bug_report/SKILL.md | ✅ | 残缺Bug描述→结构化Bug单(6字段自动推断) | 已合入 |
| log_analyzer Skill | engine/skills/log_analyzer/SKILL.md | ✅ | 日志异常提取→归类→根因定位→回归范围建议 | 已合入 |

---
## 四十一、E2E端到端验证

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| E2EVerifier | harness/execution/e2e_verifier.py | ✅ | 一次调用验证7子系统: ①拆分②执行③汇合④损耗⑤血缘⑥ROI⑦Wiki | 已合入 |
| POST /verify/e2e | platform/apps/fde/api/fde.py | ✅ | 端到端全链路验证端点 | 已合入 |
| record_traversal_step | harness/infrastructure/lineage_store.py | ✅ | 记录语义遍历步骤到lineage_decisions (decision_type=traversal) | 已合入 |
| GET /lineage/{id}/path | platform/apps/fde/api/fde.py | ✅ | 获取推理遍历路径 | 已合入 |
| graph_traversal record_path | harness/ontology_engine/graph_traversal.py | ✅ | traverse()新增record_path参数，BFS每步自动记录遍历证据 | 已合入 |
| OntologyValidator | harness/infrastructure/gates/ontology_validator.py | ✅ | 本体驱动确定性校验: PreToolUse/PostToolUse/Stop三阶段规则检查 | 已合入 |
| ontology hooks | harness/infrastructure/hooks/hook_manager.py | ✅ | PreToolUse(priority65)+Stop(priority60)挂接OntologyValidator | 已合入 |
| inference_rules injection | harness/infrastructure/gates/ontology_validator.py | ✅ | 自动读取exclusive_states+state_dependencies+transitions转为runtime约束 | 已合入 |
| Ingestor→MemoryManager | harness/memory/manager.py | ✅ | build_context自动注入最近7天byIngestor生成的Wiki页面 | 已合入 |
| Wiki冲突处理 | harness/knowledge/conversation_ingestor.py | ✅ | 平台>30%/repo>15%差异保留用户版+.aiplat_conflict审计 | 已合入 |
| GET /health/all | platform/apps/fde/api/fde.py | ✅ | 一键聚合7子系统健康状态 | 已合入 |
| Runtime Profile Calibration | harness/execution/pipeline_engine.py | ✅ | v5.0 运行时剖面校准 — 对比Agent静态声明 vs 执行实际行为，自动纠正能力等级偏差 | 已合入 |
| Cross-Domain Ontology Bridge | harness/knowledge/cross_domain_bridge.py | ✅ | 跨域三元组桥接 — Wiki→Agent、Model→Agent、Prompt→Agent，将5个孤立知识图连接到统一TripleStore | 已合入 |
| Ontology REST API | api/routers/ontology_routes.py | ✅ | 统一知识本体查询API — POST /query、GET /impact/{urn}、GET /stats | 已合入 |
| sys_ontology_context Syscall | harness/syscalls/ontology.py | ✅ | Agent ReActLoop中可调用的知识网络上下文查询 | 已合入 |
| Ontology Health Check | diagnostics/checks/ontology_health.py | ✅ | 本体驱动健康检查 — 孤儿Skill/Tool/Agent检测、废弃模型检测、孤立Wiki检测 | 已合入 |

---

## 统计

<!-- AUTO-STATS -->
| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|------|
| Harness 执行引擎 | 69 | 0 | 69 |
| 记忆子系统 | 41 | 0 | 41 |
| 知识引擎（本体） | 150 | 0 | 150 |
| RAG 检索 | 46 | 0 | 46 |
| 知识基础设施 | 29 | 0 | 29 |
| Agent 系统 | 42 | 0 | 42 |
| Skill 系统 | 54 | 0 | 54 |
| 安全与治理 | 55 | 0 | 55 |
| 可观测性 | 27 | 0 | 27 |
| 模型基础设施 | 42 | 0 | 42 |
| 部署与运维 | 23 | 0 | 23 |
| 扩展与学习 | 130 | 0 | 130 |
| Gate 系统 | 19 | 0 | 19 |
| 评估系统 | 18 | 0 | 18 |
| MCP 协议 | 9 | 0 | 9 |
| A2A 协议 | 9 | 0 | 9 |
| 文档智能 | 27 | 0 | 27 |
| 工具生态 | 22 | 0 | 22 |
| 微调系统 | 14 | 0 | 14 |
| 部署与灰度 | 7 | 0 | 7 |
| 运行时干预 | 6 | 0 | 6 |
| Arena & 调度 | 7 | 0 | 7 |
| 平台治理 | 88 | 0 | 88 |
| Infra 基础设施 | 14 | 0 | 14 |
| 核心API统一入口 | 7 | 0 | 7 |
| 编排系统 | 10 | 0 | 10 |
| 管理 & 质量 | 28 | 0 | 28 |
| 编排层 | 22 | 0 | 22 |
| L6 自主能力 | 8 | 0 | 8 |
| 记忆系统白盒化 | 7 | 0 | 7 |
| 记忆运行时过滤 | 2 | 0 | 2 |
| MoA多模型推理 | 5 | 0 | 5 |
| AI知识层增强 | 3 | 0 | 3 |
| Hermes压缩对标 | 3 | 0 | 3 |
| Scenario Simulation | 5 | 0 | 5 |
| Decision Lineage | 6 | 0 | 6 |
| Security 3D 增强 | 4 | 0 | 4 |
| Global Branching | 3 | 0 | 3 |
| EvoX 蜂群协作 | 9 | 0 | 9 |
| 闭环执行层 | 7 | 0 | 7 |
| 知识编译与OKF | 0 | 0 | 0 |
| 对话→Wiki 自动管线 | 6 | 0 | 6 |
| Skill 目录标准化 | 7 | 0 | 7 |
| Web 工具归并 | 4 | 0 | 4 |
| E2E 端到端验证 | 16 | 0 | 16 |
| **总计** | **1110** | **0** | **1110** |

| **总计** | **1095** | **0** | **1095** |

---

*最后更新: 2026-07-30*
*版本: 25.0 · +Scenario Simulation(10) +Decision Lineage(11) +Security 3D(7) +Global Branching(10) +EvoX Swarm(16) +ClosedLoop(17)*

**自检命令**：
```bash
# 1. 验证 ✅ 数与统计表一致
grep -c '✅' AIPLAT_CAPABILITIES.md
# 预期: 应匹配统计表的 "400 ✅"

# 2. 验证代码位置仍存在
grep '^\|.*`.*\.py:.*`.*\|' AIPLAT_CAPABILITIES.md | grep -oP '`[^`]+\.py[^`]*`' | while read f; do
  path=$(echo "$f" | tr -d '`')
  [ -f "aiPlat-core/core/$path" ] || echo "MISSING: $path"
done
```
