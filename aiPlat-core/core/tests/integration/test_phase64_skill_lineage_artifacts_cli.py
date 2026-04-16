import json
import subprocess
from pathlib import Path


def test_phase64_skill_version_and_rollback_artifacts(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    db_path = tmp_path / "executions.sqlite3"
    cli = repo_root / "scripts" / "learning_cli.py"

    skill_version = {
        "id": "s1:v1.0",
        "skill_id": "s1",
        "version": "v1.0",
        "parent_version": None,
        "evolution_type": "fix",
        "trigger": "test",
        "content_hash": "abcd",
        "diff": "",
        "created_at": "2026-01-01T00:00:00",
        "metadata": {"k": "v"},
    }
    sv_path = tmp_path / "skill_version.json"
    sv_path.write_text(json.dumps(skill_version, ensure_ascii=False), encoding="utf-8")

    # Create skill version artifact
    p = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-skill-version-artifact",
            "--skill-version-json",
            str(sv_path),
            "--version",
            "artifact-v1",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    artifact1 = p.stdout.strip()
    assert artifact1

    # Create rollback artifact
    p2 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-skill-rollback-artifact",
            "--skill-id",
            "s1",
            "--from-version",
            "v2.0",
            "--to-version",
            "v1.0",
            "--version",
            "artifact-rb1",
            "--reason",
            "regression",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    artifact2 = p2.stdout.strip()
    assert artifact2

    # Verify kinds
    p3 = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "list", "--target-type", "skill", "--target-id", "s1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p3.returncode == 0, p3.stderr
    data = json.loads(p3.stdout)
    items = {i["artifact_id"]: i for i in data["items"]}
    assert items[artifact1]["kind"] == "skill_evolution"
    assert items[artifact2]["kind"] == "skill_rollback"

