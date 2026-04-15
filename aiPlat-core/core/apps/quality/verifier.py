"""
Result Verifier

Verifies execution results against specifications.
"""

import json
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .types import (
    VerificationType,
    VerificationSpec,
    VerificationResult,
)


class ResultVerifier:
    """Result Verifier - Validates execution results"""

    def __init__(self):
        pass

    async def verify(
        self,
        result: Any,
        spec: VerificationSpec
    ) -> VerificationResult:
        """Verify result against specification"""
        if spec.type == VerificationType.ASSERTION:
            return await self._verify_assertion(result, spec.spec)
        elif spec.type == VerificationType.SCHEMA:
            return await self._verify_schema(result, spec.spec)
        elif spec.type == VerificationType.REGRESSION:
            return await self._verify_regression(result, spec.spec)
        elif spec.type == VerificationType.THRESHOLD:
            return await self._verify_threshold(result, spec.spec)
        else:
            return VerificationResult(
                passed=False,
                message=f"Unknown verification type: {spec.type}"
            )

    async def _verify_assertion(
        self,
        result: Any,
        spec: Dict[str, Any]
    ) -> VerificationResult:
        """Verify using assertion logic"""
        expression = spec.get("expression", "")
        
        try:
            context = {"result": result, **self._flatten_dict(result)}
            passed = self._eval_expression(expression, context)
            
            return VerificationResult(
                passed=passed,
                message=f"Assertion '{expression}' {'passed' if passed else 'failed'}",
                details={"expression": expression, "result": result}
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                message=f"Assertion evaluation error: {str(e)}",
                details={"expression": expression, "error": str(e)}
            )

    async def _verify_schema(
        self,
        result: Any,
        spec: Dict[str, Any]
    ) -> VerificationResult:
        """Verify using JSON schema"""
        schema = spec.get("schema", {})
        
        try:
            errors = self._validate_json_schema(result, schema)
            
            if errors:
                return VerificationResult(
                    passed=False,
                    message=f"Schema validation failed: {len(errors)} error(s)",
                    details={"errors": errors}
                )
            
            return VerificationResult(
                passed=True,
                message="Schema validation passed"
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                message=f"Schema validation error: {str(e)}",
                details={"error": str(e)}
            )

    async def _verify_regression(
        self,
        result: Any,
        spec: Dict[str, Any]
    ) -> VerificationResult:
        """Verify against historical results"""
        baseline = spec.get("baseline", {})
        tolerance = spec.get("tolerance", 0.0)
        
        differences = self._compare_results(result, baseline)
        
        significant_diffs = [
            d for d in differences 
            if abs(d.get("diff_ratio", 0)) > tolerance
        ]
        
        if significant_diffs:
            return VerificationResult(
                passed=False,
                message=f"Regression detected: {len(significant_diffs)} significant difference(s)",
                details={"differences": significant_diffs[:5]}
            )
        
        return VerificationResult(
            passed=True,
            message="Regression check passed",
            details={"differences": differences}
        )

    async def _verify_threshold(
        self,
        result: Any,
        spec: Dict[str, Any]
    ) -> VerificationResult:
        """Verify numeric thresholds"""
        metric = spec.get("metric", "")
        min_value = spec.get("min")
        max_value = spec.get("max")
        
        value = self._get_nested_value(result, metric)
        
        if value is None:
            return VerificationResult(
                passed=False,
                message=f"Metric '{metric}' not found in result"
            )
        
        try:
            value = float(value)
            
            if min_value is not None and value < min_value:
                return VerificationResult(
                    passed=False,
                    message=f"Value {value} below minimum {min_value}",
                    details={"value": value, "min": min_value}
                )
            
            if max_value is not None and value > max_value:
                return VerificationResult(
                    passed=False,
                    message=f"Value {value} above maximum {max_value}",
                    details={"value": value, "max": max_value}
                )
            
            return VerificationResult(
                passed=True,
                message=f"Value {value} within threshold [{min_value}, {max_value}]",
                details={"value": value, "min": min_value, "max": max_value}
            )
        except (TypeError, ValueError):
            return VerificationResult(
                passed=False,
                message=f"Cannot convert value to number: {value}"
            )

    def _eval_expression(self, expr: str, context: Dict[str, Any]) -> bool:
        """Evaluate simple boolean expression"""
        expr = expr.replace("==", "=")
        
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.<>=!&|() ")
        if any(c not in allowed_chars for c in expr):
            raise ValueError("Invalid characters in expression")
        
        for key, value in context.items():
            if isinstance(value, str):
                expr = expr.replace(key, f'"{value}"')
            elif isinstance(value, (int, float, bool)):
                expr = expr.replace(key, str(value))
        
        return eval(expr, {"__builtins__": {}}, {})

    def _flatten_dict(self, d: Any, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """Flatten nested dictionary"""
        if not isinstance(d, dict):
            return {parent_key: d} if parent_key else {}
        
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(self._flatten_dict(v, new_key, sep).items())
        return dict(items)

    def _validate_json_schema(self, data: Any, schema: Dict[str, Any]) -> List[str]:
        """Simple JSON schema validation"""
        errors = []
        
        required = schema.get("required", [])
        if isinstance(data, dict):
            for field in required:
                if field not in data:
                    errors.append(f"Missing required field: {field}")
        
        properties = schema.get("properties", {})
        if isinstance(data, dict):
            for key, value in data.items():
                if key in properties:
                    prop_schema = properties[key]
                    prop_type = prop_schema.get("type")
                    
                    if prop_type and not self._check_type(value, prop_type):
                        errors.append(f"Field '{key}' has wrong type: expected {prop_type}")
        
        return errors

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
        }
        
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        
        return isinstance(value, expected)

    def _compare_results(
        self,
        current: Any,
        baseline: Any,
        path: str = ""
    ) -> List[Dict[str, Any]]:
        """Compare current result with baseline"""
        differences = []
        
        if isinstance(current, dict) and isinstance(baseline, dict):
            for key in set(current.keys()) | set(baseline.keys()):
                new_path = f"{path}.{key}" if path else key
                
                if key not in current:
                    differences.append({
                        "path": new_path,
                        "type": "missing",
                        "baseline": baseline[key]
                    })
                elif key not in baseline:
                    differences.append({
                        "path": new_path,
                        "type": "added",
                        "current": current[key]
                    })
                else:
                    differences.extend(
                        self._compare_results(current[key], baseline[key], new_path)
                    )
        elif isinstance(current, list) and isinstance(baseline, list):
            if len(current) != len(baseline):
                differences.append({
                    "path": path,
                    "type": "length_diff",
                    "current_len": len(current),
                    "baseline_len": len(baseline)
                })
        elif current != baseline:
            diff_ratio = 0.0
            if isinstance(current, (int, float)) and isinstance(baseline, (int, float)) and baseline != 0:
                diff_ratio = abs(current - baseline) / abs(baseline)
            
            differences.append({
                "path": path,
                "type": "value_diff",
                "current": current,
                "baseline": baseline,
                "diff_ratio": diff_ratio
            })
        
        return differences

    def _get_nested_value(self, data: Any, key: str) -> Any:
        """Get nested value using dot notation"""
        keys = key.split(".")
        value = data
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            elif isinstance(value, list) and k.isdigit():
                idx = int(k)
                value = value[idx] if idx < len(value) else None
            else:
                return None
                
            if value is None:
                return None
                
        return value


def create_verifier() -> ResultVerifier:
    """Create a result verifier instance"""
    return ResultVerifier()


__all__ = [
    "ResultVerifier",
    "create_verifier",
]