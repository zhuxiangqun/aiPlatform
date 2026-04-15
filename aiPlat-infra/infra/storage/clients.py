import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Any
from .base import StorageClient, FileStorage, ObjectStorage
from .schemas import StorageConfig


class LocalStorageClient(StorageClient, FileStorage):
    def __init__(self, config: StorageConfig):
        self.config = config
        base_path = ""
        if config.file and config.file.base_path:
            base_path = config.file.base_path
        self._base_path = (
            Path(base_path)
            if base_path
            else Path(tempfile.gettempdir()) / "ai-platform"
        )
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, key: str, data: Any) -> str:
        path = self._base_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (str, bytes)):
            mode = "wb" if isinstance(data, bytes) else "w"
            with open(path, mode) as f:
                f.write(data)
        else:
            import json

            with open(path, "w") as f:
                json.dump(data, f)
        return str(path)

    async def load(self, key: str) -> Optional[Any]:
        path = self._base_path / key
        if not path.exists():
            return None
        with open(path, "r") as f:
            return f.read()

    async def delete(self, key: str) -> bool:
        path = self._base_path / key
        if path.exists():
            path.unlink()
            return True
        return False

    async def exists(self, key: str) -> bool:
        return (self._base_path / key).exists()

    async def list(self, prefix: str) -> List[str]:
        results = []
        base = self._base_path / prefix
        if base.is_dir():
            for p in base.rglob("*"):
                if p.is_file():
                    results.append(str(p.relative_to(self._base_path)))
        return results

    async def clear(self) -> None:
        if self._base_path.exists():
            shutil.rmtree(self._base_path)
            self._base_path.mkdir(parents=True, exist_ok=True)

    async def save_file(self, path: str, content: bytes) -> str:
        full_path = self._base_path / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)

    async def read_file(self, path: str) -> bytes:
        return (self._base_path / path).read_bytes()

    async def delete_file(self, path: str) -> bool:
        full_path = self._base_path / path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    async def list_files(self, dir: str) -> List[str]:
        full_path = self._base_path / dir
        if not full_path.exists():
            return []
        return [
            str(p.relative_to(full_path)) for p in full_path.iterdir() if p.is_file()
        ]

    async def get_size(self, path: str) -> int:
        return (self._base_path / path).stat().st_size


class S3StorageClient(ObjectStorage):
    def __init__(self, config: StorageConfig):
        self.config = config
        self._client = None

    async def connect(self):
        import boto3

        obj_config = self.config.object
        self._client = boto3.client(
            "s3",
            region_name=obj_config.region if obj_config else "us-east-1",
            aws_access_key_id=obj_config.access_key if obj_config else "",
            aws_secret_access_key=obj_config.secret_key if obj_config else "",
            endpoint_url=obj_config.endpoint
            if obj_config and obj_config.endpoint
            else None,
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        if not self._client:
            await self.connect()
        bucket = (
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        self._client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )
        return key

    async def download(self, key: str) -> bytes:
        if not self._client:
            await self.connect()
        bucket = (
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    async def delete(self, key: str) -> bool:
        if not self._client:
            await self.connect()
        bucket = (
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        self._client.delete_object(Bucket=bucket, Key=key)
        return True

    async def list_objects(self, prefix: str) -> List[str]:
        if not self._client:
            await self.connect()
        bucket = (
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        response = self._client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]

    def get_presigned_url(self, key: str, expires: int) -> str:
        if not self._client:
            import boto3

            obj_config = self.config.object
            self._client = boto3.client(
                "s3",
                region_name=obj_config.region if obj_config else "us-east-1",
                aws_access_key_id=obj_config.access_key if obj_config else "",
                aws_secret_access_key=obj_config.secret_key if obj_config else "",
            )
        bucket = (
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )


class GCSStorageClient(ObjectStorage):
    def __init__(self, config: StorageConfig):
        self.config = config
        self._client = None

    async def connect(self):
        try:
            from google.cloud import storage as cloud_storage
        except ImportError:
            raise ImportError("google-cloud-storage is required for GCS support")

        obj_config = self.config.object
        self._client = cloud_storage.Client(
            project=obj_config.project if obj_config else None,
            credentials=obj_config.credentials if obj_config else None,
        )

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        if not self._client:
            await self.connect()
        bucket = self._client.bucket(
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        blob = bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return key

    async def download(self, key: str) -> bytes:
        if not self._client:
            await self.connect()
        bucket = self._client.bucket(
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        blob = bucket.blob(key)
        return blob.download_as_bytes()

    async def delete(self, key: str) -> bool:
        if not self._client:
            await self.connect()
        bucket = self._client.bucket(
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        blob = bucket.blob(key)
        blob.delete()
        return True

    async def list_objects(self, prefix: str) -> List[str]:
        if not self._client:
            await self.connect()
        bucket = self._client.bucket(
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        return [blob.name for blob in bucket.list_blobs(prefix=prefix)]

    def get_presigned_url(self, key: str, expires: int) -> str:
        if not self._client:
            import asyncio

            asyncio.run(self.connect())
        bucket = self._client.bucket(
            self.config.object.bucket if self.config.object else "ai-platform-bucket"
        )
        blob = bucket.blob(key)
        return blob.generate_signed_url(version="v4", expiration=expires)


class AzureStorageClient(ObjectStorage):
    def __init__(self, config: StorageConfig):
        self.config = config
        self._client = None

    async def connect(self):
        from azure.storage.blob import BlobServiceClient

        obj_config = self.config.object
        connection_string = obj_config.connection_string if obj_config else ""
        self._client = BlobServiceClient.from_connection_string(connection_string)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        if not self._client:
            await self.connect()
        container = self.config.object.bucket or "ai-platform-container"
        blob_client = self._client.get_blob_client(container=container, blob=key)
        blob_client.upload_blob(data, content_type=content_type)
        return key

    async def download(self, key: str) -> bytes:
        if not self._client:
            await self.connect()
        container = self.config.object.bucket or "ai-platform-container"
        blob_client = self._client.get_blob_client(container=container, blob=key)
        return blob_client.download_blob().readall()

    async def delete(self, key: str) -> bool:
        if not self._client:
            await self.connect()
        container = self.config.object.bucket or "ai-platform-container"
        blob_client = self._client.get_blob_client(container=container, blob=key)
        blob_client.delete_blob()
        return True

    async def list_objects(self, prefix: str) -> List[str]:
        if not self._client:
            await self.connect()
        container = self.config.object.bucket or "ai-platform-container"
        container_client = self._client.get_container_client(container)
        return [
            blob.name for blob in container_client.list_blobs(name_starts_with=prefix)
        ]

    def get_presigned_url(self, key: str, expires: int) -> str:
        if not self._client:
            import asyncio

            asyncio.run(self.connect())
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions

        container = self.config.object.bucket or "ai-platform-container"
        account_name = self._client.account_name
        account_key = self._client.credential.account_key
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=key,
            permission=BlobSasPermissions(read=True),
            expiry=expires,
        )
        return f"https://{account_name}.blob.core.windows.net/{container}/{key}?{sas_token}"
