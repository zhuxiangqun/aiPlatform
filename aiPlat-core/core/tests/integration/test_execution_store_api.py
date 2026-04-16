import json
import sqlite3
import time

from fastapi.testclient import TestClient


def _insert_agent_exec(db_path: str, execution_id: str, agent_id: str):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO agent_executions
              (id, agent_id, status, input_json, output_json, error, start_time, end_time, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                agent_id,
                "completed",
                json.dumps({"q": "hello"}, ensure_ascii=False),
                json.dumps({"a": "world"}, ensure_ascii=False),
                None,
                time.time(),
                time.time(),
                1,
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_skill_exec(db_path: str, execution_id: str, skill_id: str):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO skill_executions
              (id, skill_id, status, input_json, output_json, error, start_time, end_time, duration_ms, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                skill_id,
                "failed",
                json.dumps({"x": 1}, ensure_ascii=False),
                json.dumps(None),
                "boom",
                time.time(),
                time.time(),
                2,
                "system",
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_execution_store_api_reads_from_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "executions.sqlite3"
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(db_path))

    # Import after env set so singleton uses the temp DB
    from core.server import app

    with TestClient(app) as client:
        _insert_agent_exec(str(db_path), "exec_1", "agent_1")
        r = client.get("/api/core/agents/executions/exec_1")
        assert r.status_code == 200
        assert r.json()["id"] == "exec_1"

        r = client.get("/api/core/agents/agent_1/history")
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] >= 1
        assert payload["history"][0]["agent_id"] == "agent_1"

        _insert_skill_exec(str(db_path), "sexec_1", "skill_1")
        r = client.get("/api/core/skills/executions/sexec_1")
        assert r.status_code == 200
        assert r.json()["execution_id"] == "sexec_1"

        r = client.get("/api/core/skills/skill_1/executions")
        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] >= 1
        assert payload["executions"][0]["skill_id"] == "skill_1"

