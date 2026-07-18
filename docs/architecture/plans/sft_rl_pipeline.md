# SFT→RL Pipeline — End-to-End Data Flow

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: DATA GENERATION (Agent Execution)                   │
│                                                              │
│ Agent runs → ReActLoop.run()                                 │
│   → _infer_task_type() → state.context["task_type"]          │
│   → _try_save_interaction() → ExecutionStore.set_meta()       │
│   → ImplicitFeedbackCollector.record() → implicit_label      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: DATA QUALITY (AutoTrigger)                          │
│                                                              │
│ AutoLearner approves SkillDraft (confidence ≥ 0.8)           │
│   → LoRAAutoTrigger._quality_count++                        │
│   → When ≥ 100: trigger()                                    │
│     → _fetch_samples() from ExecutionStore                   │
│     → TrajectoryScorer.score_batch() — 4-dim quality filter  │
│     → _mixed_sample_by_task_type() — uniform task coverage   │
│     → is_learnable() — student model teachability gate       │
│     → _split_train_val() — 85/15 stratified split            │
│     → sft_train_{ts}.jsonl + sft_val_{ts}.jsonl              │
│     → _auto_submit_job() → JobManager.create()               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: SFT TRAINING                                        │
│                                                              │
│ JobManager._execute()                                         │
│   → DatasetManager.snapshot() → upload → create_job → poll   │
│   → COMPLETED: _register_model() → ModelManager.add_model()  │
│   → _signal_sft_complete() → ~/.aiplat/sft_models/latest.json│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: RL TRAINING (V2.5)                                  │
│                                                              │
│ EvolutionEngine Step 11 (_do_rl_trigger)                     │
│   → RLTrainer._detect_latest_sft_model() ← reads latest.json │
│   → _select_reward(tasks) → CodeTestReward / VerifierReward  │
│   → train(episodes=8, iterations=1)                          │
│     → _rollout_online() with Semaphore(2), timeout(300s)     │
│     → _execute_online() via ReActLoop.run()                  │
│     → VerifierReward.compute() → deterministic score         │
│     → RLOOUpdater.compute_advantages() → policy gradient     │
│   → export_rl_dataset() → ~/.aiplat/rl_data/                 │
└─────────────────────────────────────────────────────────────┘
```

## Key Data Files

| File | Produced By | Consumed By |
|------|------------|-------------|
| `~/.aiplat/sft_models/latest.json` | `job_manager._signal_sft_complete()` | `RLTrainer._detect_latest_sft_model()` |
| `~/.aiplat/sft_models/history.jsonl` | `job_manager._signal_sft_complete()` | Audit trail |
| `~/.aiplat/training/sft_train_{ts}.jsonl` | `auto_trigger.trigger()` | `DatasetManager.import_jsonl()` |
| `~/.aiplat/training/sft_val_{ts}.jsonl` | `auto_trigger.trigger()` | Validation set |
| `~/.aiplat/rl_data/{run_id}.jsonl` | `RLTrainer.export_rl_dataset()` | SkyRL / Harbor |
| `~/.aiplat/skill_drafts/` | `AutoLearner.analyze_failure/success()` | Admin review |
| `~/.aiplat/experience_cache.json` | `ExperienceVector.store()` | `AutoLearner._enrich_with_history()` |
| `~/.aiplat/immune_memory.json` | `ImmuneMemory.save_persistent()` | `ImmuneMemory.load_persistent()` |
| `~/.aiplat/pending_models.json` | `job_manager._register_model()` (degradation) | Admin recovery |

## Environment Variables Quick Reference

```bash
# SFT Pipeline
AIPLAT_SFT_ENABLED=true
AIPLAT_SFT_AUTO_TRIGGER_THRESHOLD=100
AIPLAT_SFT_MIN_QUALITY=0.8
AIPLAT_SFT_TEACHER_MODEL=gpt-5.5
AIPLAT_SFT_STUDENT_MODEL=qwen2.5-coder:7b

# RL Pipeline
AIPLAT_RL_ENABLED=true
AIPLAT_RL_ONLINE=false        # Start offline
AIPLAT_RL_EPISODES_PER_ITER=64
AIPLAT_RL_MAX_CONCURRENT=2
AIPLAT_RL_ROLLOUT_TIMEOUT=300

# Self-Learning
AIPLAT_MAX_EDITS_PER_DRAFT=4
AIPLAT_EXPERIENCE_CACHE_ENABLED=true
AIPLAT_CROSS_TENANT_SCAN_ENABLED=false
AIPLAT_META_AGENT_ENABLED=false
```
