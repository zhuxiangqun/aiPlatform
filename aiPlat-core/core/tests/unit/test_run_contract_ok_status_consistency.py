from types import SimpleNamespace

from core.api.utils.run_contract import wrap_execution_result_as_run_summary


def test_run_contract_ok_false_when_status_waiting_approval():
    r = SimpleNamespace(ok=True, payload={"status": "waiting_approval", "error": {"code": "APPROVAL_REQUIRED", "message": "需要审批"}}, run_id="run1")
    out = wrap_execution_result_as_run_summary(r)
    assert out["ok"] is False
    assert out["status"] == "waiting_approval"


def test_run_contract_ok_false_when_status_failed():
    r = SimpleNamespace(ok=True, payload={"status": "failed", "error": {"code": "EXCEPTION", "message": "boom"}}, run_id="run2")
    out = wrap_execution_result_as_run_summary(r)
    assert out["ok"] is False
    assert out["status"] == "failed"

