#!/usr/bin/env python3
"""Run P1 security unit suites without importing real ``core`` package.

Tests under ``aiPlat-core/core/tests/...`` are rewritten into a temp dir so
pytest does not treat them as ``core.*`` (which pulls ``core/__init__.py`` and
fails in a minimal CI venv missing anyio/etc.).
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = ROOT / "aiPlat-core"
TEST_DIR = CORE_ROOT / "core" / "tests" / "unit" / "test_apps"
FILES = [
    "test_security_text_live_p1.py",
    "test_security_tool_retrieval_live_p1.py",
    "test_security_p1_judge_session.py",
    "test_security_dynamic_p13.py",
    "test_security_p1_4_kvm_escape.py",
]

_ROOT_ASSIGN = re.compile(
    r"^ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*$",
    re.M,
)


def main() -> int:
    """main。
    """
    missing = [f for f in FILES if not (TEST_DIR / f).is_file()]
    if missing:
        print(f"MISSING tests: {missing}", file=sys.stderr)
        return 2

    import pytest

    with tempfile.TemporaryDirectory(prefix="sec_p1_ut_") as td:
        tdir = Path(td)
        rewritten = []
        for name in FILES:
            src = TEST_DIR / name
            text = src.read_text(encoding="utf-8")
            repl = f"ROOT = Path({str(CORE_ROOT)!r})"
            text2, n = _ROOT_ASSIGN.subn(repl, text, count=1)
            if n != 1:
                print(f"FAIL: could not rewrite ROOT in {name}", file=sys.stderr)
                return 2
            dst = tdir / name
            dst.write_text(text2, encoding="utf-8")
            rewritten.append(str(dst))

        args = [
            f"--rootdir={ROOT}",
            f"-c{ROOT / 'pytest.ini'}",
            "--noconftest",
            "--import-mode=importlib",
            "-o",
            "addopts=",
            "-o",
            "asyncio_mode=auto",
            "-o",
            "markers=asyncio: mark async tests (pytest-asyncio)",
            "-v",
            "--tb=short",
            *rewritten,
        ]
        return int(pytest.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
