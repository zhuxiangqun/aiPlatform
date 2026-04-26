from fastapi.testclient import TestClient


def test_routing_metric_tags_api_smoke():
    import core.server as srv

    with TestClient(srv.app) as client:
        r = client.get("/api/core/workspace/skills/observability/routing-metrics/tags")
        assert r.status_code == 200
        js = r.json()
        assert js.get("status") == "ok"
        assert "scalars" in js and "hists" in js

