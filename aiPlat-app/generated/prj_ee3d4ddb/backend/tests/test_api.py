import pytest
from httpx import AsyncClient
from backend.main import app

@pytest.mark.asyncio
async def test_create_project():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/projects", json={"name": "Test Project", "requirements": "Test requirements"})
        assert response.status_code == 200
        assert response.json()["status"] == "created"

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"