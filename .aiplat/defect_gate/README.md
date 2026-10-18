# Defect gate receipt

Machine-checkable unlock for PR / push. Written by the `defect-gate` skill after
an independent zero-findings review.

- File: `receipt.json` (same directory; commit it with the PR)
- Validate: `python3 scripts/defect_gate_validate.py`
- Template: `python3 scripts/defect_gate_validate.py --print-template`
- Local hook: `.cursor/hooks/defect-gate-shell.sh` denies `gh pr create` / gated `git push` without a pass receipt
- CI: `.github/workflows/defect-gate.yml` — mark **Zero-findings receipt** as a required status check on `main`

`diff_sha256` locks `git diff <merge-base> HEAD` with this receipt excluded.
Any new product commit invalidates it. `head_sha` is informational only.

Emergency local bypass only: `AIPLAT_DEFECT_GATE=0` (CI does not honor this).
