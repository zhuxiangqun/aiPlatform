"""Architecture guard: detect async antipatterns — asyncio.sleep() inside loops."""

import ast
from pathlib import Path
from typing import Any, Dict, List

from core.management.arch_guard_base import ArchIssue, ArchRule


class AsyncSleepInLoopCheck(ArchRule):
    """Detect await asyncio.sleep() inside for/while loops (serializing async).
    
    Excludes retry/backoff patterns where the sleep argument is computed
    (e.g., ``asyncio.sleep(delay)``, ``asyncio.sleep(2**attempt)``) rather
    than a constant value.
    """
    code = "async_sleep_in_loop"
    level = "warning"
    section_number = "§39"
    section_name = "异步性能检测"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        issues = []
        for target_dir in ("aiPlat-core/core/harness/execution", "aiPlat-platform/kb"):
            d = repo_root / target_dir
            if not d.is_dir():
                continue
            for py_file in d.rglob("*.py"):
                if "__pycache__" in str(py_file) or "tests" in str(py_file):
                    continue
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue

                rel = str(py_file.relative_to(repo_root))
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.For, ast.While)):
                        continue
                    has_sleep = False
                    sleep_lineno = 0
                    is_backoff = False
                    for child in ast.walk(node):
                        if isinstance(child, ast.Await):
                            call = child.value
                            is_sleep = (
                                isinstance(call, ast.Call)
                                and isinstance(call.func, ast.Attribute)
                                and call.func.attr == "sleep"
                                and isinstance(call.func.value, ast.Name)
                                and call.func.value.id == "asyncio"
                            )
                            if is_sleep:
                                has_sleep = True
                                sleep_lineno = child.lineno
                                # Check if sleep argument is computed (backoff pattern) vs constant
                                if call.args:
                                    arg = call.args[0]
                                    is_backoff = not isinstance(arg, ast.Constant)
                                break

                    if has_sleep and not is_backoff:
                        issues.append(ArchIssue(
                            level=self.level, code=self.code,
                            message=f"asyncio.sleep() inside loop — serializes async. Use semaphore or gather for concurrency",
                            files=[f"{rel}:{sleep_lineno}: asyncio.sleep() in loop" if sleep_lineno else f"{rel}:{node.lineno}"],
                            count=1,
                        ))
        return issues
