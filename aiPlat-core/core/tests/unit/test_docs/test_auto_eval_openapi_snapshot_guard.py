from __future__ import annotations

import json
from pathlib import Path


def test_auto_eval_openapi_snapshot_guard():
    """
    更强一层的“防脱节”护栏：
    - 以 FastAPI OpenAPI 为事实来源，生成最小稳定快照
    - 与仓库内 snapshot 文件逐项对比

    若失败，请执行：
      python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json
    并检查设计文档是否也需要同步更新。
    """

    from core.tools.export_eval_openapi import build_snapshot

    actual = build_snapshot()
    snap_path = Path(__file__).resolve().parents[4] / "docs" / "design" / "evaluation" / "openapi-eval.snapshot.json"
    assert snap_path.exists(), f"missing snapshot: {snap_path}"
    expected = json.loads(snap_path.read_text(encoding="utf-8", errors="ignore"))

    assert actual == expected

