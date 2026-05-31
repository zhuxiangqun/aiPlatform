import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_project():
    response = client.post("/api/projects", json={"name": "Test Project", "requirements": "Test requirements"})
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert data["status"] == "created"

def test_get_project():
    # First create a project
    create_resp = client.post("/api/projects", json={"name": "Test", "requirements": "Req"})
    project_id = create_resp.json()["project_id"]
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["project"]["name"] == "Test"

def test_confirm_prd():
    create_resp = client.post("/api/projects", json={"name": "Test", "requirements": "Req"})
    project_id = create_resp.json()["project_id"]
    response = client.post(f"/api/projects/{project_id}/confirm-prd")
    assert response.status_code == 200
    assert response.json()["status"] == "prd_confirmed"

def test_assign_roles():
    create_resp = client.post("/api/projects", json={"name": "Test", "requirements": "Req"})
    project_id = create_resp.json()["project_id"]
    roles = [{"role_name": "product_manager", "user_id": "user1"}]
    response = client.post(f"/api/projects/{project_id}/roles", json={"roles": roles})
    assert response.status_code == 200
    assert response.json()["status"] == "roles assigned"