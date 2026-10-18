---
name: defect-gate
description: >-
  Independent defect-first gate before claiming done, committing for merge,
  opening a PR, or pushing to a protected branch. Use when finishing
  implementation, creating a pull request, pushing feature work, or when the
  user asks for a zero-findings review receipt.
---

# Defect Gate (zero findings before PR)

Author-green tests and architecture health are not enough. Before claiming
done, opening a PR, or pushing merge-bound work, run an independent
defect-first review and write a machine-checkable **local** receipt.

Trust model:

- Local receipt unlocks Cursor `git push` / `gh pr create` only.
- CI required check **Zero-findings receipt** unlocks on a **non-author**
  GitHub `APPROVED` review (`scripts/defect_gate_independence.py`).
- Author-signed `receipt.json` does **not** unlock CI.

## When this skill applies

- User asks to finish, ship, open a PR, create a PR, or push.
- Agent is about to say the change is complete.
- Hook or CI asks for a defect-gate receipt.

Do not skip because unit tests or `architecture_guard.sh` passed.

## Review rules

Review the merge diff only (`git merge-base` → `HEAD`). Do not modify product
code during the review pass. Flag only defects introduced by the change.

Every finding needs a path and line. Severity: P0 / P1 / P2 / P3.

Answer all five checks with file:line evidence. Any "yes" is an open finding:

1. **old_fallback** — After the new branch, does older fallback / soft path still run and undo the rule?
2. **call_signatures** — Do all changed call sites still match callee signatures?
3. **failure_as_success** — Can a new failure / skip / deny status be treated as success by an older predicate?
4. **second_implementation** — Is there a second surface (other loop graph, Pi, duplicate API) that still lacks the same fix?
5. **self_certifying_health** — Would a new health / guard check still pass while the defect remains?

Findings cannot be closed by "my new tests cover it." Close only by fixing code
and re-reviewing to zero findings, or by adding a test that fails while the
defect remains and citing that test next to the finding.

## Receipt (required)

After a clean review, write:

`.aiplat/defect_gate/receipt.json`

Validate before PR / push:

```bash
python3 scripts/defect_gate_validate.py
```

Schema (must match exactly):

```json
{
  "schema": "aiplat.defect_gate.v1",
  "status": "pass",
  "findings_count": 0,
  "reviewed_at": "2026-10-18T00:00:00+08:00",
  "base_ref": "origin/main",
  "merge_base": "<git merge-base HEAD origin/main>",
  "diff_sha256": "<from --print-template; receipt file is excluded>",
  "head_sha": "<optional; informational only>",
  "checks": {
    "old_fallback": "pass",
    "call_signatures": "pass",
    "failure_as_success": "pass",
    "second_implementation": "pass",
    "self_certifying_health": "pass"
  },
  "findings": [],
  "reviewer": "agent",
  "note": "brief residual risk if any"
}
```

Rules for the file:

- `status` must be `"pass"` and `findings_count` must be `0` to unlock PR/push.
- `diff_sha256` locks the merge diff **excluding** this receipt file. Fill it with
  `python3 scripts/defect_gate_validate.py --print-template` after the product
  commits exist and the worktree is clean aside from the receipt.
- Do not set `diff_sha256` equal to a commit SHA. A file inside a commit cannot
  contain that commit's SHA.
- Any later product commit changes the diff and invalidates the receipt.
- If findings remain, set `"status": "fail"`, list them under `findings`, and do not open a PR.

## Hard stops

- Do not claim the work is done while the receipt is missing, stale, or `fail`.
- Do not run `gh pr create` / push without a validated local pass receipt.
- Do not treat a local pass receipt as CI green — merge still needs non-author Approve.
- Architecture guard green ≠ defect-gate pass.
