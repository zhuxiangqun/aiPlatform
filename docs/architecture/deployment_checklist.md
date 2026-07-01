# aiPlatform Production Deployment Checklist

## Pre-Deployment Verification

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | All tests pass | `pytest aiPlat-core/core/tests/unit/ aiPlat-core/core/tests/wiring/ -q` | 110+ passed, ≤2 skipped |
| 2 | Architecture guard clean | `bash scripts/architecture_guard.sh` | 0 new errors |
| 3 | Import chain intact | `python -c "import all_modules"` | 0 import errors |
| 4 | No dead code | `grep -rn "TODO.*wire\|0 caller" aiPlat-core/core/ --include='*.py' \| grep -v __pycache__` | empty output |
| 5 | Capabilities doc synced | `grep -c "✅" AIPLAT_CAPABILITIES.md` | matches code |

## Feature Flags (Production Safe Defaults)

| Feature | Env Var | Default | Risk | Ready? |
|---------|---------|:---:|:---:|:---:|
| DynamicRouter | `routing_mode="llm"` on stage config | `"static"` | Low | ✅ |
| RL Training | `AIPLAT_RL_ENABLED=true` | `false` | Medium | ✅ |
| RL Online Mode | `AIPLAT_RL_ONLINE=true` | `false` | High | ✅ |
| Auto-learn | `AIPLAT_META_AGENT_ENABLED=true` | `false` | Low | ✅ |
| Cross-tenant scan | `AIPLAT_CROSS_TENANT_SCAN_ENABLED=true` | `false` | Medium | ✅ |
| ImmuneMemory | Always on (via `_guard_messages()`) | `active` | Low | ✅ |
| ToolDriftDetector | Always on (via `sys_tool_call`) | `active` | Low | ✅ |

## Grayscale Sequence (DynamicRouter)

```
Phase 1 (Week 1): 1 internal pipeline, routing_mode="llm"
  → Monitor _dynamic_trace for supervisor decision accuracy
  → Target: >80% correct routing decisions (human review)

Phase 2 (Week 2): Expand to 3 pipelines if Phase 1 passes
  → Monitor cost delta (must be <2x baseline)
  → Monitor latency delta (must be <1.5x baseline)

Phase 3 (Week 3): Enable on all non-critical pipelines
  → Continue monitoring via EvolutionEngine nightly metrics

Rollback: Set routing_mode="static" on any stage config
  → Immediate: no code change needed
```

## SFT→RL Pipeline Activation

```bash
# Step 1: Enable implicit feedback collection
export AIPLAT_IMPLICIT_FEEDBACK_ENABLED=true

# Step 2: Wait for 100+ positive samples (check via get_implicit_feedback_collector().get_stats())

# Step 3: SFT auto-triggers at ≥100 samples
export AIPLAT_SFT_ENABLED=true

# Step 4: After SFT completes, enable RL (optional — V2.5)
export AIPLAT_RL_ENABLED=true
export AIPLAT_RL_ONLINE=false   # Start with offline mode
# After 2 iterations of offline RL → enable online
export AIPLAT_RL_ONLINE=true
```

## Rollback Procedure

| Scenario | Action |
|----------|--------|
| DynamicRouter accuracy drops | Set `routing_mode="static"` on stage config |
| RL training diverges | Set `AIPLAT_RL_ENABLED=false` |
| SkillOpt generates bad drafts | Clear `~/.aiplat/skill_drafts/` |
| SFT dataset quality drops | Lower `AIPLAT_SFT_MIN_QUALITY` |
| ImmuneMemory false positives | Raise `AIPLAT_IMMUNE_LEVEL1` to 0.98 |

## Health Checks (Nightly)

EvolutionEngine runs at 3AM (default). Check logs:
```bash
grep "EvolutionEngine" ~/.aiplat/logs/ | tail -20
```

Expected: 11 steps completed or partial (some steps may skip if disabled).
