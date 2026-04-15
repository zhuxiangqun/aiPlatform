import time
from typing import Optional, Dict, Any
from .base import HTTPClient, AsyncHTTPClient
from .schemas import HTTPConfig
from .response import Response


class SyncHTTPClient(HTTPClient):
    def __init__(self, config: Optional[HTTPConfig] = None):
        self.config = config or HTTPConfig()
        import httpx

        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=self.config.timeout.connect,
                read=self.config.timeout.read,
                write=self.config.timeout.write,
                pool=self.config.timeout.pool,
            ),
            proxy=self._get_proxy(),
            headers=self.config.headers or {},
        )

    def _get_proxy(self) -> Optional[str]:
        proxies = {}
        if self.config.proxy.http:
            proxies["http://"] = self.config.proxy.http
        if self.config.proxy.https:
            proxies["https://"] = self.config.proxy.https
        return proxies if proxies else None

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        retry_config = self.config.retry
        max_attempts = retry_config.max_attempts if retry_config.enabled else 1

        last_exception = None
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                response = self._client.request(method, url, **kwargs)
                elapsed = time.time() - start_time

                if (
                    retry_config.enabled
                    and response.status_code in retry_config.retry_on_status
                ):
                    if attempt < max_attempts - 1:
                        backoff = retry_config.backoff_factor**attempt
                        time.sleep(backoff)
                        continue

                return Response(
                    status_code=response.status_code,
                    text=response.text,
                    headers=dict(response.headers),
                    cookies=dict(response.cookies),
                    elapsed=elapsed,
                    _content=response.content,
                )
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    backoff = retry_config.backoff_factor**attempt
                    time.sleep(backoff)
                else:
                    raise

        raise last_exception

    def get(self, url: str, **kwargs: Any) -> Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self._request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Response:
        return self._request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self._request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> Response:
        return self._request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> Response:
        return self._request("OPTIONS", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        return self._request(method, url, **kwargs)

    def close(self) -> None:
        self._client.close()


class AsyncHTTPClientImpl(AsyncHTTPClient):
    def __init__(self, config: Optional[HTTPConfig] = None):
        self.config = config or HTTPConfig()
        import httpx

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.config.timeout.connect,
                read=self.config.timeout.read,
                write=self.config.timeout.write,
                pool=self.config.timeout.pool,
            ),
            proxy=self._get_proxy(),
            headers=self.config.headers or {},
        )

    def _get_proxy(self) -> Optional[str]:
        if self.config.proxy.https:
            return self.config.proxy.https
        if self.config.proxy.http:
            return self.config.proxy.http
        return None

    async def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        import asyncio

        retry_config = self.config.retry
        max_attempts = retry_config.max_attempts if retry_config.enabled else 1

        last_exception = None
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                response = await self._client.request(method, url, **kwargs)
                elapsed = time.time() - start_time

                if (
                    retry_config.enabled
                    and response.status_code in retry_config.retry_on_status
                ):
                    if attempt < max_attempts - 1:
                        backoff = retry_config.backoff_factor**attempt
                        await asyncio.sleep(backoff)
                        continue

                return Response(
                    status_code=response.status_code,
                    text=response.text,
                    headers=dict(response.headers),
                    cookies=dict(response.cookies),
                    elapsed=elapsed,
                    _content=response.content,
                )
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    backoff = retry_config.backoff_factor**attempt
                    await asyncio.sleep(backoff)
                else:
                    raise

        raise last_exception

    async def get(self, url: str, **kwargs: Any) -> Response:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Response:
        return await self._request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Response:
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Response:
        return await self._request("DELETE", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> Response:
        return await self._request(method, url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()
