---
doc_type: Index
---

# Conformance Harness

This directory contains **reference** conformance assets, not proof of a deployed implementation.

## Included

- `reference_policy.json` — mock RBAC/ABAC policy used by the semantic validators;
- `approval-record.pending.json` — v4.2 pending approval record (historical);
- `approval-record.approved.json` — v4.2 approved record (historical);
- `approval-record-v4.3.pending.json` — v4.3 pending record (historical);
- `approval-record-v4.3.approved.json` — v4.3 approved record (effective 2027-01-01).

## Commands

```bash
python docs/standards/knowledge-system/v4.3.1/schemas/validate_examples.py
python docs/standards/knowledge-system/v4.3.1/schemas/validate_semantics.py
python docs/standards/knowledge-system/v4.3.1/schemas/validate_examples_v4.3.py
python docs/standards/knowledge-system/v4.3.1/schemas/validate_semantics_v4.3.py
```

## Real implementation tests (required before claiming conformance)

1. **RBAC/ACL**
   - Replace `reference_policy.json` with the deployed policy source.
   - Test recall-time filtering, aggregation, export, cache, and cross-tenant denial.
2. **External reconciliation**
   - Implement query-by-idempotency-key and compensation in the real adapter.
   - Test `unknown → succeeded`, `unknown → failed`, and duplicate execution rejection.
3. **State transitions**
   - Run the sequence cases in `semantic_cases.json` against the real Fact Store.
4. **Citations**
   - Verify every published claim resolves to a real source snapshot/locator.
5. **Customer-action audit**
   - Verify `action_namespace=customer_action` executions contain snapshots, run/evidence refs, and approval id when required.

The mock harness passing does **not** prove these production properties.
