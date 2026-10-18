# Defect gate

Two unlock surfaces — do not conflate them:

| Surface | Artifact | Unlocks |
|---------|----------|---------|
| Local (Cursor hook / agents) | `receipt.json` after five-check review | `git push` / `gh pr create` |
| CI (required check **Zero-findings receipt**) | Non-author GitHub `APPROVED` review | Merge to `main` |

An author-signed `receipt.json` **does not** unlock CI. Forging five `pass` checks cannot satisfy the required status check.

## Local

```bash
# After product commits; worktree clean aside from receipt
python3 scripts/defect_gate_validate.py --print-template > .aiplat/defect_gate/receipt.json
# Fill reviewed_at; keep status=pass and findings_count=0 only after a real review
python3 scripts/defect_gate_validate.py
```

- Dirty paths outside the receipt fail validation unless `--allow-dirty`.
- Emergency local bypass only: `AIPLAT_DEFECT_GATE=0` (ignored as unlock in CI independence).

## CI

```bash
python3 scripts/defect_gate_independence.py
```

Needs an `APPROVED` review from someone other than the PR author. Solo maintainers need a second account or reviewer. Workflow: `.github/workflows/defect-gate.yml` (also runs on `pull_request_review`).
