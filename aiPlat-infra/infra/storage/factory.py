from typing import Optional
from .schemas import StorageConfig
from .base import StorageClient, FileStorage, ObjectStorage


def create(config: Optional[StorageConfig] = None) -> StorageClient:
    """创建存储客户端（便捷函数）"""
    return create_storage_client(config)


def create_storage_client(config: Optional[StorageConfig] = None) -> StorageClient:
    config = config or StorageConfig()

    if config.type == "file":
        from .clients import LocalStorageClient

        return LocalStorageClient(config)
    elif config.type in ("s3", "aws"):
        try:
            from .clients import S3StorageClient

            return S3StorageClient(config)
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 support. Install with: pip install boto3"
            )
    elif config.type == "gcs":
        try:
            from .clients import GCSStorageClient

            return GCSStorageClient(config)
        except ImportError:
            raise ImportError(
                "google-cloud-storage is required for GCS support. Install with: pip install google-cloud-storage"
            )
    elif config.type == "azure":
        try:
            from .clients import AzureStorageClient

            return AzureStorageClient(config)
        except ImportError:
            raise ImportError(
                "azure-storage-blob is required for Azure support. Install with: pip install azure-storage-blob"
            )
    else:
        raise ValueError(f"Unknown storage type: {config.type}")
