#!/usr/bin/env python3
"""Offline ontology seed readiness (no server).

Validates ``aiPlat-core/workspace_seeds/ontologies/*.yaml`` parse, and
best-effort copies into ``$AIPLAT_HOME/ontologies`` when writable.
Exit 0 when workspace seeds are present and valid YAML.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--seed-dir",
        default="aiPlat-core/workspace_seeds/ontologies",
        help="Workspace ontology seed directory",
    )
    ap.add_argument(
        "--install",
        action="store_true",
        help="Best-effort copy into ~/.aiplat/ontologies (or AIPLAT_HOME)",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    seed_dir = (root / args.seed_dir).resolve()
    if not seed_dir.is_dir():
        print(f"FAIL: seed dir missing: {seed_dir}", file=sys.stderr)
        return 1

    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None

    files = sorted(seed_dir.glob("*.yaml"))
    if not files:
        print(f"FAIL: no *.yaml in {seed_dir}", file=sys.stderr)
        return 1

    ok = []
    bad = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            if yaml is not None:
                data = yaml.safe_load(text)
                if data is None or not isinstance(data, (dict, list)):
                    raise ValueError("empty or non-mapping YAML")
            elif not text.strip():
                raise ValueError("empty file")
            ok.append(f.name)
        except Exception as e:
            bad.append({"file": f.name, "error": str(e)})

    installed = 0
    install_err = ""
    if args.install and ok:
        home = Path(os.path.expanduser(os.environ.get("AIPLAT_HOME") or "~/.aiplat"))
        dest = home / "ontologies"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            for name in ok:
                shutil.copy2(seed_dir / name, dest / name)
                installed += 1
        except Exception as e:
            install_err = str(e)

    report = {
        "ok": len(bad) == 0,
        "seed_dir": str(seed_dir),
        "valid_count": len(ok),
        "invalid": bad,
        "files": ok,
        "installed": installed,
        "install_error": install_err or None,
    }
    if args.json:
        import json

        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"ontology seeds: valid={len(ok)} invalid={len(bad)} dir={seed_dir}")
        if bad:
            for b in bad:
                print(f"  FAIL {b['file']}: {b['error']}")
        if args.install:
            if install_err:
                print(f"WARN: install skipped: {install_err}")
            else:
                print(f"installed {installed} → {os.path.expanduser(os.environ.get('AIPLAT_HOME') or '~/.aiplat')}/ontologies")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
