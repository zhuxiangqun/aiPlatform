# Code Review Gold Seeds (ReviewBench-aligned)

40+ match-only cases covering common P0/P1 security & correctness findings.

## Install into runtime gold dir

```bash
python3 scripts/eval_code_review_gold.py --install-seeds
# → ~/.aiplat/eval/code_review_gold/

# Or full offline readiness (seeds + IDE hooks):
bash scripts/ops_harness_ready_check.sh
```

Tenant-scoped:

```bash
mkdir -p ~/.aiplat/eval/tenants/demo/code_review_gold
cp aiPlat-core/workspace_seeds/eval/code_review_gold/*.yaml \
  ~/.aiplat/eval/tenants/demo/code_review_gold/
```

## Smoke (no LLM)

```bash
python3 scripts/eval_code_review_gold.py --match-only \
  --gold-dir aiPlat-core/workspace_seeds/eval/code_review_gold
```

## Live autoreview

Add `target:` (frozen git ref / worktree path) to each case, then:

```bash
python3 scripts/eval_code_review_gold.py --profile balanced --record-novel
```

Novel P0/P1 → shared_memory + experience_feedback pending (never rewrites gold).
Promotion → Team Brain via ExperienceStore confirm.
