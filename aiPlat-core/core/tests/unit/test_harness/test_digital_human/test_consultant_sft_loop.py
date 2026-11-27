"""consultant_sft_loop：ShareGPT 转换 + 门槛/防抖/dry-run。"""
from __future__ import annotations

import json
from types import SimpleNamespace

from core.harness.digital_human.consultant_sft_loop import (
    maybe_submit_digital_human_sft,
    sharegpt_to_messages_jsonl,
)


def test_sharegpt_to_messages_jsonl():
    line = json.dumps(
        {
            "conversations": [
                {"from": "human", "value": "你好"},
                {"from": "gpt", "value": "你好，我是小朱"},
            ]
        },
        ensure_ascii=False,
    )
    out = sharegpt_to_messages_jsonl(line + "\n")
    obj = json.loads(out.strip())
    roles = [m["role"] for m in obj["messages"]]
    assert roles == ["user", "assistant"]


def test_need_more_and_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_DH_SFT_MIN_SAMPLES", "10")
    monkeypatch.setenv("AIPLAT_DH_SFT_AUTO_SUBMIT", "1")

    def fake_export(**kwargs):
        return {"samples": 2, "output_path": ""}

    monkeypatch.setattr(
        "core.harness.digital_human.trajectory_collector.export_curated_sharegpt_dataset",
        fake_export,
    )
    r = maybe_submit_digital_human_sft()
    assert r["submitted"] is False
    assert r["reason"] == "need_more"

    def fake_export10(**kwargs):
        p = tmp_path / "training" / "curated.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(10):
            rows.append(
                json.dumps(
                    {
                        "conversations": [
                            {"from": "human", "value": f"q{i}"},
                            {"from": "gpt", "value": f"a{i}"},
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return {"samples": 10, "output_path": str(p)}

    monkeypatch.setattr(
        "core.harness.digital_human.trajectory_collector.export_curated_sharegpt_dataset",
        fake_export10,
    )
    dry = maybe_submit_digital_human_sft(dry_run=True)
    assert dry["submitted"] is False
    assert dry["reason"] == "dry_run"
    assert dry["sample_count"] == 10


def test_auto_submit_disabled_and_debounce(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_DH_SFT_MIN_SAMPLES", "3")
    monkeypatch.setenv("AIPLAT_DH_SFT_AUTO_SUBMIT", "0")

    def fake_export(**kwargs):
        p = tmp_path / "training" / "c.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(3):
            rows.append(
                json.dumps(
                    {
                        "conversations": [
                            {"from": "human", "value": f"qq{i}"},
                            {"from": "gpt", "value": f"aa{i}"},
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return {"samples": 3, "output_path": str(p)}

    monkeypatch.setattr(
        "core.harness.digital_human.trajectory_collector.export_curated_sharegpt_dataset",
        fake_export,
    )
    r = maybe_submit_digital_human_sft()
    assert r["reason"] == "auto_submit_disabled"

    monkeypatch.setenv("AIPLAT_DH_SFT_AUTO_SUBMIT", "1")

    class FakeProv:
        available = True

        def check_quota(self):
            return {"used": 0, "total": 1, "available": 1}

    class FakeJobMgr:
        def _get_provider(self, pref):
            return FakeProv()

        def create(self, req):
            return SimpleNamespace(id="job_test_1")

    class FakeDsMgr:
        def list_all(self, limit=200):
            return SimpleNamespace(datasets=[])

        def create(self, req):
            return SimpleNamespace(id="ds_test_1")

        def import_jsonl(self, dataset_id, content):
            return SimpleNamespace(sample_count=3, id=dataset_id)

    monkeypatch.setattr(
        "core.harness.digital_human.consultant_sft_loop._pick_provider",
        lambda: (__import__("core.apps.finetune.schemas", fromlist=["FineTuneProvider"]).FineTuneProvider.LOCAL, FakeJobMgr()),
    )
    monkeypatch.setattr(
        "core.apps.finetune.dataset_manager.DatasetManager",
        FakeDsMgr,
    )
    monkeypatch.setattr(
        "core.harness.digital_human.consultant_sft_loop._resolve_base_model",
        lambda: "deepseek-chat",
    )

    ok = maybe_submit_digital_human_sft()
    assert ok["submitted"] is True
    assert ok["job_id"] == "job_test_1"

    again = maybe_submit_digital_human_sft()
    assert again["submitted"] is False
    assert again["reason"] == "already_submitted"
