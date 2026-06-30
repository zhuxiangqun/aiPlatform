# Decision: Evaluator Self-Calibration (L7) — V3.0

**Date**: 2026-07-01
**Status**: Design archived — V3.0 priority
**Author**: aiPlatform architecture review

## Context

The self-learning pipeline (AutoLearner, PatternAccumulator, SkillSimulator, etc.)
relies on automatic evaluators to determine success/failure of Agent executions.
However, the evaluators themselves are not calibrated against ground truth —
meaning a biased evaluator can systematically reinforce wrong behaviors.

This is the "judge bias" problem:
  - If the evaluator consistently over-scores, AutoLearner generates SkillDrafts
    from low-quality executions.
  - If the evaluator consistently under-scores, valuable successful patterns are never learned.

## Decision

Not implemented yet. Design archived for V3.0.

## Architecture Design

### Core loop: 10% sampling → second-pass re-evaluation → calibrate

```
Every N evaluations:
  1. Randomly sample 10% of evaluations labeled "success"
  2. Re-evaluate with stronger model (GPT-4-Turbo / Claude Opus)
  3. Compare: if second-pass disagrees with original → store in correction pool
  4. When correction pool >= 50 items → fine-tune lightweight evaluator
  5. Adjust evaluation thresholds based on calibration drift
```

### Data model

```python
@dataclass
class CalibrationEntry:
    run_id: str
    original_verdict: str      # "success" | "failure"
    original_confidence: float
    second_pass_verdict: str   # from stronger judge
    second_pass_confidence: float
    disagreement: bool          # True if verdicts differ
    correction_type: str        # "false_positive" | "false_negative"

@dataclass
class CalibrationPool:
    entries: List[CalibrationEntry]  # max 500
    false_positive_rate: float
    false_negative_rate: float
    precision: float
    recall: float
    last_calibrated: float       # timestamp
```

### Integration points

| Component | File | Change |
|-----------|------|:---:|
| Evaluator calibration hook | `execution/pipeline_engine.py` | +15 lines after `_tri_evaluate` |
| Second-pass re-evaluation | `evaluation/calibrator.py` (new) | ~150 lines |
| Fine-tune pipeline trigger | `training/rl_trainer.py` | +10 lines for evaluator fine-tuning |
| Calibration pool storage | `ExecutionStore` `calibration_entries` table | migration script |

### Implementation estimate

~200 lines total, 1 new file, 2 modified files.

## Re-evaluation Triggers

Re-evaluate when:
1. AutoLearner generates SkillDrafts with simulation_pass_rate >= 0.8 but admin rejection rate > 30%
   (suggests evaluator is over-scoring)
2. Production traces show systematic drift in success/failure ratio without corresponding product change
3. User satisfaction metrics diverge from evaluator scores by > 20%

## Related Decisions

- SFT data quality is independently validated via TrajectoryScorer (scoring + mixed sampling + learnability filter)
- RL training uses VerifierReward which is deterministic (rule-based), reducing judge dependency
- The dual-channel Success/Failure analyst provides cross-validation of evaluation results
