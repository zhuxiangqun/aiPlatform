"""G2b pack status — facilitation facts; accuracy_claim always false."""
from __future__ import annotations

from core.apps.eval.service.g2b import g2b_pack_status


def test_g2b_pack_status_reads_n100_pack():
    st = g2b_pack_status(tenant_id="eval-v1")
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["not_accuracy_certification"] is True
    assert st["task_count"] == 100
    assert st["target_n"] == 100
    assert st["pack_ready"] is True
    # Committed closeout is still n=30 until dual-human 31–100 lands.
    assert st["closeout_n"] == 30
    assert st["pending_dual_human"] == 70
    assert st["dual_human_complete"] is False
    assert "prompt" in (st.get("families") or {})


def test_eval_g2b_pack_status_facade():
    from core.api.core_facade import eval_g2b_pack_status

    st = eval_g2b_pack_status()
    assert st["accuracy_claim"] is False
    assert st["task_count"] >= 30
