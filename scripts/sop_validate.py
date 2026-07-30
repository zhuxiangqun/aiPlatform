#!/usr/bin/env python3
"""SOP 自动验证 — Day 1-5 checks for domain delivery (v1.0)."""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def run_checks(domain_id: str):
    base = os.path.expanduser(f"~/.aiplat")
    results = {}

    # ── Day 1: Ontology ──
    yp = os.path.join(base, "ontologies", f"{domain_id}.yaml")
    if not os.path.exists(yp):
        results["Day1-YAML"] = (False, f"Not found: {yp}")
    else:
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            onto = load_ontology_from_yaml(yp)
            n = len(getattr(onto, "classes", []))
            results["Day1-YAML"] = (n >= 3, f"{n} classes loaded")
        except Exception as e:
            results["Day1-YAML"] = (False, str(e)[:80])

    # ── Day 2: Seed data ──
    sp = os.path.join(base, "seed_data", f"{domain_id}.json")
    if not os.path.exists(sp):
        results["Day2-Seed"] = (False, "No seed data")
    else:
        try:
            with open(sp) as f:
                data = json.load(f)
            n = len(data.get("entities", []))
            results["Day2-Seed"] = (n >= 10, f"{n} seed entities")
        except Exception as e:
            results["Day2-Seed"] = (False, str(e)[:80])

    # ── Day 3: Actions ──
    ap = os.path.join(base, "actions", f"{domain_id}_actions.yaml")
    if not os.path.exists(ap):
        results["Day3-Actions"] = (False, "No actions YAML")
    else:
        try:
            from core.harness.infrastructure.action_contract import ActionContractModel
            contracts = ActionContractModel.from_yaml_batch(ap)
            results["Day3-Actions"] = (len(contracts) >= 3, f"{len(contracts)} actions defined")
        except Exception as e:
            results["Day3-Actions"] = (False, str(e)[:80])

    # ── Day 3b: Handlers ──
    try:
        from custom_handlers.service_handlers import (
            assign_technician, start_repair, submit_report,
            complete_work_order, reopen_work_order,
        )
        results["Day3-Handlers"] = (True, "5 handlers importable")
    except Exception as e:
        results["Day3-Handlers"] = (False, str(e)[:80])

    # ── Day 4: RuleValidator ──
    try:
        from core.harness.infrastructure.rule_validator import RuleValidator
        v = RuleValidator(domain_id)
        r = v.check_transition("test", "已完成", "待指派")
        results["Day4-Rules"] = (not r["valid"], "RuleValidator blocks correctly" if not r["valid"] else "Unexpected: allowed")
    except Exception as e:
        results["Day4-Rules"] = (False, str(e)[:80])

    # ── Day 5: Audit store ──
    try:
        from core.harness.infrastructure.action_store import ActionStore
        store = ActionStore()
        await store.initialize()
        results["Day5-Audit"] = (True, "Audit store initialized")
    except Exception as e:
        results["Day5-Audit"] = (False, str(e)[:80])

    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="service-domain")
    args = parser.parse_args()

    results = await run_checks(args.domain)
    passed = sum(1 for v in results.values() if v[0])
    total = len(results)

    print(f"\nSOP 验证 — {args.domain}")
    print("-" * 50)
    for name, (ok, msg) in results.items():
        print(f"{'✅' if ok else '❌'} {name}: {msg}")
    print("-" * 50)
    print(f"通过率: {passed}/{total}")
    print(f"最终: {'✅ ALL PASS' if passed == total else '❌ FAIL'}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
