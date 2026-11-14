"""http/base：HTTP 客户端抽象接口。"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Union
from .response import Response


class HTTPClient(ABC):
    """同步 HTTP 客户端抽象接口。"""

    @abstractmethod
    def get(self, url: str, **kwargs: Any) -> Response:
        """发送 GET 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def post(self, url: str, **kwargs: Any) -> Response:
        """发送 POST 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def put(self, url: str, **kwargs: Any) -> Response:
        """发送 PUT 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def patch(self, url: str, **kwargs: Any) -> Response:
        """发送 PATCH 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def delete(self, url: str, **kwargs: Any) -> Response:
        """发送 DELETE 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def head(self, url: str, **kwargs: Any) -> Response:
        """发送 HEAD 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def options(self, url: str, **kwargs: Any) -> Response:
        """发送 OPTIONS 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        """发送任意方法请求。

        Args:
            method: HTTP 方法。
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭客户端并释放连接。"""
        pass


class AsyncHTTPClient(ABC):
    """异步 HTTP 客户端抽象接口。"""

    @abstractmethod
    async def get(self, url: str, **kwargs: Any) -> Response:
        """异步发送 GET 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def post(self, url: str, **kwargs: Any) -> Response:
        """异步发送 POST 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def put(self, url: str, **kwargs: Any) -> Response:
        """异步发送 PUT 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def patch(self, url: str, **kwargs: Any) -> Response:
        """异步发送 PATCH 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def delete(self, url: str, **kwargs: Any) -> Response:
        """异步发送 DELETE 请求。

        Args:
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def request(self, method: str, url: str, **kwargs: Any) -> Response:
        """异步发送任意方法请求。

        Args:
            method: HTTP 方法。
            url: 请求 URL。
            kwargs: 附加关键字参数。
        """
        pass

    @abstractmethod
    async def aclose(self) -> None:
        """异步关闭客户端并释放连接。"""
        pass
