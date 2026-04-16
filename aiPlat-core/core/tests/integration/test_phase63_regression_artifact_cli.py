import json
import subprocess
from pathlib import Path


def test_phase63_learning_cli_regression_artifact(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    db_path = tmp_path / "executions.sqlite3"

    current = {
        "benchmark_name": "code-review",
        "total_tasks": 10,
        "passed_tasks": 8,
        "pass_at_1": 0.8,
        "pass_at_3": 0.8,
        "pass_at_k": 0.8,
        "avg_latency_ms": 10.0,
        "avg_tokens": 20,
        "task_results": [],
        "executed_at": "now",
    }
    baseline = {
        "benchmark_name": "code-review",
        "total_tasks": 10,
        "passed_tasks": 10,
        "pass_at_1": 1.0,
        "pass_at_3": 1.0,
        "pass_at_k": 1.0,
        "avg_latency_ms": 10.0,
        "avg_tokens": 20,
        "task_results": [],
        "executed_at": "then",
    }
    cur_path = tmp_path / "current.json"
    base_path = tmp_path / "baseline.json"
    cur_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    base_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    cli = repo_root / "scripts" / "learning_cli.py"
    p = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-regression-artifact",
            "--target-type",
            "agent",
            "--target-id",
            "a1",
            "--version",
            "v1",
            "--current-json",
            str(cur_path),
            "--baseline-json",
            str(base_path),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    artifact_id = p.stdout.strip()
    assert artifact_id

    # List and ensure artifact exists with regression_report kind
    p2 = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "list", "--target-type", "agent", "--target-id", "a1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    data = json.loads(p2.stdout)
    item = next(i for i in data["items"] if i["artifact_id"] == artifact_id)
    assert item["kind"] == "regression_report"

