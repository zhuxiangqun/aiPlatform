from typing import Optional, Union
from .schemas import HTTPConfig
from .httpx_client import SyncHTTPClient, AsyncHTTPClientImpl
from .aiohttp_client import AioHttpClient


def create(
    config: Optional[HTTPConfig] = None,
    async_mode: bool = False,
    use_aiohttp: bool = False,
) -> Union[SyncHTTPClient, AsyncHTTPClientImpl, AioHttpClient]:
    """创建 HTTP 客户端（便捷函数）"""
    return create_http_client(config, async_mode, use_aiohttp)


def create_http_client(
    config: Optional[HTTPConfig] = None,
    async_mode: bool = False,
    use_aiohttp: bool = False,
) -> Union[SyncHTTPClient, AsyncHTTPClientImpl, AioHttpClient]:
    if async_mode:
        if use_aiohttp:
            return AioHttpClient(config)
        return AsyncHTTPClientImpl(config)
    return SyncHTTPClient(config)
