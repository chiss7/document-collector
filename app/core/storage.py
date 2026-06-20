from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.core.supabase_config import client as supabase_client

logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, data: bytes, path: str, content_type: str = "application/pdf") -> str:
        """Upload file bytes and return the public URL."""
        pass


class SupabaseStorageProvider(StorageProvider):
    async def upload(self, data: bytes, path: str, content_type: str = "application/pdf") -> str:
        sb = supabase_client()
        bucket = settings.SUPABASE_BUCKET or "ia-docs-uce"
        logger.info("Supabase upload params: SUPABASE_URL=%s, bucket=%s, path=%s", settings.SUPABASE_URL, bucket, path)
        logger.info("PDF bytes read: %d", len(data))

        sb.storage.from_(bucket).upload(path, data, file_options={
            "content-type": content_type,
            "cache-control": "3600",
        })

        try:
            res = sb.storage.from_(bucket).get_public_url(path)
            url = None
            if isinstance(res, dict):
                url = res.get("publicUrl") or res.get("publicURL") or res.get("public_url")
            if not url:
                base = settings.SUPABASE_URL.rstrip('/')
                url = f"{base}/storage/v1/object/public/{bucket}/{path}"
            return url
        except Exception:
            base = settings.SUPABASE_URL.rstrip('/')
            return f"{base}/storage/v1/object/public/{bucket}/{path}"


class R2StorageProvider(StorageProvider):
    def __init__(self):
        import boto3
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=settings.R2_ENDPOINT,
        )
        self.bucket = settings.R2_BUCKET
        self.public_url = settings.R2_PUBLIC_URL.rstrip('/') if settings.R2_PUBLIC_URL else None

    async def upload(self, data: bytes, path: str, content_type: str = "application/pdf") -> str:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.client.put_object(
                Bucket=self.bucket,
                Key=path,
                Body=data,
                ContentType=content_type,
            ),
        )
        if self.public_url:
            return f"{self.public_url}/{path}"
        return f"{settings.R2_ENDPOINT.rstrip('/')}/{self.bucket}/{path}"


def get_storage_provider() -> StorageProvider:
    provider_name = settings.STORAGE_PROVIDER.lower()
    if provider_name == "r2":
        return R2StorageProvider()
    return SupabaseStorageProvider()
