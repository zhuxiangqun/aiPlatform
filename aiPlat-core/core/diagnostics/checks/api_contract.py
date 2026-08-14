"""API 响应结构运行时抽样 — 热度加权抽样 + 响应 schema 校验。

使用 MetricsCollector.get_top_endpoints() 获取过去 1h 流量 Top-5 端点，
发起 HTTP GET 请求并校验响应结构。

防御措施：
  - 超时 2s，失败不阻塞调度器
  - 仅做结构性检查（HTTP 200 + JSON 可解析），不做深度业务逻辑验证
"""

import json
from typing import Any, Dict, List


async def check_api_contract() -> Dict[str, Any]:
    try:
        from core.harness.observability.metrics import get_top_endpoints
        top_eps = get_top_endpoints(limit=5)
    except Exception:
        return {"status": "warn", "reason": "MetricsCollector unavailable"}

    if not top_eps:
        return {"status": "pass", "note": "no endpoints with recent traffic"}

    mismatches: List[Dict[str, Any]] = []
    server_port = int(__import__("os").environ.get("AIPLAT_SERVER_PORT", "8000"))

    for ep in top_eps:
        try:
            import aiohttp
            url = f"http://127.0.0.1:{server_port}{ep}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status != 200:
                        mismatches.append({"endpoint": ep, "issue": f"HTTP {resp.status}"})
                        continue
                    try:
                        await resp.json()
                    except Exception:
                        mismatches.append({"endpoint": ep, "issue": "response not valid JSON"})
        except Exception:
            mismatches.append({"endpoint": ep, "issue": "timeout or connection error"})

    if mismatches:
        return {"status": "warn", "mismatches": mismatches}
    return {"status": "pass", "endpoints_checked": len(top_eps)}
