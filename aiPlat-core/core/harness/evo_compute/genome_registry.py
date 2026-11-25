"""Genome Registry — 可进化对象边界登记（Phase 0）。

进程内登记 + 可选落盘到 ``AIPLAT_HOME/evo_compute/genomes/``。
不写生产路由配置；不做 DE/ES。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _home_dir() -> Path:
    """演化计算落盘根目录；不可写时回退临时目录。"""
    import tempfile

    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "genomes"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "genomes"
        p.mkdir(parents=True, exist_ok=True)
        return p


def _validate_genome(genome: Dict[str, Any]) -> Optional[str]:
    """校验 genome 必填字段。

    Args:
        genome: genome 字典。

    Returns:
        错误码或 None。
    """
    gid = str(genome.get("genome_id") or "").strip()
    if not gid:
        return "genome_id_required"
    if not str(genome.get("target") or "").strip():
        return "target_required"
    if not str(genome.get("representation") or "").strip():
        return "representation_required"
    fields = genome.get("fields")
    if not isinstance(fields, list) or not fields:
        return "fields_required"
    if not str(genome.get("owner") or "").strip():
        return "owner_required"
    if not str(genome.get("evaluation_profile") or "").strip():
        return "evaluation_profile_required"
    return None


def register_genome(genome: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """登记 genome；失败关闭。

    Args:
        genome: 含 genome_id/target/fields/owner/evaluation_profile 等。
        persist: 是否写入 AIPLAT_HOME。

    Returns:
        回执含 ``ok`` / ``genome_id``。
    """
    err = _validate_genome(genome or {})
    gid = str((genome or {}).get("genome_id") or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "genome_id": gid,
        "error": "",
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
    }
    if err:
        out["error"] = err
        return out
    record = dict(genome)
    record["genome_id"] = gid
    record["registered_at"] = time.time()
    record.setdefault("mutable", True)
    record.setdefault("rollback", "versioned_config")
    record.setdefault("risk_class", "low")
    _REGISTRY[gid] = record
    if persist:
        path = _home_dir() / f"{gid.replace('/', '_')}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        out["persist_path"] = str(path)
    out["ok"] = True
    out["genome"] = record
    return out


def get_genome(genome_id: str) -> Dict[str, Any]:
    """读取已登记 genome。

    Args:
        genome_id: genome id。
    """
    gid = str(genome_id or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "genome_id": gid,
        "genome": None,
        "error": "",
        "g0_foundation": True,
        "certified": False,
    }
    if not gid:
        out["error"] = "genome_id_required"
        return out
    if gid in _REGISTRY:
        out["ok"] = True
        out["genome"] = dict(_REGISTRY[gid])
        return out
    path = _home_dir() / f"{gid.replace('/', '_')}.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out["error"] = "persist_corrupt"
            return out
        _REGISTRY[gid] = data
        out["ok"] = True
        out["genome"] = dict(data)
        return out
    out["error"] = "not_found"
    return out


def list_genomes() -> Dict[str, Any]:
    """列出已登记 genome id。"""
    # 合并磁盘
    for path in _home_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            gid = str(data.get("genome_id") or "").strip()
            if gid:
                _REGISTRY.setdefault(gid, data)
        except (OSError, json.JSONDecodeError):
            continue
    ids = sorted(_REGISTRY.keys())
    return {
        "ok": True,
        "genome_ids": ids,
        "count": len(ids),
        "g0_foundation": True,
        "certified": False,
    }


def clear_registry_for_tests() -> None:
    """测试用：清空进程内登记（不删磁盘）。"""
    _REGISTRY.clear()
