"""MinIO bucket client for downloading artifacts."""

import os
from pathlib import Path
from typing import Optional

import structlog
from minio import Minio
from minio.error import S3Error

logger = structlog.get_logger()


class MinIOClient:
    """Client for MinIO bucket operations."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = False,
    ):
        """Initialize MinIO client.

        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000")
            access_key: Access key
            secret_key: Secret key
            bucket_name: Bucket name
            secure: Use HTTPS
        """
        self.bucket_name = bucket_name
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

        logger.info(
            "minio.client_initialized",
            endpoint=endpoint,
            bucket=bucket_name,
            secure=secure,
        )

    async def download(self, object_path: str, local_path: str) -> str:
        """Download object from MinIO bucket.

        Args:
            object_path: Path in bucket (e.g., "artifacts/helm/wrktalk-2.3.0.tgz")
            local_path: Local destination path (e.g., "/tmp/chart.tgz")

        Returns:
            Path to downloaded file

        Raises:
            Exception: If download fails
        """
        try:
            # Ensure parent directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            logger.info(
                "minio.downloading",
                bucket=self.bucket_name,
                object_path=object_path,
                local_path=local_path,
            )

            # Download from MinIO
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
                file_path=local_path,
            )

            file_size = os.path.getsize(local_path)
            logger.info(
                "minio.download_complete",
                object_path=object_path,
                local_path=local_path,
                size_bytes=file_size,
            )

            return local_path

        except S3Error as e:
            logger.error(
                "minio.download_error",
                object_path=object_path,
                error=str(e),
                error_code=e.code,
            )
            raise Exception(f"Failed to download {object_path}: {e}")

    def object_exists(self, object_path: str) -> bool:
        """Check if object exists in bucket.

        Args:
            object_path: Path in bucket

        Returns:
            True if object exists
        """
        try:
            self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
            )
            return True
        except S3Error:
            return False

    def get_object_info(self, object_path: str) -> Optional[dict]:
        """Get object metadata.

        Args:
            object_path: Path in bucket

        Returns:
            Object metadata dict or None if not found
        """
        try:
            stat = self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_path,
            )
            return {
                "size": stat.size,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
                "content_type": stat.content_type,
            }
        except S3Error as e:
            logger.warning("minio.stat_error", object_path=object_path, error=str(e))
            return None
