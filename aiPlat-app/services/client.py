"""
API Client - API 客户端

封装与 platform 层通信的 HTTP 客户端。
"""

from typing import Any, Optional, Dict
import requests
from datetime import datetime


class APIClient:
    """API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8080", api_key: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self._session = requests.Session()
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "aiPlat-app/0.1.0",
        }

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key
        self._headers["Authorization"] = f"Bearer {api_key}"

    def set_tenant_id(self, tenant_id: str) -> None:
        self._headers["X-AIPLAT-TENANT-ID"] = tenant_id

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(
                method,
                url,
                json=data,
                params=params,
                headers=self._headers,
                timeout=30,
            )
            return resp
        except requests.RequestException as e:
            return type("Response", (), {"status_code": 500, "json": lambda: {"error": str(e)}})()

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = self._request("GET", path, params=params)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}

    def post(self, path: str, data: dict) -> dict:
        resp = self._request("POST", path, data=data)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}

    def put(self, path: str, data: dict) -> dict:
        resp = self._request("PUT", path, data=data)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}

    def delete(self, path: str) -> dict:
        resp = self._request("DELETE", path)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}

    def health_check(self) -> dict:
        return self.get("/health")


api_client = APIClient()