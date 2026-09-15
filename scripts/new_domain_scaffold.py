#!/usr/bin/env python3
"""Scaffold a new ontology domain (Phase B method productization).

Generates:
  - ~/.aiplat/ontologies/{domain_id}.yaml  (classes/states/axioms skeleton)
  - workspace_seeds/actions/{domain_id}_assign.yaml  (optional customer_action)
  - registry.json fragment printed to stdout (merge manually / --apply-registry)

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/new_domain_scaffold.py \\
    --domain-id acme-locks --name "Acme 锁服" --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))


YAML_TMPL = '''# Scaffolded domain — fill scene-specific classes before claiming OCS≥80
name: "{name}"
namespace: "http://aiplat.local/ontology/{domain_id}/"
version: "0.1.0"
description: "Scaffold for {name} — edit classes/states/axioms for your closed loop"

interfaces:
  Assignable:
    label: 可派单
    description: 可复用语义模块 — 可指派责任人
  EvidencedCloseable:
    label: 需证据关单
    description: 可复用语义模块 — 关闭前须证据

classes:
  WorkOrder:
    label: 工单
    implements: [Assignable, EvidencedCloseable]
    required_fields: [order_id, status]
    optional_fields: [assignee, notes]
    categories: [{domain_id}]
    states:
      default: pending
      enum:
        - name: pending
          label: 待处理
        - name: assigned
          label: 已派单
        - name: in_progress
          label: 进行中
        - name: completed
          label: 已完成
      transitions:
        - from: pending
          to: assigned
        - from: assigned
          to: in_progress
        - from: in_progress
          to: completed

  Party:
    label: 责任人
    required_fields: [name]
    categories: [{domain_id}]

object_properties:
  - name: assigned_to
    label: 派单给
    domain: [WorkOrder]
    range: [Party]

axioms:
  - id: {prefix}-A1
    severity: error
    description: "工单派单前须处于 pending；非法状态不得派单"
    check: "WorkOrder.status == pending before assign"
  - id: {prefix}-A2
    severity: error
    description: "完工前须具备完成证据（责任人或证据引用）"
    check: "evidence before completed"
  - id: {prefix}-A3
    severity: warning
    description: "工单应声明责任人字段或 assigned_to 关系"
    check: "assignee or relation assigned_to"
'''

ACTION_TMPL = '''# Scaffold customer_action — adjust required_state / handler as needed
actions:
  - action_id: "customer_action:{domain_id}:assign"
    aliases: []
    label: "派单"
    description: "Scaffold: pending → assigned"
    category: mutation
    scope: domain
    domain_id: {domain_id}
    target_class: 工单
    required_state: pending
    effect_semantics: "Work order assigned"
    compensation: "revert to pending"
    risk_level: medium
    require_approval: false
    throttle_limit: 0
    action_namespace: customer_action
    eval_gate: customer_action_safety
    handler: "core.harness.ontology_engine.builtin_handlers:set_entity_state"
    input_schema:
      type: object
      required: [new_state]
      properties:
        new_state:
          type: string
          const: assigned
        assigned_technician:
          type: string
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain-id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--apply", action="store_true", help="Write YAML under AIPLAT_HOME")
    ap.add_argument("--with-action", action="store_true", default=True)
    ap.add_argument("--apply-registry", action="store_true", help="Merge domain into registry.json")
    args = ap.parse_args()

    did = args.domain_id.strip()
    prefix = "".join(ch for ch in did.upper().replace("-", "_") if ch.isalnum() or ch == "_")[:8] or "DOM"
    yaml_body = YAML_TMPL.format(name=args.name, domain_id=did, prefix=prefix)
    onto_dir = HOME / "ontologies"
    onto_path = onto_dir / f"{did}.yaml"

    if args.apply:
        onto_dir.mkdir(parents=True, exist_ok=True)
        if onto_path.exists():
            print(f"REFUSE: {onto_path} already exists", file=sys.stderr)
            return 2
        onto_path.write_text(yaml_body, encoding="utf-8")
        print(f"wrote {onto_path}")
    else:
        print("--- ontology YAML ---")
        print(yaml_body)

    action_path = (
        ROOT / "aiPlat-core" / "workspace_seeds" / "actions" / f"{did.replace('-', '_')}_assign.yaml"
    )
    if args.with_action:
        action_body = ACTION_TMPL.format(domain_id=did)
        if args.apply:
            action_path.parent.mkdir(parents=True, exist_ok=True)
            if not action_path.exists():
                action_path.write_text(action_body, encoding="utf-8")
                print(f"wrote {action_path}")
            else:
                print(f"skip existing {action_path}")
        else:
            print("--- action YAML ---")
            print(action_body)

    fragment = {
        did: {
            "name": args.name,
            "description": f"Scaffolded domain {args.name}",
            "ontology_file": f"{did}.yaml",
            "collection_id": did,
            "namespace": f"http://aiplat.local/ontology/{did}/",
            "maturity": "seeding",
        }
    }
    print("--- registry fragment ---")
    print(json.dumps(fragment, ensure_ascii=False, indent=2))

    if args.apply_registry:
        reg_path = onto_dir / "registry.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"domains": {}}
        reg.setdefault("domains", {}).update(fragment)
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {reg_path}")

    print("Next: fill scene classes → add GraphIndex instances → raise OCS to ≥70/80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
