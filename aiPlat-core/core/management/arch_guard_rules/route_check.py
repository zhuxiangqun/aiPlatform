"""Route duplicate detection — Python-based rule (replaces broken YAML shell command).

§77: Detects same-path + same-method routes that would crash FastAPI on startup.
"""

import ast
from collections import Counter
from pathlib import Path
from typing import List

from core.management.arch_guard_base import ArchIssue, ArchRule


class RouteDuplicateCheck(ArchRule):
    """§77: Detect routes that share the same path AND HTTP method.

    Same path with different methods (GET vs POST) is normal REST design.
    Same path AND method = FastAPI crashes on startup.
    """

    code = "route_duplicate_detection"
    level = "error"
    section_number = "§77"
    section_name = "路由重复检测"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        routers_dir = repo_root / "aiPlat-core" / "core" / "api" / "routers"
        if not routers_dir.is_dir():
            return []

        duplicates = []
        for fname in sorted(routers_dir.iterdir()):
            if not fname.name.endswith(".py") or fname.name == "__init__.py":
                continue
            try:
                tree = ast.parse(fname.read_text(), filename=str(fname))
            except Exception:
                continue

            prefix = ""
            routes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and hasattr(node.func, "attr"):
                    if node.func.attr == "APIRouter":
                        for kw in node.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                prefix = kw.value.value
                    if (
                        isinstance(node.func, ast.Attribute)
                        and hasattr(node.func, "value")
                        and hasattr(node.func.value, "id")
                        and node.func.value.id == "router"
                        and node.func.attr in ("get", "post", "put", "delete", "patch")
                    ):
                        if node.args and isinstance(node.args[0], ast.Constant):
                            routes.append(
                                (prefix + node.args[0].value, node.func.attr.upper())
                            )

            cnt = Counter((p, m) for p, m in routes)
            for (path, method), count in cnt.items():
                if count > 1:
                    duplicates.append(f"{fname.name}: {method} {path} (x{count})")

        if duplicates:
            return [
                ArchIssue(
                    level=self.level,
                    code=self.code,
                    message="Duplicate routes found (same path + method) — FastAPI would crash on startup",
                    files=duplicates,
                    count=len(duplicates),
                )
            ]
        return []
