import importlib

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_eval_suite_create_and_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"skill_eval_trigger":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Create suite targeting a fake skill id
        suite = client.post(
            "/api/core/skill-evals/suites",
            headers=hdr,
            json={
                "name": "pdf_table_extract_trigger_eval",
                "scope": "all",
                "target_skill_id": "pdf_table_extract",
                "positive_queries": ["帮我从PDF里提取表格到Excel"],
                "negative_queries": ["总结一下这篇文章"],
            },
        )
        assert suite.status_code == 200, suite.text
        suite_id = suite.json()["suite"]["suite_id"]

        # Deterministic catalog override: ensure overlap makes pdf_table_extract top-1
        skills_override = [
            {
                "skill_id": "pdf_table_extract",
                "name": "PDF 表格提取",
                "description": "从 PDF 中提取表格并导出 Excel",
                "scope": "engine",
                "trigger_conditions": ["PDF", "表格", "Excel"],
                "keywords": {},
            },
            {
                "skill_id": "text_summarize",
                "name": "文本总结",
                "description": "总结文章内容",
                "scope": "engine",
                "trigger_conditions": ["总结", "概括"],
                "keywords": {},
            },
        ]

        run = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/run",
            headers=hdr,
            json={"mode": "heuristic", "max_cases": 20, "skills_override": skills_override},
        )
        assert run.status_code == 200, run.text
        run_id = run.json()["run_id"]

        run_row = client.get(f"/api/core/skill-evals/runs/{run_id}", headers=hdr)
        assert run_row.status_code == 200, run_row.text
        metrics = (run_row.json().get("metrics") or {})
        assert metrics.get("counts", {}).get("total") == 2
        assert metrics.get("counts", {}).get("tp") == 1
        assert metrics.get("counts", {}).get("tn") == 1

        results = client.get(f"/api/core/skill-evals/runs/{run_id}/results", headers=hdr)
        assert results.status_code == 200, results.text
        items = results.json().get("items") or []
        assert len(items) == 2

        # Run again using "live" simulation mode and compare
        run2 = client.post(
            f"/api/core/skill-evals/suites/{suite_id}/run",
            headers=hdr,
            json={"mode": "live", "max_cases": 20, "skills_override": skills_override},
        )
        assert run2.status_code == 200, run2.text
        run_id2 = run2.json()["run_id"]

        # live mode should emit routing syscalls (routing_decision + skill_candidates_snapshot)
        from core.harness.kernel.runtime import get_kernel_runtime

        rt = get_kernel_runtime()
        assert rt and rt.execution_store
        ev = anyio.run(lambda: rt.execution_store.list_syscall_events(limit=200, offset=0, tenant_id="t_demo", kind="routing", run_id=run_id2))
        names = [x.get("name") for x in (ev.get("items") or [])]
        assert "routing_decision" in names
        assert "skill_candidates_snapshot" in names

        cmp = client.post("/api/core/skill-evals/compare", headers=hdr, json={"run_id_a": run_id, "run_id_b": run_id2})
        assert cmp.status_code == 200, cmp.text
        assert cmp.json().get("status") == "ok"

        # Analyzer-lite suggestions
        sug = client.post(f"/api/core/skill-evals/runs/{run_id}/suggest", headers=hdr, json={"max_tokens": 10})
        assert sug.status_code == 200, sug.text
        body = sug.json()
        assert isinstance(body.get("suggested_description"), str) and body.get("suggested_description")
        assert isinstance(body.get("add_keywords"), list)
        assert isinstance(body.get("avoid_keywords"), list)
        assert isinstance(body.get("patch"), dict)

        # Apply suggestion patch back to suite
        ap = client.post(f"/api/core/skill-evals/suites/{suite_id}/apply-suggestion", headers=hdr, json={"patch": body.get("patch")})
        assert ap.status_code == 200, ap.text
        suite2 = ap.json().get("suite") or {}
        assert isinstance(suite2.get("description"), str) and suite2.get("description")
        cfg2 = suite2.get("config") or {}
        assert "suggested_add_keywords" in cfg2
        assert "suggested_avoid_keywords" in cfg2
        assert "applied_suggestion_at" in cfg2
