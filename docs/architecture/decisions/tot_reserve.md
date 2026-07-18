# Decision: Tree of Thoughts (ToT) — Delayed Indefinitely

**Date**: 2026-07-01
**Status**: Archived for V3.0 re-evaluation
**Author**: aiPlatform architecture review

---

## Context

Of the 13 mainstream Agent design patterns (from Single Agent to Loop Engineering),
aiPlatform has implemented 12. Tree of Thoughts (ToT) is the sole unimplemented
pattern.

ToT addresses a specific failure mode: when linear chain-of-thought reasoning
encounters a fork point and needs to explore multiple branches before selecting
the optimal path. The classic example is the "Game of 24" puzzle where GPT-4's
single-pass CoT success rate is 4%, but ToT lifts it to 74%.

## Decision

**Do not implement ToT at this time. Archive the design for V3.0.**

## Rationale

Three reasons, ranked by weight:

1. **Native reasoning models have internalized multi-path search.**
   GPT-5.5, Claude 4, and Gemini 2.5 (all Q2 2026) perform internal tree search
   during inference. Wrapping ToT around them means paying for the same
   computation twice — once inside the model, once in your architecture.
   The article itself warns: "如果你已经在用推理模型，外面再套 ToT 大概率是在为推理推理。"

2. **Cost-to-benefit ratio is unfavorable.**
   Theoretical numbers based on aiPlatform's current production parameters
   (max_steps=10, avg_tokens/step=2000):

   | Metric | Current (ReAct) | ToT (k=3, d=2) | Delta |
   |--------|:---:|:---:|:---:|
   | LLM calls per task | ~10 | up to 13 nodes × 2 (gen+eval) ≈ 26 | +160% |
   | Token consumption | ~20,000 | ~52,000 | +160% |
   | Success rate gain (on reasoning models) | baseline | +5%~15% | marginal |
   | Debugging complexity | low | high (tree state tracing) | steep increase |

   A 5-15% success rate improvement at 160% cost increase does not clear the ROI bar.

3. **Existing architecture provides Agent-level multi-path exploration.**
   `Plan-and-Execute` + `DynamicRouter` + `SubagentCoordinator` already perform
   branch exploration and dynamic routing at the Agent level, which is more
   cost-efficient and debuggable than Thought-level tree search.

## Architecture Design (Preserved)

The full design document is preserved below for future reference.

### Data Model

```python
@dataclass
class ThoughtNode:
    id: str
    state: Dict[str, Any]          # LoopState snapshot
    content: str                   # LLM candidate "thought"
    score: float = 0.0             # StateEvaluator score [0, 1]
    evaluator_type: str = ""       # "deterministic" | "llm_judge" | "heuristic"
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    depth: int = 0
    status: str = "pending"        # "pending" | "evaluating" | "active" | "dead" | "solution"

@dataclass
class ThoughtTree:
    root: ThoughtNode
    nodes: Dict[str, ThoughtNode]
    best_path: List[str]
    best_score: float = 0.0
    total_cost_tokens: int = 0
    max_depth: int = 3
    branch_factor: int = 3
```

### Three-Layer Architecture

1. **ThoughtGenerator** — LLM generates k=3 candidate next steps from current state
2. **StateEvaluator** — Three-tier: deterministic (free) → heuristic → LLM Judge (fallback)
3. **SearchController** — BFS (shallow trees) / Beam Search (production default) / DFS (fast path)

### PipelineStageConfig Extension

```python
thinking_mode: str = "chain"      # "chain"(ReAct) | "tree"(ToT)
tot_k: int = 3                    # candidates per level
tot_max_depth: int = 2            # max search depth
tot_strategy: str = "beam_search" # "bfs" | "beam_search" | "dfs"
tot_beam_width: int = 2           # beam width
tot_token_budget: int = 50000     # hard budget cap
```

### Hard Safety Limits

```python
TOT_HARD_LIMITS = {
    "max_branches": 3,
    "max_depth": 3,
    "max_total_nodes": 20,
    "token_budget": 50000,
    "evaluator_budget": 10,
}
```

### Implementation Estimate

| File | Lines | Purpose |
|------|:---:|------|
| `execution/tot_engine.py` | ~350 | ThoughtTree + Generator + Evaluator + Controller |
| `schemas_builder.py` | +8 | 5 new fields |
| `execution/loop.py` | +5 | thinking_mode="tree" switch |
| `tests/unit/test_tot_engine.py` | ~25 | Unit tests |
| **Total** | ~388 | 1 new file, 3 modified |

## Re-evaluation Triggers

Re-evaluate ToT implementation when ALL THREE conditions are simultaneously met:

1. Native reasoning capabilities of target models are empirically proven insufficient
   (measured via benchmark that requires multi-path backtracking)
2. Per-task token budget allows 2x current consumption (environment: `AIPLAT_TOT_TOKEN_BUDGET`)
3. Production traces (from aiPlatform's trace analysis via `compare_success_failure()`) show
   concrete evidence that the current Plan-and-Execute + DynamicRouter combination is
   bottlenecked by single-path reasoning

## Related Decisions

- **Implemented instead**: SkillOpt-style dual-channel analysis (P0), Rejected Edit Buffer (P0), Edit Learning Rate (P0) — commit a413fd9
- **Provides coarse-grained multi-path**: `Plan-and-Execute Agent` + `DynamicRouter` (LLM-driven next-stage selection) — commit e6cc6f5
- **Existing tree-like structure**: `LangGraph` checkpoint/resume with conditional routing — `execution/langgraph/core.py`
