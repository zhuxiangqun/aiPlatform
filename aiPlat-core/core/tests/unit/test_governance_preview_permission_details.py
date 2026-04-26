from core.server import _skill_governance_preview


def test_governance_preview_includes_permission_details():
    out = _skill_governance_preview(
        scope="workspace",
        payload={
            "skill_kind": "executable",
            "permissions": ["llm:generate", "tool:webfetch", "tool:run_command"],
            "config": {},
            "tenant_id": "ops",
            "actor_id": "admin",
        },
    )
    assert out["risk_level"] in ("medium", "high")
    assert "permission_details" in out
    pd = out["permission_details"]
    assert "tool:run_command" in pd
    assert pd["tool:run_command"]["risk_level"] == "high"
    assert isinstance(pd["tool:run_command"].get("suggestions"), list)
    assert "recommendations" in out

