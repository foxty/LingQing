"""File storage implementations.

Provides concrete implementations of FileStorage interface for:
- Local filesystem
- AWS S3
- Aliyun OSS
- Google Cloud Storage (can be added)
"""

import shutil
from pathlib import Path
from typing import BinaryIO

from apps.config import get_tenant_documents_path
from apps.shared.utils.logger import get_logger

from .base import FileStorage

logger = get_logger(__name__)


class LocalFileStorage(FileStorage):
    """Local filesystem storage implementation.

    Uses tenant-centric storage structure where each tenant's documents
    are stored in: {DATA_ROOT_PATH}/tenants/tenant_{id}/documents/

    Best for:
    - Development and testing
    - Single-server deployments
    - Small to medium file volumes

    Example:
        storage = LocalFileStorage()
        file_url = await storage.save("123", "doc.pdf", file_content)
        # Returns: "/data/tenants/tenant_123/documents/doc.pdf"
    """

    def __init__(self):
        """Initialize local file storage.

        Note: No base_path needed - uses tenant-centric paths from config.
        """
        logger.debug("LocalFileStorage initialized with tenant-centric paths")

    def _get_tenant_path(self, tenant_id: str) -> Path:
        """Get tenant documents directory path.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Path to tenant's documents directory
        """
        return Path(get_tenant_documents_path(tenant_id))

    async def save(self, tenant_id: str, filename: str, file_content: BinaryIO) -> str:
        """Save file to local filesystem."""
        tenant_path = self._get_tenant_path(tenant_id)
        file_path = tenant_path / filename

        logger.info(f"Saving file to local storage: {file_path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as f:
            shutil.copyfileobj(file_content, f)

        return filename.replace("\\", "/")

    async def read(self, file_url: str) -> bytes:
        """Read file from local filesystem."""
        file_path = Path(file_url)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_url}")

        with file_path.open("rb") as f:
            return f.read()

    async def delete(self, file_url: str) -> bool:
        """Delete file from local filesystem."""
        file_path = Path(file_url)

        if not file_path.exists():
            logger.warning(f"File not found for deletion: {file_url}")
            return False

        file_path.unlink()
        logger.info(f"File deleted: {file_url}")
        return True

    async def exists(self, file_url: str) -> bool:
        """Check if file exists."""
        return Path(file_url).exists()

    async def get_size(self, file_url: str) -> int:
        """Get file size."""
        file_path = Path(file_url)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_url}")
        return file_path.stat().st_size

    async def generate_presigned_url(self, file_url: str, expiration: int = 3600) -> str | None:
        """Local storage doesn't support presigned URLs."""
        return None

    async def get_local_path(self, file_url: str) -> str:
        """Get local file path. For local storage, the file_url is already a local path."""
        file_path = Path(file_url)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_url}")
        return file_url


class S3FileStorage(FileStorage):
    """S3-compatible storage implementation.

    Supports:
    - AWS S3 (native)
    - Aliyun OSS (S3-compatible mode)
    - Tencent COS (S3-compatible mode)
    - MinIO (fully S3-compatible)
    - Any S3-compatible storage

    Best for:
    - Production deployments
    - Multi-cloud compatibility
    - Unified storage interface

    Requires:
        pip install boto3

    Examples:
        # AWS S3 (default)
        storage = S3FileStorage(
            bucket="my-bucket",
            region="us-west-2"
        )

        # Aliyun OSS (S3-compatible mode)
        storage = S3FileStorage(
            bucket="my-bucket",
            region="oss-cn-hangzhou",
            endpoint_url="https://oss-cn-hangzhou.aliyuncs.com",
            access_key_id="your_access_key_id",
            secret_access_key="your_access_key_secret"
        )

        # Tencent COS (S3-compatible mode)
        storage = S3FileStorage(
            bucket="my-bucket-1234567890",
            region="ap-guangzhou",
            endpoint_url="https://cos.ap-guangzhou.myqcloud.com",
            access_key_id="your_secret_id",
            secret_access_key="your_secret_key"
        )

        # MinIO (private cloud)
        storage = S3FileStorage(
            bucket="my-bucket",
            region="us-east-1",
            endpoint_url="http://minio.example.com:9000",
            access_key_id="minioadmin",
            secret_access_key="minioadmin"
        )
    """

    def __init__(
        self,
        bucket: str,
        region: str = "us-west-2",
        prefix: str = "",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        use_ssl: bool = True,
    ):
        """Initialize S3-compatible storage.

        Args:
            bucket: Bucket name
            region: Region (AWS region or cloud provider region)
            prefix: Optional prefix for all objects (e.g., "documents")
            endpoint_url: S3 endpoint URL (for non-AWS S3-compatible services)
                         AWS S3: None (uses default)
                         Aliyun OSS: https://oss-cn-hangzhou.aliyuncs.com
                         Tencent COS: https://cos.ap-guangzhou.myqcloud.com
                         MinIO: http://minio.example.com:9000
            access_key_id: Access key ID (cloud-agnostic, or use IAM role for AWS)
            secret_access_key: Secret access key (cloud-agnostic, or use IAM role for AWS)
            use_ssl: Use HTTPS (default: True)
        """
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")

        self.bucket = bucket
        self.region = region
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.use_ssl = use_ssl

        # Initialize S3 client
        client_kwargs = {
            "region_name": region,
            "use_ssl": use_ssl,
        }

        # Add endpoint URL for S3-compatible services
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        # Add credentials if provided
        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key

        self.s3_client = boto3.client("s3", **client_kwargs)

        provider = "AWS S3" if not endpoint_url else f"S3-compatible ({endpoint_url})"
        logger.info(f"S3FileStorage initialized: provider={provider}, bucket={bucket}, region={region}")

    def _get_s3_key(self, tenant_id: str, filename: str) -> str:
        """Generate S3 object key."""
        parts = [self.prefix, tenant_id, filename] if self.prefix else [tenant_id, filename]
        return "/".join(parts)

    def _get_file_url(self, s3_key: str) -> str:
        """Generate S3 URL from key."""
        return f"s3://{self.bucket}/{s3_key}"

    def _parse_s3_url(self, file_url: str) -> str:
        """Extract S3 key from URL."""
        if not file_url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL: {file_url}")
        # Remove "s3://bucket/" prefix
        return file_url.replace(f"s3://{self.bucket}/", "")

    async def save(self, tenant_id: str, filename: str, file_content: BinaryIO) -> str:
        """Upload file to S3."""
        s3_key = self._get_s3_key(tenant_id, filename)

        logger.info(f"Uploading file to S3: bucket={self.bucket}, key={s3_key}")

        self.s3_client.upload_fileobj(
            file_content,
            self.bucket,
            s3_key,
            ExtraArgs={"ServerSideEncryption": "AES256"},  # Enable encryption
        )

        file_url = self._get_file_url(s3_key)
        logger.info(f"File uploaded successfully: {file_url}")
        return file_url

    async def read(self, file_url: str) -> bytes:
        """Download file from S3."""
        s3_key = self._parse_s3_url(file_url)

        logger.debug(f"Reading file from S3: {s3_key}")

        response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
        return response["Body"].read()

    async def delete(self, file_url: str) -> bool:
        """Delete file from S3."""
        s3_key = self._parse_s3_url(file_url)

        logger.info(f"Deleting file from S3: {s3_key}")

        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting file from S3: {e}")
            return False

    async def exists(self, file_url: str) -> bool:
        """Check if file exists in S3."""
        s3_key = self._parse_s3_url(file_url)

        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception:
            return False

    async def get_size(self, file_url: str) -> int:
        """Get file size from S3."""
        s3_key = self._parse_s3_url(file_url)

        response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
        return response["ContentLength"]

    async def generate_presigned_url(self, file_url: str, expiration: int = 3600) -> str | None:
        """Generate presigned URL for temporary access."""
        s3_key = self._parse_s3_url(file_url)

        logger.debug(f"Generating presigned URL for {s3_key}, expiration={expiration}s")

        try:
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return presigned_url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    async def get_local_path(self, file_url: str) -> str:
        """Download S3 file to temp location and return local path."""
        import tempfile

        s3_key = self._parse_s3_url(file_url)

        # Create temp file with same extension
        suffix = Path(s3_key).suffix
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = temp_file.name
        temp_file.close()

        logger.debug(f"Downloading S3 file to temp: {s3_key} -> {temp_path}")

        self.s3_client.download_file(Bucket=self.bucket, Key=s3_key, Filename=temp_path)

        return temp_path
