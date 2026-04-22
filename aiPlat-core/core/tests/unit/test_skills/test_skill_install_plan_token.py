import time

import pytest


def test_plan_token_ok(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET", "secret")
    from core.management.skill_install_plan_token import build_plan_token, verify_plan_token

    data = {"a": 1, "b": "x"}
    token, exp = build_plan_token(data=data, ttl_seconds=60)
    assert exp > time.time()
    verify_plan_token(token=token, expected_data=data, now=time.time())


def test_plan_token_mismatch(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET", "secret")
    from core.management.skill_install_plan_token import build_plan_token, verify_plan_token

    token, _ = build_plan_token(data={"a": 1}, ttl_seconds=60)
    with pytest.raises(ValueError):
        verify_plan_token(token=token, expected_data={"a": 2}, now=time.time())


def test_plan_token_digest_change(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET", "secret")
    from core.management.skill_install_plan_token import build_plan_token, verify_plan_token

    token, _ = build_plan_token(data={"planned_skills_digest": "aaa"}, ttl_seconds=60)
    with pytest.raises(ValueError):
        verify_plan_token(token=token, expected_data={"planned_skills_digest": "bbb"}, now=time.time())


def test_plan_token_expired(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET", "secret")
    from core.management.skill_install_plan_token import build_plan_token, verify_plan_token

    token, exp = build_plan_token(data={"a": 1}, ttl_seconds=1)
    with pytest.raises(ValueError):
        verify_plan_token(token=token, expected_data={"a": 1}, now=exp + 10)
