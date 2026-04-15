from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Union
from .response import Response


class HTTPClient(ABC):
    @abstractmethod
    def get(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def post(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def put(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def patch(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def delete(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def head(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def options(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class AsyncHTTPClient(ABC):
    @abstractmethod
    async def get(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def post(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def put(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def patch(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def delete(self, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def request(self, method: str, url: str, **kwargs: Any) -> Response:
        pass

    @abstractmethod
    async def aclose(self) -> None:
        pass
