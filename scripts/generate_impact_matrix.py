#!/usr/bin/env python3
"""Phase 43: Generate capability impact matrix from registry YAML.

Produces two views:
  1. Consumer → Capabilities (for subsystem maintainers)
  2. Capabilities → Consumers (for capability developers)

Usage: python3 scripts/generate_impact_matrix.py
Output: docs/matrix/capability-impact-matrix.md
"""
import yaml
from pathlib import Path
from collections import defaultdict

def main():
    root = Path(__file__).resolve().parent.parent
    reg_path = root / "aiPlat-core" / "core" / "capability_registry.yaml"
    if not reg_path.exists():
        reg_path = Path.home() / ".aiplat" / "capability_registry.yaml"

    with open(reg_path) as f:
        data = yaml.safe_load(f)

    consumer_map = defaultdict(list)
    for domain_id, domain in data.get("domains", {}).items():
        for cons in domain.get("consumers_expected", []):
            consumer_map[cons["module"]].append({
                "domain_id": domain_id,
                "section": domain["section"],
                "name": domain["section_name"],
                "caps_count": domain["caps_count"],
                "reason": cons["reason"],
            })

    out = root / "docs" / "matrix" / "capability-impact-matrix.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w") as f:
        f.write(f"# Capability Impact Matrix\n\n")
        f.write(f"> Auto-generated from `capability_registry.yaml`\n")
        f.write(f"> Version: {data['version']} | {data['total_capability_domains']} domains | {data['total_capabilities']} capabilities\n\n")

        # Section 1: Consumer → Capabilities
        f.write("## Consumer-to-Capability Dependencies\n\n")
        for consumer in sorted(consumer_map.keys()):
            f.write(f"### {consumer}\n\n")
            f.write("| Domain | Section | Caps | Reason |\n")
            f.write("|--------|---------|:---:|--------|\n")
            for dep in sorted(consumer_map[consumer], key=lambda x: x["section"]):
                f.write(f"| {dep['domain_id']} | §{dep['section']} {dep['name']} | {dep['caps_count']} | {dep['reason'][:80]} |\n")
            f.write("\n")

        # Section 2: Capabilities → Consumers
        f.write("## Capability-to-Consumer Impact\n\n")
        for domain_id in sorted(data["domains"].keys()):
            domain = data["domains"][domain_id]
            f.write(f"### §{domain['section']} {domain['section_name']} ({domain['caps_count']} caps)\n\n")
            if domain["consumers_expected"]:
                for cons in domain["consumers_expected"]:
                    f.write(f"- **{cons['module']}** — {cons['reason']}\n")
            else:
                f.write("- (no expected consumers)\n")
            f.write("\n")

    print(f"Generated {out} ({len(consumer_map)} consumers mapped)")

if __name__ == "__main__":
    main()
