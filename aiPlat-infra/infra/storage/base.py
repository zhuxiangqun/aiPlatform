from abc import ABC, abstractmethod
from typing import List, Optional, Any


class StorageClient(ABC):
    @abstractmethod
    async def save(self, key: str, data: Any) -> str:
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def list(self, prefix: str) -> List[str]:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass


class FileStorage(ABC):
    @abstractmethod
    async def save_file(self, path: str, content: bytes) -> str:
        pass

    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        pass

    @abstractmethod
    async def list_files(self, dir: str) -> List[str]:
        pass

    @abstractmethod
    async def get_size(self, path: str) -> int:
        pass


class ObjectStorage(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def list_objects(self, prefix: str) -> List[str]:
        pass

    @abstractmethod
    def get_presigned_url(self, key: str, expires: int) -> str:
        pass
