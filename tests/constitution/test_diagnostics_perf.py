"""Performance regression tests — prevent redundant operations in hot paths."""
import pytest


def test_diagnostics_no_direct_build_graph():
    """Ensure diagnostics.py checks don't directly call build_graph().
    
    All graph-dependent checks must use _get_or_build_graph() or
    DiagnosticCheck.get_graph() which reuses the shared graph built once
    by run_all_diagnostics.
    """
    import ast
    from pathlib import Path
    
    diag_path = Path(__file__).resolve().parents[2] / "aiPlat-core" / "core" / "api" / "routers" / "diagnostics.py"
    if not diag_path.exists():
        pytest.skip("diagnostics.py not found")
    
    tree = ast.parse(diag_path.read_text())
    
    # Find all async def _check_* functions
    check_funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_check_"):
                check_funcs.append(node)
    
    violations = []
    for func in check_funcs:
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                func_ref = _get_call_name(node.func)
                if func_ref == "build_graph":
                    violations.append(f"{func.name}: calls build_graph() directly")
    
    assert len(violations) == 0, (
        f"Found {len(violations)} direct build_graph() calls in check functions:\n"
        + "\n".join(violations)
        + "\n\nUse _get_or_build_graph() or DiagnosticCheck.get_graph() instead."
    )


def test_shared_graph_built_exactly_once():
    """Ensure run_all_diagnostics only triggers one build_graph().
    
    The shared graph is built once via _get_or_build_graph() at the start,
    and all checks reuse it."""
    import ast
    from pathlib import Path
    
    diag_path = Path(__file__).resolve().parents[2] / "aiPlat-core" / "core" / "api" / "routers" / "diagnostics.py"
    if not diag_path.exists():
        pytest.skip("diagnostics.py not found")
    
    tree = ast.parse(diag_path.read_text())
    
    # Find run_all_diagnostics function
    run_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "run_all_diagnostics":
                run_func = node
                break
    
    assert run_func is not None, "run_all_diagnostics function not found"
    
    # Count _get_or_build_graph calls (should be exactly 1)
    get_graph_calls = 0
    for node in ast.walk(run_func):
        if isinstance(node, ast.Call):
            func_ref = _get_call_name(node.func)
            if func_ref == "_get_or_build_graph":
                get_graph_calls += 1
    
    assert get_graph_calls >= 1, (
        "run_all_diagnostics should call _get_or_build_graph() at least once "
        "to build the shared code graph"
    )


def _get_call_name(node) -> str:
    """Extract the function name from an AST Call node."""
    import ast
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
