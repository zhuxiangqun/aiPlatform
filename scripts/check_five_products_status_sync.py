#!/usr/bin/env python3
"""Assert reports/five-products/STATUS.md mirrors capabilities.manifest.yaml.

Fails if Autonomy / Delivery / delivery_mode / hard gates disagree.
Does not Accept ADRs or flip authorize flags.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "capabilities.manifest.yaml"
STATUS = ROOT / "reports/five-products/STATUS.md"


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Minimal fallback: not expected in-repo (PyYAML normally present)
    raise SystemExit(f"FAIL: cannot parse YAML {path}")


def _cell(s: str) -> str:
    return re.sub(r"\*+", "", s).strip()


def _parse_status_table(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("| Capability"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 4:
                continue
            cap = _cell(parts[0]).lower()
            if not cap or cap == "capability":
                continue
            rows[cap] = {
                "autonomy": _cell(parts[1]),
                "delivery": _cell(parts[2]),
                "mode": _cell(parts[3]).lower(),
            }
            continue
        if in_table and not line.startswith("|"):
            break
    return rows


def _parse_hard_gates(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in (
        "cutover_authorized",
        "process_split_authorized",
        "d3_production_authorized",
    ):
        # Table cells look like: | `cutover_authorized` | **false** |
        m = re.search(
            rf"{key}`?\s*\|\s*\**\s*(true|false)\s*\**",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            out[key] = m.group(1).lower()
    return out


def main() -> int:
    errors: list[str] = []
    data = _load_yaml(MANIFEST)
    caps = {c["id"]: c for c in (data.get("capabilities") or []) if isinstance(c, dict)}
    status_text = STATUS.read_text(encoding="utf-8")
    rows = _parse_status_table(status_text)
    gates = _parse_hard_gates(status_text)

    for cid, c in caps.items():
        row = rows.get(cid)
        if not row:
            errors.append(f"STATUS missing capability row: {cid}")
            continue
        want_a = str(c.get("current_autonomy", "")).split()[0]
        want_d = str(c.get("current_delivery", "")).split()[0]
        want_mode = str(c.get("delivery_mode", "")).lower()
        got_a = re.search(r"A\d", row["autonomy"])
        got_d = re.search(r"D\d", row["delivery"])
        if not got_a or got_a.group(0) != want_a:
            errors.append(f"{cid}: autonomy STATUS={row['autonomy']!r} manifest={want_a}")
        if not got_d or got_d.group(0) != want_d:
            errors.append(f"{cid}: delivery STATUS={row['delivery']!r} manifest={want_d}")
        if want_mode and want_mode not in row["mode"]:
            errors.append(
                f"{cid}: delivery_mode STATUS={row['mode']!r} must contain {want_mode!r}"
            )

    # Hard gates from manifest
    expect_false = {
        "cutover_authorized": bool(caps.get("aiplat", {}).get("cutover_authorized")),
        "d3_production_authorized": bool(
            caps.get("pi", {}).get("d3_production_authorized")
        ),
        "process_split_authorized": bool(
            caps.get("ontology", {}).get("process_split_authorized")
        )
        or bool(caps.get("evaluation", {}).get("process_split_authorized")),
    }
    for key, authorized in expect_false.items():
        want = "true" if authorized else "false"
        got = gates.get(key)
        if got is None:
            errors.append(f"STATUS missing hard gate cell for {key}")
        elif got != want:
            errors.append(f"hard gate {key}: STATUS={got} manifest={want}")

    # cohost must be called out as D1c (not independent deploy)
    if "cohost" in status_text.lower() and "d1c" not in status_text.lower():
        errors.append("STATUS must label cohost delivery as D1c (not independent deploy)")

    if errors:
        print("FAIL five_products STATUS↔manifest sync:")
        for e in errors:
            print(f" - {e}")
        return 1

    print(
        f"OK STATUS↔manifest sync caps={len(caps)} "
        f"gates_cutover={gates.get('cutover_authorized')} "
        f"process_split={gates.get('process_split_authorized')} "
        f"d3={gates.get('d3_production_authorized')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
