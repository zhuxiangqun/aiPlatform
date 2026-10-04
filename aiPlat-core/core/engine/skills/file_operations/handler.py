"""Real file I/O for the file_operations skill — single path through FileOperationsTool."""
from __future__ import annotations

from typing import Any, Dict


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    from core.apps.tools.base import get_tool_registry
    from core.harness.syscalls.tool import sys_tool_call

    args = dict(params or {})
    op = str(args.get("operation") or args.get("action") or "").strip().lower()
    path = str(args.get("path") or "").strip()
    if not op:
        if args.get("content") is not None and path:
            args["operation"] = "write"
        else:
            return {
                "error": (
                    "missing_operation: file_operations requires operation="
                    "read|write|list|delete and path (do not invent writes)"
                )
            }
    tool = get_tool_registry().get("file_operations")
    if tool is None:
        return {"error": "file_operations tool is not registered"}
    result = await sys_tool_call(tool, args)
    success = bool(getattr(result, "success", False))
    err = getattr(result, "error", None)
    output = getattr(result, "output", None)
    if not success:
        return {"error": err or "file_operations tool failed", "output": output}
    return {"success": True, "result": output}
