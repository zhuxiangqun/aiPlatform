"""
API Client - API 客户端

封装与 platform 层通信的 HTTP 客户端。

⚠ I/O: Primary methods use synchronous requests.Session for backward compat.
For async contexts, use async_get/async_post/async_put/async_delete which
use httpx internally. Prefer async methods in new code.
"""

from typing import Any, Optional, Dict
import os
import requests
from datetime import datetime


class APIClient:
    """API 客户端"""

    def __init__(self, base_url: str = "", api_key: str = ""):
        self.base_url = base_url or os.environ.get("AIPLAT_PLATFORM_URL", "http://localhost:8003")
        self.base_url = base_url
        self.api_key = api_key
        self._session = requests.Session()
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "aiPlat-app/0.1.0",
        }

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key
        # Prefer explicit API key header; keep Authorization for compatibility
        self._headers["X-AIPLAT-API-KEY"] = api_key
        self._headers["Authorization"] = f"Bearer {api_key}"

    def set_tenant_id(self, tenant_id: str) -> None:
        self._headers["X-AIPLAT-TENANT-ID"] = tenant_id

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
        files: Optional[dict] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            headers = dict(self._headers)
            # When uploading multipart, requests will set Content-Type automatically.
            if files is not None:
                headers.pop("Content-Type", None)
            resp = self._session.request(
                method,
                url,
                json=data if files is None else None,
                data=None if files is None else (data or None),
                files=files,
                params=params,
                headers=headers,
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

    def post_multipart(self, path: str, *, form: Optional[dict] = None, files: Optional[dict] = None) -> dict:
        """
        发送 multipart/form-data（用于上传文件）。
        files example: {"file": ("name.pdf", open(...,"rb"), "application/pdf")}
        """
        resp = self._request("POST", path, data=form or {}, files=files or {})
        if resp.status_code == 200:
            return resp.json()
        try:
            return {"error": resp.text, "status_code": resp.status_code}
        except Exception:
            return {"error": "request_failed", "status_code": getattr(resp, "status_code", 500)}

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

    # ── Async methods (httpx) ─────────────────────────────────────────

    async def _async_request(self, method: str, path: str, data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        import httpx
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {k: v for k, v in self._headers.items() if k.lower() != "content-type"}
                resp = await client.request(method, url, json=data, params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": resp.text, "status_code": resp.status_code}
        except Exception as e:
            return {"error": str(e), "status_code": 500}

    async def async_get(self, path: str, params: Optional[dict] = None) -> dict:
        return await self._async_request("GET", path, params=params)

    async def async_post(self, path: str, data: dict) -> dict:
        return await self._async_request("POST", path, data=data)

    async def async_put(self, path: str, data: dict) -> dict:
        return await self._async_request("PUT", path, data=data)

    async def async_delete(self, path: str) -> dict:
        return await self._async_request("DELETE", path)

    def health_check(self) -> dict:
        return self.get("/health")


api_client = APIClient()
