"""FDE Conformance Pack — 薄路由，经 CoreFacade（附录 N / §9.4 / Core 门）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

router = APIRouter(tags=["fde-conformance-pack"])


@router.get("/conformance-pack")
async def get_conformance_pack_route(
    pilot_domain: Optional[str] = Query(None, description="override pilot domain"),
    catalog_path: Optional[str] = Query(None, description="optional catalog yaml"),
) -> Dict[str, Any]:
    """读取 N24 + 认证证据包。

    Args:
        pilot_domain: 可选试点域覆盖。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import build_conformance_pack

    return build_conformance_pack(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )


@router.get("/conformance-pack/gate")
async def evaluate_conformance_gate_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """证据包结构门槛门（非 24/24 认证）。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import evaluate_conformance_gate

    return evaluate_conformance_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )


@router.get("/conformance-pack/core-ready")
async def evaluate_core_ready_gate_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Core 最小符合集结构门（core_ready ≠ certified / pilot_certified）。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import evaluate_core_ready_gate

    return evaluate_core_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )


@router.get("/conformance-pack/pilot-core-cert")
async def evaluate_pilot_core_certification_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
    approval_record_path: Optional[str] = Query(
        None,
        description="path to pilot Core approval JSON; omit → pilot_certified false",
    ),
) -> Dict[str, Any]:
    """试点 Core 认证裁决；无非作者批准记录时 pilot_certified 恒 false。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
        approval_record_path: 批准记录路径；缺省则不徽章。
    """
    from core.api.core_facade import evaluate_pilot_core_certification

    return evaluate_pilot_core_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=approval_record_path,
    )


@router.get("/conformance-pack/extended-ready")
async def evaluate_extended_ready_gate_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Extended 最小符合集结构门（extended_ready ≠ certified）。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import evaluate_extended_ready_gate

    return evaluate_extended_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )


@router.get("/conformance-pack/pilot-extended-cert")
async def evaluate_pilot_extended_certification_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
    approval_record_path: Optional[str] = Query(
        None,
        description="path to Extended approval JSON; omit → badge false",
    ),
) -> Dict[str, Any]:
    """试点 Extended 认证裁决；无非作者批准时徽章恒 false。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
        approval_record_path: 批准记录路径；缺省则不徽章。
    """
    from core.api.core_facade import evaluate_pilot_extended_certification

    return evaluate_pilot_extended_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=approval_record_path,
    )


@router.get("/conformance-pack/operational-ready")
async def evaluate_operational_ready_gate_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Operational 最小符合集结构门（operational_ready ≠ certified）。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import evaluate_operational_ready_gate

    return evaluate_operational_ready_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )


@router.get("/conformance-pack/pilot-operational-cert")
async def evaluate_pilot_operational_certification_route(
    pilot_domain: Optional[str] = Query(None),
    catalog_path: Optional[str] = Query(None),
    approval_record_path: Optional[str] = Query(
        None,
        description="path to Operational approval JSON; omit → badge false",
    ),
) -> Dict[str, Any]:
    """试点 Operational 认证裁决；无非作者批准时徽章恒 false。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
        approval_record_path: 批准记录路径；缺省则不徽章。
    """
    from core.api.core_facade import evaluate_pilot_operational_certification

    return evaluate_pilot_operational_certification(
        catalog_path=catalog_path,
        pilot_domain=pilot_domain,
        approval_record_path=approval_record_path,
    )
