#!/usr/bin/env python3
"""Phase 43: Generate capability impact matrix from registry YAML.

Produces two views:
  1. Consumer → Capabilities (for subsystem maintainers)
  2. Capabilities → Consumers (for capability developers)

Usage:
  python3 scripts/generate_impact_matrix.py              # write docs/matrix/...
  python3 scripts/generate_impact_matrix.py --ci         # temp full regenerate + diff vs committed
  python3 scripts/generate_impact_matrix.py --check      # alias of --ci

Public API:
  load_registry(root) -> dict
  render_matrix_markdown(data) -> str
  write_matrix(path, data) -> Path
"""
from __future__ import annotations

import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_registry(root: Optional[Path] = None) -> Dict[str, Any]:
    root = root or Path(__file__).resolve().parent.parent
    reg_path = root / "aiPlat-core" / "core" / "capability_registry.yaml"
    if not reg_path.exists():
        reg_path = Path.home() / ".aiplat" / "capability_registry.yaml"
    with open(reg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_matrix_markdown(data: Dict[str, Any]) -> str:
    """Render full impact matrix markdown from registry data (no I/O)."""
    consumer_map: Dict[str, list] = defaultdict(list)
    domains = data.get("domains") or {}
    for domain_id, domain in domains.items():
        for cons in domain.get("consumers_expected") or []:
            consumer_map[cons["module"]].append({
                "domain_id": domain_id,
                "section": domain.get("section"),
                "name": domain.get("section_name"),
                "caps_count": domain.get("caps_count"),
                "reason": cons.get("reason") or "",
            })

    n_domains = len(domains)
    n_caps = sum(int(d.get("caps_count") or 0) for d in domains.values())
    n_symbols = sum(len(d.get("provides") or []) for d in domains.values())

    lines = []
    lines.append("# Capability Impact Matrix")
    lines.append("")
    lines.append("> Auto-generated from `capability_registry.yaml`")
    lines.append(
        f"> Version: {data.get('version', '?')} | {n_domains} domains | "
        f"{n_caps} capabilities (caps_count) | {n_symbols} symbols (provides)"
    )
    lines.append("")
    lines.append(
        "> 口径：`caps_count` 应对齐 `len(provides)`（登记公开符号数）；"
        "勿与 `AIPLAT_CAPABILITIES.md` 产品能力行计数混算。"
    )
    lines.append("")

    lines.append("## Consumer-to-Capability Dependencies")
    lines.append("")
    for consumer in sorted(consumer_map.keys()):
        lines.append(f"### {consumer}")
        lines.append("")
        lines.append("| Domain | Section | Caps | Reason |")
        lines.append("|--------|---------|:---:|--------|")
        for dep in sorted(consumer_map[consumer], key=lambda x: (x["section"] is None, x["section"] or 0)):
            reason = (dep["reason"] or "")[:80]
            lines.append(
                f"| {dep['domain_id']} | §{dep['section']} {dep['name']} | "
                f"{dep['caps_count']} | {reason} |"
            )
        lines.append("")

    lines.append("## Capability-to-Consumer Impact")
    lines.append("")
    for domain_id in sorted(domains.keys()):
        domain = domains[domain_id]
        lines.append(
            f"### §{domain.get('section')} {domain.get('section_name')} "
            f"({domain.get('caps_count')} caps)"
        )
        lines.append("")
        consumers = domain.get("consumers_expected") or []
        if consumers:
            for cons in consumers:
                lines.append(f"- **{cons['module']}** — {cons.get('reason', '')}")
        else:
            lines.append("- (no expected consumers)")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_matrix(out_path: Path, data: Optional[Dict[str, Any]] = None, root: Optional[Path] = None) -> Path:
    if data is None:
        data = load_registry(root or Path(__file__).resolve().parent.parent)
    text = render_matrix_markdown(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path


def check_matrix_fresh(root: Optional[Path] = None) -> int:
    """Regenerate into a temp file and diff against the committed matrix. Return 0/1."""
    root = root or Path(__file__).resolve().parent.parent
    data = load_registry(root)
    expected = render_matrix_markdown(data)
    committed = root / "docs" / "matrix" / "capability-impact-matrix.md"
    if not committed.is_file():
        print(f"ERROR: missing committed matrix {committed}")
        return 1
    actual = committed.read_text(encoding="utf-8")
    if actual == expected:
        print(f"OK: matrix matches registry render ({committed})")
        return 0
    # Write temp for debugging
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tf:
        tf.write(expected)
        tmp = tf.name
    print(f"ERROR: docs/matrix/capability-impact-matrix.md is stale vs capability_registry.yaml")
    print(f"  regenerated: {tmp}")
    print(f"  committed:   {committed}")
    print("  Fix: python3 scripts/generate_impact_matrix.py")
    # Show a short unified-style hint
    a_lines = actual.splitlines()
    e_lines = expected.splitlines()
    diffs = 0
    for i, (a, e) in enumerate(zip(a_lines, e_lines)):
        if a != e:
            print(f"  first diff at line {i + 1}:")
            print(f"    - {a[:120]}")
            print(f"    + {e[:120]}")
            diffs += 1
            break
    if len(a_lines) != len(e_lines):
        print(f"  length: committed={len(a_lines)} expected={len(e_lines)}")
    return 1


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    root = Path(__file__).resolve().parent.parent
    if "--ci" in argv or "--check" in argv:
        return check_matrix_fresh(root)

    data = load_registry(root)
    out = root / "docs" / "matrix" / "capability-impact-matrix.md"
    write_matrix(out, data)
    domains = data.get("domains") or {}
    n_cons = len({
        c["module"]
        for d in domains.values()
        for c in (d.get("consumers_expected") or [])
    })
    print(f"Generated {out} ({n_cons} consumers mapped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
