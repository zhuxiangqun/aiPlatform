"""
AST-based architecture checks — complements grep rules with call-graph analysis.

Checks that grep cannot do:
  - Verify a specific function is reachable from a set of entry-point methods
  - Verify a specific data field is assigned in any function reachable from an entry point
  - Detect indirect call chains that grep misses

Used by arch_guard_rules.yaml via check.type: ast_call_chain
"""

from __future__ import annotations
import ast
import os
from pathlib import Path
from typing import List, Optional, Set, Dict


def _parse_file(filepath: str) -> Optional[ast.AST]:
    """Parse a Python file, return AST or None on failure."""
    try:
        with open(filepath, 'r') as f:
            return ast.parse(f.read(), filename=filepath)
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return None


def _collect_calls(node: ast.AST) -> List[str]:
    """Collect all function/method call names in an AST subtree."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.append(child.func.attr)
    return calls


def _find_method(tree: ast.AST, method_name: str) -> Optional[ast.FunctionDef]:
    """Find a method/function definition by name in the AST."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                return node
    return None


def _find_all_methods(tree: ast.AST, names: Set[str]) -> Dict[str, ast.FunctionDef]:
    """Find all methods matching a set of names."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in names:
                found[node.name] = node
    return found


def _resolve_call_target(tree: ast.AST, func_name: str, call_site: ast.AST) -> Optional[str]:
    """Resolve a simple method call like self._foo() to the definition name.
    
    Returns the resolved function name if found, None otherwise.
    """
    if isinstance(call_site, ast.Call):
        if isinstance(call_site.func, ast.Attribute):
            # self.method_name or obj.method_name
            attr_name = call_site.func.attr
            return attr_name
        elif isinstance(call_site.func, ast.Name):
            return call_site.func.id
    return None


def check_call_chain(
    filepath: str,
    entry_methods: List[str],
    required_callee: str,
    *,
    max_depth: int = 3,
) -> List[str]:
    """Check if required_callee is reachable from any of entry_methods.
    
    Traces through simple method calls (self.foo() patterns) up to max_depth levels.
    Returns list of entry methods where required_callee is NOT reachable.
    
    Args:
        filepath: Path to the Python file to analyze
        entry_methods: Method names that should eventually call required_callee
        required_callee: The function that must be reachable
        max_depth: Maximum call depth to trace
    """
    tree = _parse_file(filepath)
    if tree is None:
        return entry_methods  # All unreachable if file can't be parsed
    
    # Find all entry method definitions
    entries = _find_all_methods(tree, set(entry_methods))
    
    unreachable = []
    for name, method in entries.items():
        # BFS through call chain
        visited: Set[str] = set()
        queue: List[ast.AST] = [method]
        found = False
        
        for _ in range(max_depth + 1):
            if not queue:
                break
            next_queue = []
            for node in queue:
                calls = _collect_calls(node)
                if required_callee in calls:
                    found = True
                    break
                
                # Look for self.method() calls and resolve to their definitions
                for call_node in ast.walk(node):
                    if isinstance(call_node, ast.Call):
                        target = _resolve_call_target(tree, "", call_node)
                        if target and target not in visited:
                            visited.add(target)
                            target_def = _find_method(tree, target)
                            if target_def:
                                next_queue.append(target_def)
            if found:
                break
            queue = next_queue
        
        if not found:
            unreachable.append(name)
    
    return unreachable


def check_field_assigned(
    filepath: str,
    entry_function: str,
    required_field: str,
    *,
    sub_functions: Optional[List[str]] = None,
) -> bool:
    """Check if required_field is assigned anywhere reachable from entry_function.
    
    Searches entry_function body AND any listed sub_functions.
    
    Args:
        filepath: Path to the Python file to analyze
        entry_function: The main entry-point function name
        required_field: The field/attribute name that must be assigned
        sub_functions: Additional functions that may contain the assignment
    """
    tree = _parse_file(filepath)
    if tree is None:
        return False
    
    funcs_to_check = [entry_function]
    if sub_functions:
        funcs_to_check.extend(sub_functions)
    
    for func_name in funcs_to_check:
        func = _find_method(tree, func_name)
        if func is None:
            continue
        
        # Walk the function body looking for assignments to required_field
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        # dict[key] = value
                        if isinstance(target.slice, ast.Constant):
                            if target.slice.value == required_field:
                                return True
                    elif isinstance(target, ast.Attribute):
                        if target.attr == required_field:
                            return True
                    elif isinstance(target, ast.Name):
                        if target.id == required_field:
                            return True
            
            # Check aug_assign and ann_assign
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                target = node.target
                if isinstance(target, ast.Attribute) and target.attr == required_field:
                    return True
                elif isinstance(target, ast.Subscript):
                    if isinstance(target.slice, ast.Constant) and target.slice.value == required_field:
                        return True
            
            # Check dict literal keys: {"source_instances": [...]}
            elif isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value == required_field:
                        return True
    
    return False
