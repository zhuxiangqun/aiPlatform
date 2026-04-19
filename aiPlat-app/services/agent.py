"""
Agent Service - Agent API Client

Agent 相关的 API 服务封装。
"""

from typing import Any, Optional, Dict, List
from .client import APIClient


class AgentService:
    """Agent 服务"""

    def __init__(self, client: APIClient):
        self._client = client

    def list(self, limit: int = 100) -> List[Dict]:
        resp = self._client.get("/api/v1/agents", {"limit": limit})
        return resp.get("agents", [])

    def get(self, agent_id: str) -> Optional[Dict]:
        resp = self._client.get(f"/api/v1/agents/{agent_id}")
        return resp.get("agent")

    def create(self, name: str, description: str = "", **kwargs) -> Dict:
        data = {"name": name, "description": description}
        data.update(kwargs)
        resp = self._client.post("/api/v1/agents", data)
        return resp

    def execute(self, agent_id: str, input: str, **kwargs) -> Dict:
        data = {"input": input}
        data.update(kwargs)
        resp = self._client.post(f"/api/v1/agents/{agent_id}/execute", data)
        return resp

    def delete(self, agent_id: str) -> bool:
        resp = self._client.delete(f"/api/v1/agents/{agent_id}")
        return resp.get("ok", False)


def get_agent_service(base_url: str = "http://localhost:8080", api_key: str = "") -> AgentService:
    """获取 Agent 服务实例"""
    client = APIClient(base_url=base_url, api_key=api_key)
    return AgentService(client)


agent_service = AgentService(APIClient())