import time
from typing import Optional, Dict, Any
import aiohttp
from .base import AsyncHTTPClient
from .schemas import HTTPConfig
from .response import Response


class AioHttpClient(AsyncHTTPClient):
    def __init__(self, config: Optional[HTTPConfig] = None):
        self.config = config or HTTPConfig()
        self._client: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._client is None or self._client.closed:
            timeout = aiohttp.ClientTimeout(
                connect=self.config.timeout.connect, total=self.config.timeout.read
            )
            self._client = aiohttp.ClientSession(
                timeout=timeout, headers=self.config.headers or {}
            )
        return self._client

    async def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        import asyncio

        session = await self._get_session()
        retry_config = self.config.retry
        max_attempts = retry_config.max_attempts if retry_config.enabled else 1

        last_exception = None
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                async with session.request(method, url, **kwargs) as response:
                    elapsed = time.time() - start_time
                    text = await response.text()

                    if (
                        retry_config.enabled
                        and response.status in retry_config.retry_on_status
                    ):
                        if attempt < max_attempts - 1:
                            backoff = retry_config.backoff_factor**attempt
                            await asyncio.sleep(backoff)
                            continue

                    return Response(
                        status_code=response.status,
                        text=text,
                        headers=dict(response.headers),
                        cookies={c.key: c.value for c in response.cookies.values()},
                        elapsed=elapsed,
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
        if self._client and not self._client.closed:
            await self._client.close()
