"""FDE Conformance Pack — 薄路由，经 CoreFacade（附录 N / §9.4）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(tags=["fde-conformance-pack"])


@router.get("/conformance-pack")
async def get_conformance_pack_route(
    pilot_domain: Optional[str] = Query(None, description="override pilot domain"),
    catalog_path: Optional[str] = Query(None, description="optional catalog yaml"),
):
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
):
    """证据包结构门槛门（非 24/24 认证）。

    Args:
        pilot_domain: 可选试点域。
        catalog_path: 可选目录路径。
    """
    from core.api.core_facade import evaluate_conformance_gate

    return evaluate_conformance_gate(
        catalog_path=catalog_path, pilot_domain=pilot_domain
    )
