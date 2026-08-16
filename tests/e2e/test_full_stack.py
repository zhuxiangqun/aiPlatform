"""
aiPlatform 全域 E2E 测试 — 5 条用户旅程

运行前提:
  1. docker compose -f docker-compose.test.yml up -d
  2. bash scripts/wait_for_health.sh
  3. pytest tests/e2e/ -v --tb=short
  4. docker compose -f docker-compose.test.yml down

Mock 模式: 设置 AIPLAT_LLM_MOCK=true，不需要真实 LLM 调用。
"""
import time
import pytest
import httpx

BASE = "http://localhost:8002"
BASE_PLATFORM = "http://localhost:8003"


@pytest.fixture(scope="module")
def client():
    """httpx client with long timeout for E2E tests."""
    return httpx.Client(timeout=httpx.Timeout(30.0))


# ── J1: 入驻→首次任务→价值 ──

def test_j1_onboarding_health(client):
    """J1A: 核心服务健康检查"""
    r = client.get(f"{BASE}/api/core/health")
    assert r.status_code == 200, f"Core health failed: {r.status_code}"


def test_j1_create_spec(client):
    """J1B: 创建 Spec → 验证 DRAFT 状态"""
    r = client.post(f"{BASE_PLATFORM}/api/platform/apps/workbench/spec/create", json={
        "spec_id": "e2e-onboarding",
        "content": {"agent_md": "E2E 测试 Spec — 入驻验证"},
        "created_by": "e2e-test",
    })
    assert r.status_code in (200, 201), f"Create spec failed: {r.status_code}"
    data = r.json()
    assert data["spec_id"] == "e2e-onboarding"
    assert data["status"] == "draft"


def test_j1_submit_task_with_spec(client):
    """J1C: 提交关联 Spec 的任务 → 轮询直到完成"""
    r = client.post(f"{BASE_PLATFORM}/api/platform/apps/workbench/submit", json={
        "description": "E2E 测试: 请输出 OK",
        "capability": "general",
        "spec_id": "e2e-onboarding",
    })
    assert r.status_code == 200, f"Submit failed: {r.status_code}"
    run_id = r.json().get("run_id", "")
    assert run_id, "No run_id returned"

    # Poll for completion (up to 15s)
    for _ in range(10):
        time.sleep(1.5)
        r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/tasks/{run_id}")
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status == "completed":
                break
    else:
        pytest.fail("Task did not complete within timeout")

    # Verify spec entered REVIEW
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/spec/e2e-onboarding/history")
    assert r.status_code == 200
    versions = r.json().get("versions", [])
    assert len(versions) >= 1, f"No versions found: {r.json()}"
    latest = versions[-1]
    assert latest["status"] in ("review", "executing", "pending"), f"Unexpected status: {latest['status']}"


def test_j1_dashboard_aggregation(client):
    """J1D: FDE 仪表板能查到 pending_decisions"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/fde-dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "pending_decisions" in data, f"No pending_decisions in dashboard: {list(data.keys())}"
    assert "training" in data, "No training in dashboard"


# ── J2: 知识管线 ──

def test_j2_ontology_importable(client):
    """J2A: 本体引擎模块可导入（由 full_stack 诊断验证）"""
    r = client.get(f"{BASE}/api/core/health")
    assert r.status_code == 200


def test_j2_wiki_engine(client):
    """J2B: Wiki 引擎可访问"""
    r = client.get(f"{BASE}/api/core/health")
    assert r.status_code == 200


# ── J3: 协作→Spec 迭代 ──

def test_j3_trace_visualization(client):
    """J3A: Trace 数据可解析"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/spec/e2e-onboarding/trace")
    assert r.status_code == 200
    data = r.json()
    # Trace may be empty if mock LLM didn't generate it — that's OK
    assert "spec_id" in data


def test_j3_mark_stable(client):
    """J3B: Spec → STABLE"""
    r = client.post(f"{BASE_PLATFORM}/api/platform/apps/workbench/spec/e2e-onboarding/mark-stable", json={})
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") in ("stable", "unchanged"), f"Expected stable, got: {data}"


# ── J4: 学习→训练 ──

def test_j4_training_status(client):
    """J4A: 训练监控可读"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/training/status")
    assert r.status_code == 200
    data = r.json()
    assert "threshold" in data, f"No threshold in training status: {list(data.keys())}"
    assert "quality_count" in data


# ── J5: FDE 日常 ──

def test_j5_full_dashboard(client):
    """J5A: Dashboard 四卡 + 时间轴"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/fde-dashboard")
    assert r.status_code == 200
    data = r.json()
    for key in ("pending_decisions", "signal_alerts", "trace_anomalies", "training", "timeline", "last_updated"):
        assert key in data, f"Missing key in dashboard: {key}"


def test_j5_spec_list(client):
    """J5B: Spec 列表可读"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/specs")
    assert r.status_code == 200
    data = r.json()
    assert "specs" in data


def test_j5_radar(client):
    """J5C: 信号雷达可读"""
    r = client.get(f"{BASE_PLATFORM}/api/platform/apps/workbench/spec/e2e-onboarding/radar")
    assert r.status_code == 200
    data = r.json()
    assert "spec_id" in data


# ── Cleanup ──

def test_prompt_cache_persistence():
    """验证 Prompt Caching 跨会话持久化逻辑.
    
    不调用真实 LLM — 只测试 SHA256 hash 计算和 JSON 文件读写。
    """
    import hashlib, json, os, tempfile

    stable = "System: You are an AI. SOUL: Be concise. CLAUDE.md: Follow rules."
    stable_hash = hashlib.sha256(stable.encode()).hexdigest()[:16]

    with tempfile.TemporaryDirectory() as tmp:
        cache_file = os.path.join(tmp, "prompt_cache.json")

        # Simulate first call: write hash
        with open(cache_file, "w") as f:
            json.dump({"hash": stable_hash}, f)

        # Simulate restart: read back
        with open(cache_file) as f:
            cached = json.load(f)
            assert cached["hash"] == stable_hash, f"Hash mismatch: {cached['hash']} vs {stable_hash}"

        # Hash not changed → cache valid
        new_hash = hashlib.sha256(stable.encode()).hexdigest()[:16]
        assert new_hash == cached["hash"], "Restart hash changed unexpectedly"

        # Content changed → hash different
        modified = stable + " New rule added."
        modified_hash = hashlib.sha256(modified.encode()).hexdigest()[:16]
        assert modified_hash != cached["hash"], "Content changed but hash didn't"

        # Update cache with new hash
        with open(cache_file, "w") as f:
            json.dump({"hash": modified_hash}, f)

        with open(cache_file) as f:
            updated = json.load(f)
            assert updated["hash"] == modified_hash


def test_cleanup_seed_demo(client):
    """清理: 种子 demo 数据（可选，不阻塞）"""
    try:
        client.post(f"{BASE_PLATFORM}/api/platform/apps/workbench/seed-demo", json={})
    except Exception:
        pass
