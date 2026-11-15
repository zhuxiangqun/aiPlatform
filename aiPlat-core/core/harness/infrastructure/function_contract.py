"""FunctionContract — 附录 C.3 最小契约（无副作用函数）。

职责：定义 Function 的机器可校验合同；与 ActionContract 对称但禁止副作用。
非目标：不实现 Interface、ObjectSet、管理端 publish 流水线。
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class FunctionContractModel(BaseModel):
    """附录 C.3 FunctionContract 必填字段。"""

    model_config = {"extra": "forbid"}

    function_id: str = Field(..., min_length=1, max_length=160)
    version: str = Field(..., min_length=1, max_length=32)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    deterministic: bool = True
    side_effects: bool = False
    required_permissions: List[str] = Field(default_factory=list)
    timeout_ms: int = Field(2000, ge=1, le=120_000)
    handler: str = Field(..., min_length=1)
    label: str = ""
    description: str = ""

    @field_validator("handler")
    @classmethod
    def _validate_handler_security(cls, v: str) -> str:
        """Handler 模块白名单，防止任意代码执行。

        Args:
            v: ``module.path:function_name``。
        """
        if not v:
            raise ValueError("handler is required")
        ALLOWED_PREFIXES = (
            "core.harness.infrastructure.builtin_functions",
            "custom_handlers",
        )
        module_part = v.rsplit(":", 1)[0] if ":" in v else v
        if not any(
            module_part == p or module_part.startswith(p + ".") for p in ALLOWED_PREFIXES
        ):
            raise ValueError(
                f"Handler '{v}' not in allowed modules. "
                f"Module prefix must match: {ALLOWED_PREFIXES}"
            )
        DANGEROUS = ("os.", "sys.", "subprocess.", "shutil.", "builtins.")
        if any(kw in v for kw in DANGEROUS):
            raise ValueError(f"Handler '{v}' contains dangerous module reference")
        return v
