"""Field Feedback — FDE 现场反馈闭环 (FDE Toolkit D).

FDE 在客户现场发现的问题、写的胶水代码、形成的临时方案,
通过标准化 Schema 回传总部, 驱动产品迭代。

基础版 (P0): 结构化记录 → 本地文件 → 同步到总部
进阶版 (P1): GoalGenerator 定期扫描 → 生成改进提案 -> AutoLearner 自动学习
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional


FEEDBACK_DIR = os.path.expanduser(
    os.environ.get("AIPLAT_FEEDBACK_DIR", "~/.aiplat/field_feedback")
)


def submit_field_feedback(data: Dict[str, Any]) -> str:
    """FDE 提交现场反馈 → 写入本地 JSON 文件. 返回 feedback_id."""
    os.makedirs(FEEDBACK_DIR, exist_ok=True)
    fid = f"fb-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    record = {
        "id": fid,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **data,
    }
    path = os.path.join(FEEDBACK_DIR, f"{fid}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return fid


def list_field_feedback(limit: int = 20) -> List[Dict[str, Any]]:
    """返回最近 N 条现场反馈 (最新在前)."""
    if not os.path.isdir(FEEDBACK_DIR):
        return []
    files = sorted(
        [f for f in os.listdir(FEEDBACK_DIR) if f.endswith(".json")],
        reverse=True,
    )[:limit]
    results = []
    for fn in files:
        try:
            with open(os.path.join(FEEDBACK_DIR, fn)) as f:
                results.append(json.load(f))
        except Exception:
            continue
    return results


def count_unresolved() -> int:
    """返回未处理反馈数量 (供 GoalGenerator scanner 使用)."""
    items = list_field_feedback(limit=200)
    return len([it for it in items if it.get("status") != "resolved"])
