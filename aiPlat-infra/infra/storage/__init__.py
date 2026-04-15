from .base import StorageClient, FileStorage, ObjectStorage
from .schemas import StorageConfig, FileConfig, ObjectConfig, TempConfig
from .factory import create_storage_client

__all__ = [
    "StorageClient",
    "FileStorage",
    "ObjectStorage",
    "StorageConfig",
    "FileConfig",
    "ObjectConfig",
    "TempConfig",
    "create_storage_client",
]

try:
    from .clients import (
        LocalStorageClient,
        S3StorageClient,
        GCSStorageClient,
        AzureStorageClient,
    )

    __all__.extend(
        [
            "LocalStorageClient",
            "S3StorageClient",
            "GCSStorageClient",
            "AzureStorageClient",
        ]
    )
except ImportError:
    pass
