import importlib
import zipfile
from io import BytesIO

import anyio
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_change_control_evidence_contains_summary_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        from core.governance.changeset import record_changeset
        from core.harness.kernel.runtime import get_kernel_runtime

        rt = get_kernel_runtime()
        assert rt and rt.execution_store
        change_id = "change_evidence_demo"

        async def _seed():
            await record_changeset(
                store=rt.execution_store,
                name="skill_eval.engine_skill_md_patch_proposed",
                target_type="change",
                target_id=change_id,
                status="success",
                args={"suite_id": "suite_x", "skill_id": "skill_x", "diff_hash": "d1", "base_hash": "b1"},
                result={"path": "/tmp/x", "updated_raw": "---\nname: skill_x\n---\n"},
                tenant_id="t_demo",
                user_id="admin",
            )

        anyio.run(_seed)

        resp = client.get(f"/api/core/change-control/changes/{change_id}/evidence?format=zip", headers=hdr)
        assert resp.status_code == 200
        z = zipfile.ZipFile(BytesIO(resp.content))
        names = set(z.namelist())
        assert "evidence.json" in names
        assert "summary.json" in names
        assert "summary.md" in names

