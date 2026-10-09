"""Code-review gold — matcher + profiles + match_only eval."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.evaluation.code_review_gold import (
    GoldFinding,
    finding_matches_issue,
    list_profiles,
    load_gold_cases,
    match_review_findings,
    profile_to_autoreview_args,
    run_code_review_gold_eval,
    score_case,
    GoldCase,
)


SEED = (
    Path(__file__).resolve().parents[4]
    / "workspace_seeds"
    / "eval"
    / "code_review_gold"
)


def test_profiles_map_to_autoreview_args():
    low = profile_to_autoreview_args("low_noise")
    assert low["panel"] is False
    bal = profile_to_autoreview_args("balanced")
    assert bal["panel"] == "auto"
    high = profile_to_autoreview_args("high_coverage")
    assert high["panel"] is True and high["mode"] == "deep" and high["focus"] == "security"
    assert set(list_profiles()) == {"low_noise", "balanced", "high_coverage"}
    with pytest.raises(ValueError):
        profile_to_autoreview_args("turbo")


def test_matcher_precision_recall():
    gold = [
        GoldFinding(file="app/auth.py", line=42, severity="P0", keywords=["sql", "injection"]),
        GoldFinding(file="app/auth.py", line=88, severity="P1", keywords=["password", "plaintext"]),
    ]
    predicted = [
        {"file": "app/auth.py", "line": 41, "severity": "P0", "description": "SQL injection via f-string"},
        {"file": "app/utils.py", "line": 3, "severity": "P2", "description": "Unused import"},
    ]
    m = match_review_findings(predicted, gold, line_window=5)
    assert m["tp"] == 1
    assert m["fp"] == 1
    assert m["fn"] == 1
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5
    assert m["p0_recall"] == 1.0
    assert m["comment_count"] == 2


def test_line_window_and_basename():
    g = GoldFinding(file="auth.py", line=10, severity="P1", keywords=["jwt", "skew"])
    assert finding_matches_issue(
        g,
        {"file": "services/auth.py", "line": 12, "description": "JWT clock skew missing"},
        line_window=5,
    )
    assert not finding_matches_issue(
        g,
        {"file": "services/auth.py", "line": 99, "description": "JWT clock skew missing"},
        line_window=5,
    )


def test_load_seed_cases():
    assert SEED.is_dir(), SEED
    cases = load_gold_cases(str(SEED))
    ids = {c.id for c in cases}
    assert "sql_injection_auth" in ids
    assert "jwt_expiry_skew" in ids
    assert len(ids) >= 40, f"expected ≥40 unique gold cases, got {len(ids)}"
    assert len(cases) == len(ids), "duplicate case ids after load"


@pytest.mark.asyncio
async def test_match_only_eval_on_seeds():
    # Pin singleton seeds so batch_*.yaml growth does not inflate scored_count
    out = await run_code_review_gold_eval(
        profile="balanced",
        gold_dir=str(SEED),
        case_ids=["sql_injection_auth", "jwt_expiry_skew"],
        match_only=True,
        persist=False,
    )
    assert out["ok"] is True
    assert out["scored_count"] == 2
    assert out["precision"] is not None and out["precision"] > 0.5
    assert out["recall"] is not None and out["recall"] > 0.5
    assert out.get("harness_factors")
    sql = next(c for c in out["cases"] if c["id"] == "sql_injection_auth")
    assert sql["tp"] == 2
    assert sql["fp"] == 1
    assert sql["precision"] == pytest.approx(2 / 3, rel=1e-3)
    assert sql["recall"] == 1.0
    assert sql["p0_recall"] == 1.0


@pytest.mark.asyncio
async def test_live_path_uses_execute_fn():
    async def fake_execute(params):
        assert params.get("target") == "diff"
        assert "panel" in params
        return {
            "report": {
                "issues": [
                    {
                        "file": "a.py",
                        "line": 1,
                        "severity": "P0",
                        "description": "hardcoded secret api_key",
                    }
                ]
            },
            "clean": False,
        }

    import tempfile
    import yaml

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "live1.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "id": "live1",
                    "target": "diff",
                    "gold_findings": [
                        {
                            "file": "a.py",
                            "line": 1,
                            "severity": "P0",
                            "keywords": ["secret", "api_key"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = await run_code_review_gold_eval(
            profile="high_coverage",
            gold_dir=td,
            execute_fn=fake_execute,
            persist=False,
        )
    assert out["ok"] and out["scored_count"] == 1
    assert out["cases"][0]["precision"] == 1.0
    assert out["cases"][0]["exec"]["mode"] == "live"


@pytest.mark.asyncio
async def test_novel_and_persist_report(tmp_path, monkeypatch):
    import yaml
    from core.harness.evaluation import code_review_gold as crg

    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "n1.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "n1",
                "gold_findings": [
                    {"file": "a.py", "line": 1, "severity": "P0", "keywords": ["sql"]},
                ],
                "predicted": [
                    {"file": "a.py", "line": 1, "severity": "P0", "description": "sql injection"},
                    {"file": "b.py", "line": 9, "severity": "P1", "description": "auth bypass novel"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(crg, "reports_dir", lambda tenant_id="": tmp_path / "reports")
    out = await run_code_review_gold_eval(
        profile="balanced",
        gold_dir=str(gold),
        match_only=True,
        persist=True,
        record_novel=False,
    )
    assert out.get("novel_count", 0) >= 1
    assert any(n.get("kind") == "novel_candidate" for n in out.get("novel_findings") or [])
    report = tmp_path / "reports" / "runs.jsonl"
    assert report.is_file()
    rows = crg.list_eval_reports()
    assert rows and rows[-1].get("ok") is True
    assert "precision" in rows[-1]


def test_score_case_helper():
    case = GoldCase(
        id="x",
        gold_findings=[GoldFinding(file="f.py", line=1, severity="P2", keywords=["todo"])],
    )
    s = score_case(case, [{"file": "f.py", "line": 1, "description": "FIXME todo left"}])
    assert s["id"] == "x" and s["tp"] == 1
