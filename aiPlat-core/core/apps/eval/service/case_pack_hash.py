"""Canonical case/pack/manifest hashes for Eval Case Pack (design §钉4 / 附录 B).

Algorithm: include-fields → sort list fields → json.dumps(sort_keys, ensure_ascii=False,
separators=(',', ':')) → UTF-8 → ``sha256:`` + hex.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

CASE_HASH_KEYS = (
    "case_id",
    "prompt",
    "rubric",
    "category",
    "tags",
    "difficulty",
    "applies_to",
    "requires",
    "oracle",
    "expected_tools",
    "forbidden_tools",
    "expected_steps",
    "risk_level",
    "session_group",
    "holdout",
    "provenance",
)

_LIST_SORT_KEYS = frozenset({"tags", "expected_tools", "forbidden_tools"})


def canonical_json_bytes(obj: Any) -> bytes:
    """canonical_json_bytes。

    Args:
        obj: obj 参数。
    """
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """sha256_hex。

    Args:
        data: data 参数。
    """
    return "sha256:" + hashlib.sha256(data).hexdigest()


def case_hash_payload(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the exact object that is hashed (review/agent_id excluded).

    Args:
        case: case 参数。
    """
    out: Dict[str, Any] = {}
    for key in CASE_HASH_KEYS:
        val = case.get(key)
        if key in _LIST_SORT_KEYS:
            raw = val if isinstance(val, list) else []
            out[key] = sorted(str(x) for x in raw)
        elif key == "expected_steps":
            out[key] = list(val) if isinstance(val, list) else []
        elif key == "provenance":
            prov = val if isinstance(val, Mapping) else {}
            out[key] = {
                "generator": prov.get("generator"),
                "generator_version": prov.get("generator_version"),
                "seed": prov.get("seed"),
            }
        elif key in ("applies_to", "requires", "oracle", "rubric"):
            out[key] = dict(val) if isinstance(val, Mapping) else (val if val is not None else {})
        elif key == "holdout":
            out[key] = bool(val)
        elif key == "session_group":
            out[key] = val if val is not None else None
        else:
            out[key] = val
    return out


def compute_case_hash(case: Mapping[str, Any]) -> str:
    """计算 case_hash。

    Args:
        case: case 参数。
    """
    return sha256_hex(canonical_json_bytes(case_hash_payload(case)))


def compute_pack_hash(
    *,
    pack_id: str,
    version: str,
    kind: str,
    claim_eligible: bool,
    scope: str,
    object_types: Sequence[str],
    cases: Sequence[Mapping[str, Any]],
) -> str:
    """计算 pack_hash。

    Args:
        pack_id: pack 标识。
        version: 版本号。
        kind: kind 参数。
        claim_eligible: claim_eligible 参数。
        scope: scope 参数。
        object_types: object_types 参数。
        cases: 用例列表。
    """
    case_hashes = sorted(
        (
            {
                "case_id": str(c.get("case_id") or ""),
                "hash": compute_case_hash(c),
            }
            for c in cases
        ),
        key=lambda row: row["case_id"],
    )
    payload = {
        "claim_eligible": bool(claim_eligible),
        "case_hashes": case_hashes,
        "kind": str(kind),
        "object_types": sorted(str(x) for x in object_types),
        "pack_id": str(pack_id),
        "scope": str(scope),
        "version": str(version),
    }
    return sha256_hex(canonical_json_bytes(payload))


def compute_manifest_hash(manifest: Sequence[Mapping[str, Any]]) -> str:
    """Hash sample_manifest entries sorted by case_id (stable execution fingerprint input).

    Args:
        manifest: 清单 dict。
    """
    rows: List[Dict[str, Any]] = []
    for item in manifest:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "case_id": str(item.get("case_id") or ""),
                "hash": str(item.get("hash") or ""),
                "pack_id": str(item.get("pack_id") or ""),
                "pack_version": str(item.get("pack_version") or ""),
                "session_group": item.get("session_group"),
            }
        )
    rows.sort(key=lambda r: r["case_id"])
    return sha256_hex(canonical_json_bytes(rows))


def compute_plan_id_v2(
    *,
    contract: Mapping[str, Any],
    purpose: Sequence[str],
    selection: Mapping[str, Any],
    pack_refs: Sequence[Mapping[str, Any]],
    manifest_hash: str,
    plan_schema: str,
) -> str:
    """计算 plan_id_v2。

    Args:
        contract: contract 参数。
        purpose: purpose 参数。
        selection: selection 参数。
        pack_refs: pack_refs 参数。
        manifest_hash: manifest_hash 参数。
        plan_schema: plan_schema 参数。
    """
    blob = {
        "manifest_hash": manifest_hash,
        "object_id": contract.get("object_id"),
        "object_type": contract.get("object_type"),
        "object_version": contract.get("object_version"),
        "capabilities": contract.get("capabilities"),
        "permissions": contract.get("permissions"),
        "pack_refs": list(pack_refs),
        "plan_schema": plan_schema,
        "purpose": list(purpose),
        "selection": dict(selection),
    }
    return "plan-" + hashlib.sha256(canonical_json_bytes(blob)).hexdigest()[:16]


def compute_execution_fingerprint(
    *,
    plan_id: str,
    manifest_hash: str,
    runner_id: str = "",
    judge_oracle_version: str = "",
    model: Optional[str] = None,
    run_key: str = "",
) -> str:
    """计算 execution_fingerprint。

    Args:
        plan_id: plan 标识。
        manifest_hash: manifest_hash 参数。
        runner_id: runner 标识。
        judge_oracle_version: judge_oracle_version 参数。
        model: 模型名。
        run_key: run_key 参数。
    """
    payload = {
        "judge_oracle_version": judge_oracle_version,
        "manifest_hash": manifest_hash,
        "model": model,
        "plan_id": plan_id,
        "run_key": run_key,
        "runner_id": runner_id,
    }
    return "exec-" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:16]
