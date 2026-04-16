import json
import subprocess
from pathlib import Path

import pytest


def test_phase61_learning_cli_create_and_list(tmp_path):
    """
    Phase 6.1 acceptance:
    - learning_cli can create an evaluation_report artifact from a benchmark JSON file
    - and list it back from ExecutionStore
    """
    db_path = tmp_path / "executions.sqlite3"

    # Minimal benchmark result JSON (matches ResultReporter.generate_json shape)
    bench = {
        "benchmark_name": "code-review",
        "total_tasks": 1,
        "passed_tasks": 1,
        "pass_at_1": 1.0,
        "pass_at_3": 1.0,
        "pass_at_k": 1.0,
        "avg_latency_ms": 10.0,
        "avg_tokens": 20,
        "task_results": [
            {"task_id": "t1", "success": True, "latency_ms": 10, "tokens_used": 20, "tool_calls": []}
        ],
        "executed_at": "now",
    }
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, ensure_ascii=False), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[3]

    # Create artifact
    cmd = [
        "python3",
        str(repo_root / "scripts" / "learning_cli.py"),
        "--db",
        str(db_path),
        "create-eval-artifact",
        "--target-type",
        "agent",
        "--target-id",
        "a1",
        "--version",
        "v1",
        "--benchmark-json",
        str(bench_path),
        "--trace-id",
        "t1",
        "--run-id",
        "r1",
    ]
    p = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    artifact_id = p.stdout.strip()
    assert artifact_id

    # List artifacts
    cmd2 = [
        "python3",
        str(repo_root / "scripts" / "learning_cli.py"),
        "--db",
        str(db_path),
        "list",
        "--target-type",
        "agent",
        "--target-id",
        "a1",
        "--limit",
        "10",
        "--offset",
        "0",
    ]
    p2 = subprocess.run(cmd2, cwd=str(repo_root), capture_output=True, text=True)
    assert p2.returncode == 0, p2.stderr
    data = json.loads(p2.stdout)
    assert data["total"] >= 1
    assert any(i["artifact_id"] == artifact_id for i in data["items"])
