"""domain_evolution_bridge：三域扫描 → HUMAN_GATE → 回执。"""
from __future__ import annotations

from core.harness.digital_human.domain_evolution_bridge import (
    apply_domain_evolution_proposal,
    domain_evolution_brief_line,
    scan_domain_evolution_proposals,
)
from core.harness.digital_human.evolution_proposals import (
    STATUS_APPLIED,
    STATUS_HUMAN_GATE,
    _clear_proposals_for_tests,
    decide_evolution_proposal,
    list_evolution_proposals,
)


def test_scan_fixtures_create_and_approve(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    scan = scan_domain_evolution_proposals(
        use_fixtures_if_empty=True,
        include_evolver_snapshot=False,
        tenant_id="default",
    )
    assert scan["ok"] is True
    assert scan["e5_claimed"] is False
    assert scan["production_write"] is False
    assert len(scan["created"]) >= 2  # eval + fde + knowledge fixture

    pending = list_evolution_proposals(status=STATUS_HUMAN_GATE, limit=20)
    kinds = {p.get("kind") for p in pending}
    assert "eval_coverage" in kinds
    assert "fde_evolve" in kinds
    assert "knowledge_evolve" in kinds
    assert "待批" in domain_evolution_brief_line() or "领域进化" in domain_evolution_brief_line()

    # 批准一条
    target = next(p for p in pending if p.get("kind") == "eval_coverage")
    decided = decide_evolution_proposal(decision="approve", proposal_id=target["id"])
    assert decided["ok"] is True
    assert decided["production_model_changed"] is False
    ar = decided["apply_result"]
    assert ar.get("applied") is True
    assert ar.get("production_write") is False
    assert ar.get("e5_claimed") is False
    assert decided["proposal"]["status"] == STATUS_APPLIED
    receipt = tmp_path / "digital_human" / "domain_evolution_receipts.jsonl"
    assert receipt.is_file()


def test_scan_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    scan_domain_evolution_proposals(use_fixtures_if_empty=True, include_evolver_snapshot=False)
    scan2 = scan_domain_evolution_proposals(
        use_fixtures_if_empty=True, include_evolver_snapshot=False
    )
    assert scan2["created"] == []
    assert any(s.get("reason") == "already_pending" for s in scan2["skipped"])


def test_apply_receipt_helper(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = apply_domain_evolution_proposal(
        {
            "id": "dhp_x",
            "kind": "fde_evolve",
            "payload": {"guidance": "审草稿", "fingerprint": "abc"},
        }
    )
    assert out["applied"] is True
    assert out["e5_claimed"] is False


def test_live_inventory_file_scan(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    _clear_proposals_for_tests()
    inv_dir = tmp_path / "digital_human"
    inv_dir.mkdir(parents=True, exist_ok=True)
    import json

    (inv_dir / "eval_inventory.json").write_text(
        json.dumps(
            {
                "required_ids": [f"cap.{i}" for i in range(10)],
                "covered_ids": [f"cap.{i}" for i in range(7)],
            }
        ),
        encoding="utf-8",
    )
    scan = scan_domain_evolution_proposals(
        use_fixtures_if_empty=False,
        include_evolver_snapshot=False,
        knowledge_cases=[],  # 避免扫真实域
    )
    assert scan["live"]["eval_file"] is True
    assert "eval_coverage" in scan["created"] or any(
        s.get("domain") == "eval" for s in scan["skipped"]
    )


def test_knowledge_apply_enqueue_without_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    async def fake_enqueue(case_id, **kwargs):
        return {"status": "enqueued", "case_id": case_id, "auto_apply": False}

    monkeypatch.setattr(
        "core.harness.knowledge.ontology_case_learning.maybe_enqueue_evolution_proposal",
        fake_enqueue,
    )
    out = apply_domain_evolution_proposal(
        {
            "id": "dhp_k",
            "kind": "knowledge_evolve",
            "payload": {"case_id": "c1", "guidance": "x"},
        }
    )
    assert out["applied"] is True
    assert out["enqueue"].get("status") == "enqueued"
    assert out["auto_apply"] is False


def test_refresh_eval_inventory_from_capability(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.digital_human.domain_evolution_bridge import (
        load_inventory_file,
        refresh_domain_inventories,
    )

    def fake_analyze(**kwargs):
        return {
            "ok": True,
            "gaps": [
                {"capability_id": "cap.a", "ok": True, "gap": 0},
                {"capability_id": "cap.b", "ok": False, "gap": 2},
            ],
            "subject_kind": "test",
        }

    monkeypatch.setattr(
        "core.apps.eval.service.capability_coverage_fill.analyze_capability_coverage",
        fake_analyze,
    )
    r = refresh_domain_inventories(persist=True)
    assert r["eval"]["required_ids"] == ["cap.a", "cap.b"]
    assert r["eval"]["covered_ids"] == ["cap.a"]
    loaded = load_inventory_file("eval_inventory")
    assert loaded is not None
    assert loaded["covered_ids"] == ["cap.a"]


def test_build_fde_inventory_from_delivery_plans(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.digital_human.domain_evolution_bridge import (
        build_fde_inventory_from_delivery_plans,
        load_inventory_file,
        refresh_domain_inventories,
        scan_domain_evolution_proposals,
    )

    def fake_skel():
        return {
            "version": 1,
            "phases": [
                {
                    "id": "gate0",
                    "steps": [
                        {"id": "gate0.deploy_mode"},
                        {"id": "gate0.scope"},
                    ],
                },
                {
                    "id": "fde1",
                    "steps": [{"id": "fde1.customer"}],
                },
            ],
        }

    monkeypatch.setattr(
        "core.apps.fde.service.delivery_plan.load_delivery_plan_skeleton",
        fake_skel,
    )
    plans = tmp_path / "fde_delivery_plans"
    plans.mkdir(parents=True)
    import json

    (plans / "acme.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "id": "gate0",
                        "steps": [
                            {"id": "gate0.deploy_mode", "status": "done"},
                            {"id": "gate0.scope", "status": "pending"},
                        ],
                    },
                    {
                        "id": "fde1",
                        "steps": [{"id": "fde1.customer", "status": "done"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    built = build_fde_inventory_from_delivery_plans()
    assert built["ok"] is True
    assert built["required_ids"] == [
        "gate0.deploy_mode",
        "gate0.scope",
        "fde1.customer",
    ]
    assert built["covered_ids"] == ["gate0.deploy_mode", "fde1.customer"]
    assert built["plan_count"] == 1

    def fake_analyze(**kwargs):
        return {"ok": True, "gaps": [{"capability_id": "cap.x", "ok": False}]}

    monkeypatch.setattr(
        "core.apps.eval.service.capability_coverage_fill.analyze_capability_coverage",
        fake_analyze,
    )
    r = refresh_domain_inventories(persist=True)
    assert r["fde"]["required_ids"] == built["required_ids"]
    assert r["fde"]["covered_ids"] == built["covered_ids"]
    assert load_inventory_file("fde_inventory")["source"] == "delivery_plan_skeleton+plans"

    _clear_proposals_for_tests()
    # 人工 eval 已存在时 only_missing 扫描应补写 fde、不覆盖 eval
    inv_dir = tmp_path / "digital_human"
    inv_dir.mkdir(parents=True, exist_ok=True)
    (inv_dir / "eval_inventory.json").write_text(
        json.dumps({"required_ids": ["manual.a"], "covered_ids": []}),
        encoding="utf-8",
    )
    (inv_dir / "fde_inventory.json").unlink(missing_ok=True)
    scan = scan_domain_evolution_proposals(
        use_fixtures_if_empty=False,
        include_evolver_snapshot=False,
        knowledge_cases=[],
    )
    assert scan["live"]["refreshed"] is True
    assert load_inventory_file("eval_inventory")["required_ids"] == ["manual.a"]
    assert load_inventory_file("fde_inventory")["required_ids"] == built["required_ids"]
    assert "fde_evolve" in scan["created"] or any(
        s.get("domain") == "fde" for s in scan["skipped"]
    )
