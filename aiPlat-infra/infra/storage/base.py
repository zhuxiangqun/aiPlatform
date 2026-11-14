"""storage/base：存储客户端抽象接口。"""

from abc import ABC, abstractmethod
from typing import List, Optional, Any


class StorageClient(ABC):
    """键值存储抽象接口。"""

    @abstractmethod
    async def save(self, key: str, data: Any) -> str:
        """保存数据。

        Args:
            key: 存储键。
            data: 待存数据。
        """
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Any]:
        """加载数据。

        Args:
            key: 存储键。
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除键。

        Args:
            key: 存储键。
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """判断键是否存在。

        Args:
            key: 存储键。
        """
        pass

    @abstractmethod
    async def list(self, prefix: str) -> List[str]:
        """按前缀列出键。

        Args:
            prefix: 键前缀。
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """清空存储。"""
        pass


class FileStorage(ABC):
    """文件存储抽象接口。"""

    @abstractmethod
    async def save_file(self, path: str, content: bytes) -> str:
        """保存文件。

        Args:
            path: 文件路径。
            content: 文件字节。
        """
        pass

    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        """读取文件。

        Args:
            path: 文件路径。
        """
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """删除文件。

        Args:
            path: 文件路径。
        """
        pass

    @abstractmethod
    async def list_files(self, dir: str) -> List[str]:
        """列出目录下文件。

        Args:
            dir: 目录路径。
        """
        pass

    @abstractmethod
    async def get_size(self, path: str) -> int:
        """获取文件大小。

        Args:
            path: 文件路径。
        """
        pass


class ObjectStorage(ABC):
    """对象存储抽象接口。"""

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """上传对象。

        Args:
            key: 对象键。
            data: 对象字节。
            content_type: MIME 类型。
        """
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """下载对象。

        Args:
            key: 对象键。
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除对象。

        Args:
            key: 对象键。
        """
        pass

    @abstractmethod
    async def list_objects(self, prefix: str) -> List[str]:
        """按前缀列出对象。

        Args:
            prefix: 键前缀。
        """
        pass

    @abstractmethod
    def get_presigned_url(self, key: str, expires: int) -> str:
        """生成预签名 URL。

        Args:
            key: 对象键。
            expires: 过期秒数。
        """
        pass
