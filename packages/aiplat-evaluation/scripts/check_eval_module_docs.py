#!/usr/bin/env python3
"""Evaluation module doc consistency gate (P0-4).

Checks module.yaml pointers, contract shim SSOT resolution, living-doc
SSOT references, and process_split policy vs runtime field-name honesty.

Does not Accept ADRs or flip authorize flags.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MOD = ROOT / "docs" / "products" / "five-products" / "modules" / "evaluation"
MOD_YAML = MOD / "module.yaml"
SHIM = MOD / "contracts" / "validate_sample.py"
SSOT = ROOT / "packages" / "aiplat-evaluation" / "contracts" / "validate_sample.py"


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception as exc:  # noqa: BLE001 — surface parse failure to gate
        raise SystemExit(f"FAIL cannot parse {path}: {exc}") from exc
    raise SystemExit(f"FAIL empty/non-dict YAML: {path}")


def main() -> int:
    """校验 evaluation 模块文档与契约路径一致性。"""
    errors: list[str] = []
    if not MOD_YAML.is_file():
        errors.append(f"missing {MOD_YAML.relative_to(ROOT)}")
        print("FAIL eval module docs:")
        for e in errors:
            print(f" - {e}")
        return 1

    data = _load_yaml(MOD_YAML)
    for c in data.get("contracts") or []:
        p = ROOT / str(c)
        if not p.is_file():
            errors.append(f"module.yaml contracts missing: {c}")

    mig = (data.get("migrations") or {}).get("path")
    if not mig:
        errors.append("module.yaml migrations.path is null/empty")
    else:
        mp = ROOT / str(mig)
        if not mp.is_dir():
            errors.append(f"module.yaml migrations.path missing dir: {mig}")
        elif not list(mp.glob("*.sql")):
            errors.append(f"module.yaml migrations.path has no *.sql: {mig}")

    adr = data.get("adr_for_a3")
    if not adr:
        errors.append("module.yaml adr_for_a3 is null/empty")
    elif not (ROOT / str(adr)).is_file():
        errors.append(f"module.yaml adr_for_a3 missing: {adr}")

    if data.get("current_delivery") != "D1":
        errors.append(
            f"module.yaml current_delivery={data.get('current_delivery')!r} "
            "(expected D1 / D1c honesty; D2 ops pack ≠ delivery upgrade)"
        )

    if not SSOT.is_file():
        errors.append(f"missing contracts SSOT: {SSOT.relative_to(ROOT)}")
    if not SHIM.is_file():
        errors.append(f"missing contracts shim: {SHIM.relative_to(ROOT)}")
    else:
        # Resolve the same relative climb the shim uses (parents[6] → repo root).
        resolved = Path(SHIM).resolve().parents[6] / "packages" / "aiplat-evaluation" / "contracts" / "validate_sample.py"
        if resolved.resolve() != SSOT.resolve():
            errors.append(
                f"shim parents[6] resolves to {resolved}, expected {SSOT}"
            )

    # Living docs must prefer SSOT validate command (legacy shim may be commented).
    for rel in (
        "docs/products/five-products/modules/evaluation/README.md",
        "docs/products/five-products/modules/evaluation/EVAL_PROTOCOL.md",
        "docs/products/five-products/modules/evaluation/MODULE.md",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "packages/aiplat-evaluation/contracts/validate_sample.py" not in text:
            errors.append(f"{rel}: missing SSOT validate_sample.py reference")

    # B4 staging draft must be called out in lifecycle (not counted as archived stub).
    life = (
        ROOT
        / "reports"
        / "products"
        / "five-products"
        / "ops"
        / "EVAL_DOCS_LIFECYCLE.md"
    )
    if life.is_file():
        lt = life.read_text(encoding="utf-8")
        if "ENGINEERING_UNFREEZE_EVAL_A3_B4_STAGING" not in lt:
            errors.append("EVAL_DOCS_LIFECYCLE.md missing A3_B4_STAGING draft note")
        if "17" not in lt:
            errors.append("EVAL_DOCS_LIFECYCLE.md should mention ops-root count 17")
    else:
        errors.append("missing reports/products/five-products/ops/EVAL_DOCS_LIFECYCLE.md")

    for rel in (
        "packages/aiplat-evaluation/docs/a3/STORE_SURFACE_V0.md",
        "packages/aiplat-evaluation/docs/a3/G2B_RE_REVIEW_PROCEDURE.md",
        "packages/aiplat-evaluation/docs/a3/P1_CANONICAL.md",
        "packages/aiplat-evaluation/docs/a3/P2_STAGING_ROADMAP.md",
    ):
        if not (ROOT / rel).is_file():
            errors.append(f"missing living doc: {rel}")

    canon = (ROOT / "packages/aiplat-evaluation/docs/a3/P1_CANONICAL.md").read_text(
        encoding="utf-8"
    )
    if "v1.3" not in canon:
        errors.append("P1_CANONICAL.md should cite composite_version v1.3")

    # Policy vs runtime process_split names must stay distinct (machine gate).
    # Policy: process_split_policy_authorized
    # Runtime/Checklist/PREP/Chart: process_split_authorized / a3_process_split_authorized
    split = ROOT / "packages" / "aiplat-evaluation" / "docs" / "a3" / "SPLIT_CHECKLIST.md"
    phase3 = (
        ROOT
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "PHASE3_PROCESS_SPLIT_AUTHORIZE.md"
    )
    prep = ROOT / "packages" / "aiplat-evaluation" / "docs" / "a3" / "PREP_STATUS.json"
    for path in (split, phase3):
        if not path.is_file():
            errors.append(f"missing process_split honesty doc: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if "process_split_policy_authorized" not in text:
            errors.append(
                f"{path.relative_to(ROOT)}: missing process_split_policy_authorized"
            )
        has_runtime_true = bool(
            re.search(r"(?<!policy_)process_split_authorized:\s*true", text)
        )
        has_runtime_false = bool(
            re.search(r"(?<!policy_)process_split_authorized:\s*false", text)
        )
        if has_runtime_true and has_runtime_false:
            errors.append(
                f"{path.relative_to(ROOT)}: process_split_authorized true+false "
                "in one file — use process_split_policy_authorized for policy"
            )

    if phase3.is_file():
        p3 = phase3.read_text(encoding="utf-8")
        # Markdown may bold 禁止 → 「**禁止**共用裸字段名」.
        if "共用裸字段名" not in p3:
            errors.append(
                "PHASE3_PROCESS_SPLIT_AUTHORIZE.md: missing naming rule "
                "「共用裸字段名」(policy vs runtime)"
            )
        # Status table must keep runtime false while policy may be true.
        if not re.search(
            r"运行时\s*`process_split_authorized`\s*\|\s*\*\*false\*\*",
            p3,
        ):
            errors.append(
                "PHASE3_PROCESS_SPLIT_AUTHORIZE.md: runtime "
                "`process_split_authorized` must remain **false** in status table"
            )

    if not prep.is_file():
        errors.append(f"missing {prep.relative_to(ROOT)}")
    else:
        try:
            prep_data = json.loads(prep.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"PREP_STATUS.json invalid JSON: {exc}")
            prep_data = {}
        if not isinstance(prep_data, dict):
            errors.append("PREP_STATUS.json must be a JSON object")
        elif prep_data.get("process_split_authorized") is not False:
            errors.append(
                "PREP_STATUS.json process_split_authorized must be false "
                f"(got {prep_data.get('process_split_authorized')!r}); "
                "policy uses process_split_policy_authorized"
            )

    if errors:
        print("FAIL eval module docs:")
        for e in errors:
            print(f" - {e}")
        return 1

    n_contracts = len(data.get("contracts") or [])
    print(
        f"OK eval module docs contracts={n_contracts} "
        f"migrations={mig} adr={adr} delivery={data.get('current_delivery')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
