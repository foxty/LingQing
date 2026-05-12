"""Base interfaces for storage abstraction.

Following the Strategy Pattern to allow pluggable file storage backends.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO


class FileStorage(ABC):
    """Abstract interface for file storage.

    This interface allows swapping between local filesystem, S3, OSS, GCS, etc.
    without changing the business logic in DocumentRepository.

    Example:
        # Use local storage
        storage = LocalFileStorage(base_path="/data/files")

        # Or use S3 storage
        storage = S3FileStorage(bucket="my-bucket", region="us-west-2")

        # API remains the same
        file_url = await storage.save(tenant_id, filename, file_content)
        content = await storage.read(file_url)
        await storage.delete(file_url)
    """

    @abstractmethod
    async def save(self, tenant_id: str, filename: str, file_content: BinaryIO) -> str:
        """Save a file and return its URL/path.

        Args:
            tenant_id: Tenant identifier
            filename: Original filename
            file_content: File content as binary stream

        Returns:
            File URL or path that can be used to retrieve the file

        Example:
            Returns:
            - Local: "/data/files/tenant_123/document.pdf"
            - S3: "s3://bucket/tenant_123/document.pdf"
            - OSS: "oss://bucket/tenant_123/document.pdf"
        """
        pass

    @abstractmethod
    async def read(self, file_url: str) -> bytes:
        """Read file content by URL/path.

        Args:
            file_url: File URL or path returned by save()

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    async def delete(self, file_url: str) -> bool:
        """Delete a file by URL/path.

        Args:
            file_url: File URL or path returned by save()

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def exists(self, file_url: str) -> bool:
        """Check if file exists.

        Args:
            file_url: File URL or path

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_size(self, file_url: str) -> int:
        """Get file size in bytes.

        Args:
            file_url: File URL or path

        Returns:
            File size in bytes
        """
        pass

    @abstractmethod
    async def generate_presigned_url(self, file_url: str, expiration: int = 3600) -> str | None:
        """Generate a presigned URL for temporary access (for cloud storage).

        Args:
            file_url: File URL or path
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL or None if not supported (e.g., local storage)
        """
        pass

    @abstractmethod
    async def get_local_path(self, file_url: str) -> str:
        """Get a local filesystem path for the file.

        For local storage, returns the file_url directly.
        For cloud storage, downloads to a temp file and returns its path.

        Args:
            file_url: File URL or path

        Returns:
            Local filesystem path to the file
        """
        pass
