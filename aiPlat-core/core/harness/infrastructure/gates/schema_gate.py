"""

SchemaGate — JSON Schema enforcement for Agent outputs.



Validates Agent outputs against declared output_schema before passing

to downstream stages. Failed validation triggers re-prompt with specific

error information rather than silent downstream corruption.

"""



from __future__ import annotations



import logging

from dataclasses import dataclass, field

from enum import Enum

from typing import Any, Dict, List, Optional



log = logging.getLogger(__name__)





class SchemaVerdict(str, Enum):

    PASS = "pass"

    FAIL = "fail"

    NO_SCHEMA = "no_schema"  # no output_schema declared — skip check





@dataclass

class SchemaResult:

    verdict: SchemaVerdict

    errors: List[str] = field(default_factory=list)

    details: Dict[str, Any] = field(default_factory=dict)

    retry_hint: str = ""





class SchemaGate:

    """

    JSON Schema enforcement gate.

    

    Checks Agent output against declared output_schema.

    On failure, generates a retry_hint that can be injected back

    into the Agent's context for automatic retry.

    """



    _MAX_RETRIES: int = 3



    @property

    def max_retries(self) -> int:

        """PR #2: 从 ControlProfile 读取门控严格系数，调整最大重试次数。"""

        try:

            from core.harness.meta.profile_registry import get_active_profile

            strictness = get_active_profile().gate_strictness

            return max(1, int(round(self._MAX_RETRIES * strictness)))

        except Exception:

            return self._MAX_RETRIES



    def validate(

        self,

        output: Any,

        output_schema: Optional[Dict[str, Any]] = None,

        *,

        retry_count: int = 0,

    ) -> SchemaResult:

        """

        Validate output against schema.

        

        Args:

            output: The Agent's output (dict, string, etc.)

            output_schema: JSON Schema to validate against

            retry_count: Current retry attempt number

        

        Returns:

            SchemaResult with verdict, errors, and retry hint

        """

        # PR #3: 若 ControlProfile 关闭 schema 校验，直接放行

        try:

            from core.harness.meta.profile_registry import get_active_profile

            if not get_active_profile().require_schema_validation:

                return SchemaResult(verdict=SchemaVerdict.PASS, details={"skipped": "profile"})

        except Exception:

            logging.getLogger(__name__).debug('validate failed', exc_info=True)


        if not output_schema or not isinstance(output_schema, dict):

            return SchemaResult(verdict=SchemaVerdict.NO_SCHEMA)



        errors: List[str] = []



        # 1. Type check — schemas require 'type' field

        schema_type = output_schema.get("type", "object")

        if schema_type == "object" and not isinstance(output, dict):

            errors.append(f"Expected object (dict), got {type(output).__name__}")

        elif schema_type == "string" and not isinstance(output, str):

            errors.append(f"Expected string, got {type(output).__name__}")

        elif schema_type == "array" and not isinstance(output, list):

            errors.append(f"Expected array, got {type(output).__name__}")



        # 2. Required fields check

        required = output_schema.get("required", [])

        if isinstance(required, list) and isinstance(output, dict):

            missing = [f for f in required if f not in output]

            if missing:

                errors.append(f"Missing required field(s): {', '.join(missing)}")



        # 3. Property type checks

        properties = output_schema.get("properties", {})

        if isinstance(properties, dict) and isinstance(output, dict):

            for prop_name, prop_schema in properties.items():

                if prop_name in output:

                    val = output[prop_name]

                    expected_type = prop_schema.get("type", "")

                    if not self._type_matches(val, expected_type):

                        errors.append(

                            f"Field '{prop_name}': expected {expected_type}, "

                            f"got {type(val).__name__} (value: {str(val)[:100]})"

                        )



        # 4. Additional properties check

        if output_schema.get("additionalProperties") is False and isinstance(output, dict):

            allowed = list(properties.keys()) if isinstance(properties, dict) else []

            extra = [k for k in output if k not in allowed]

            if extra:

                errors.append(f"Unexpected field(s): {', '.join(extra)}")



        if not errors:

            return SchemaResult(verdict=SchemaVerdict.PASS, details={"schema": output_schema})



        # PR #3: Schema 校验失败 — 归因到 D6_output

        try:

            from core.harness.meta.profile_registry import set_failure_domain

            set_failure_domain("D6_output")

        except Exception:

            logging.getLogger(__name__).debug('validate failed', exc_info=True)


        # Build retry hint

        retry_hint = self._build_retry_hint(

            errors=errors,

            expected_schema=output_schema,

            actual_type=type(output).__name__,

            retry_count=retry_count,

        )



        return SchemaResult(

            verdict=SchemaVerdict.FAIL,

            errors=errors,

            retry_hint=retry_hint,

            details={"schema": output_schema, "errors": errors, "retry": retry_count},

        )



    def _type_matches(self, value: Any, expected_type: str) -> bool:

        """Check if value matches the JSON Schema type."""

        if expected_type == "string":

            return isinstance(value, str)

        elif expected_type == "number":

            return isinstance(value, (int, float)) and not isinstance(value, bool)

        elif expected_type == "integer":

            return isinstance(value, int) and not isinstance(value, bool)

        elif expected_type == "boolean":

            return isinstance(value, bool)

        elif expected_type == "array":

            return isinstance(value, list)

        elif expected_type == "object":

            return isinstance(value, dict)

        return True  # unknown types pass through



    def _build_retry_hint(

        self,

        errors: List[str],

        expected_schema: Dict[str, Any],

        actual_type: str,

        retry_count: int,

    ) -> str:

        """Build a structured retry message for the Agent."""

        hint = (

            "Your output does not match the required schema. "

            f"Attempt {retry_count + 1}/{self.max_retries}.\n\n"

            f"Errors found:\n"

        )

        for e in errors[:5]:

            hint += f"  - {e}\n"



        # Show expected properties

        required = expected_schema.get("required", [])

        properties = expected_schema.get("properties", {})

        if required or properties:

            hint += "\nExpected output format:\n"

            hint += f"  Type: {actual_type}\n"

            if required:

                hint += f"  Required fields: {', '.join(required)}\n"

            for pname, ps in properties.items():

                ptype = ps.get("type", "any")

                desc = ps.get("description", "")

                marker = " [REQUIRED]" if pname in required else ""

                hint += f"  - {pname}: {ptype}{marker}"

                if desc:

                    hint += f" — {desc}"

                hint += "\n"



        hint += "\nPlease regenerate your output to comply with this schema exactly."

        return hint





_schema_instance: Optional[SchemaGate] = None





def get_schema_gate() -> SchemaGate:

    global _schema_instance

    if _schema_instance is None:

        _schema_instance = SchemaGate()

    return _schema_instance





__all__ = ["SchemaGate", "SchemaResult", "SchemaVerdict", "get_schema_gate"]

