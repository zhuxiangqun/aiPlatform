from core.harness.execution.completion_receipt import (
    bind_completion_to_receipts,
    infer_receipt_status,
    record_tool_receipt,
)


def test_fix_claim_without_receipt_is_unverified():
    text, status = bind_completion_to_receipts("已经修好了", {})
    assert status == "unverified"
    assert text.startswith("[未核验]")
    assert "已经修好了" in text


def test_fix_claim_after_failed_receipt_keeps_error():
    ctx = {}
    record_tool_receipt(ctx, tool="shell", status="failed", detail="Error: column missing")
    text, status = bind_completion_to_receipts("已经修好了", ctx)
    assert status == "failed"
    assert "column missing" in text
    assert ctx["_last_tool_receipt_status"] == "failed"


def test_fix_claim_with_ok_receipt_stays():
    ctx = {}
    record_tool_receipt(ctx, tool="shell", status="ok", detail="tests passed")
    text, status = bind_completion_to_receipts("已经修好了", ctx)
    assert status == "ok"
    assert text == "已经修好了"


def test_path_claim_needs_receipt():
    text, status = bind_completion_to_receipts("文件在 /tmp/missing.py", {})
    assert status == "unverified"
    assert "/tmp/missing.py" in text


def test_plain_answer_without_claim_stays():
    text, status = bind_completion_to_receipts("hello", {})
    assert status == "ok"
    assert text == "hello"


def test_path_claim_confirmed_by_ok_receipt():
    ctx = {}
    record_tool_receipt(ctx, tool="read", status="ok", detail="read /tmp/ok.py bytes=12")
    text, status = bind_completion_to_receipts("文件在 /tmp/ok.py", ctx)
    assert status == "ok"
    assert text == "文件在 /tmp/ok.py"


def test_infer_receipt_status_head_only():
    assert infer_receipt_status("Error: column missing") == "failed"
    assert infer_receipt_status("404 not found") == "failed"
    assert infer_receipt_status("") == "failed"
    long_ok = "wrote handler\n" + ("error handling stays in the function\n" * 20)
    assert infer_receipt_status(long_ok) == "ok"
    assert infer_receipt_status("AIPLAT_TOOL_EXECUTE_APPROVAL_REQUIRED tool=x") == "failed"
    assert infer_receipt_status("AIPLAT_APPROVAL_WAIT_DENIED\nstatus=rejected") == "failed"
    assert infer_receipt_status("approval_required: need human") == "failed"
