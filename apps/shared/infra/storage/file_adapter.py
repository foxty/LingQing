"""File adapter for RAGManager integration.

Handles the gap between cloud storage (S3/OSS) and RAGManager which expects local file paths.
Downloads cloud files to temporary cache and manages cleanup.
"""

import hashlib
import tempfile
from pathlib import Path
from typing import List

from apps.shared.utils.logger import get_logger

from .base import FileStorage

logger = get_logger(__name__)


class FileAdapter:
    """Adapter between FileStorage and RAGManager.

    Problem:
    - FileStorage returns URLs (s3://bucket/file.pdf, oss://bucket/file.pdf)

    Solution:
    - Download cloud files to temporary cache
    - Return local paths to RAGManager
    - Manage cache and cleanup

    Example:
        adapter = FileAdapter(file_storage=S3FileStorage(...))

        # Get local paths (downloads if needed)
        local_paths = await adapter.get_local_paths([
            "s3://bucket/doc1.pdf",
            "s3://bucket/doc2.pdf"
        ])


        # Cleanup
        await adapter.cleanup(local_paths)
    """

    def __init__(
        self,
        file_storage: FileStorage,
        cache_dir: str | None = None,
        auto_cleanup: bool = True,
    ):
        """Initialize file adapter.

        Args:
            file_storage: File storage instance
            cache_dir: Cache directory for downloaded files (default: temp dir)
            auto_cleanup: Whether to auto cleanup temp files on cleanup()
        """
        self.file_storage = file_storage
        self.auto_cleanup = auto_cleanup

        # Cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Use system temp directory
            self.cache_dir = Path(tempfile.gettempdir()) / "_file_cache"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Track downloaded files for cleanup
        self._temp_files: List[str] = []

        logger.debug(f"FileAdapter initialized with cache_dir: {self.cache_dir}")

    def _is_local_path(self, file_url: str) -> bool:
        """Check if file_url is a local file path (not cloud URL).

        Args:
            file_url: File URL or path

        Returns:
            True if local path, False if cloud URL
        """
        # Check for cloud storage URL schemes
        if file_url.startswith(("s3://", "oss://", "gs://", "http://", "https://")):
            return False

        # Check if it's an existing local file
        return Path(file_url).exists()

    def _get_cache_path(self, file_url: str) -> Path:
        """Generate cache file path based on URL.

        Args:
            file_url: File URL

        Returns:
            Cache file path
        """
        # Use hash of URL as cache key to avoid collisions
        url_hash = hashlib.md5(file_url.encode()).hexdigest()

        # Extract filename
        filename = Path(file_url).name
        if not filename or filename == file_url:
            # For URLs without clear filename, use hash
            filename = url_hash

        # Cache path: cache_dir / hash_filename
        cache_filename = f"{url_hash}_{filename}"
        return self.cache_dir / cache_filename

    async def get_local_path(self, file_url: str) -> str:
        """Get local file path, downloading from cloud if necessary.

        Args:
            file_url: File URL (local path or cloud URL)

        Returns:
            Local file path
        """
        # If already a local path, return as-is
        if self._is_local_path(file_url):
            logger.debug(f"File is local: {file_url}")
            return file_url

        # Check cache first
        cache_path = self._get_cache_path(file_url)
        if cache_path.exists():
            logger.debug(f"Using cached file: {cache_path}")
            return str(cache_path)

        # Download from cloud storage
        logger.info(f"Downloading file from cloud: {file_url}")
        try:
            file_content = await self.file_storage.read(file_url)

            # Write to cache
            with cache_path.open("wb") as f:
                f.write(file_content)

            # Track for cleanup
            self._temp_files.append(str(cache_path))

            logger.info(f"File downloaded to cache: {cache_path}")
            return str(cache_path)

        except Exception as e:
            logger.error(f"Error downloading file {file_url}: {e}")
            raise

    async def get_local_paths(self, file_urls: List[str]) -> List[str]:
        """Get local file paths for multiple files.

        Args:
            file_urls: List of file URLs

        Returns:
            List of local file paths
        """
        local_paths = []

        for file_url in file_urls:
            try:
                local_path = await self.get_local_path(file_url)
                local_paths.append(local_path)
            except Exception as e:
                logger.error(f"Failed to get local path for {file_url}: {e}")
                # Skip failed files
                continue

        return local_paths

    async def cleanup(self, file_paths: List[str | None] = None) -> None:
        """Cleanup downloaded temporary files.

        Args:
            file_paths: Specific paths to cleanup. If None, cleanup all tracked files
        """
        if not self.auto_cleanup:
            logger.debug("Auto cleanup is disabled")
            return

        paths_to_clean = file_paths if file_paths else self._temp_files

        for file_path in paths_to_clean:
            try:
                path = Path(file_path)
                if path.exists() and path.parent == self.cache_dir:
                    path.unlink()
                    logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Error cleaning up {file_path}: {e}")

        # Clear tracked files if cleaning all
        if file_paths is None:
            self._temp_files.clear()

    async def cleanup_cache(self, max_age_hours: int = 24) -> None:
        """Cleanup old cached files.

        Args:
            max_age_hours: Remove files older than this many hours
        """
        import time

        logger.info(f"Cleaning up cache older than {max_age_hours} hours")

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        removed_count = 0

        for cache_file in self.cache_dir.iterdir():
            if not cache_file.is_file():
                continue

            file_age = current_time - cache_file.stat().st_mtime

            if file_age > max_age_seconds:
                try:
                    cache_file.unlink()
                    removed_count += 1
                    logger.debug(f"Removed old cache file: {cache_file}")
                except Exception as e:
                    logger.warning(f"Error removing {cache_file}: {e}")

        logger.info(f"Cleaned up {removed_count} old cache files")

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        cache_files = list(self.cache_dir.glob("*"))
        total_size = sum(f.stat().st_size for f in cache_files if f.is_file())

        return {
            "cache_dir": str(self.cache_dir),
            "file_count": len(cache_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }


# Convenience function
async def prepare_files_for_rag(file_storage: FileStorage, file_urls: List[str]) -> tuple[List[str], FileAdapter]:
    """Prepare cloud/local files for RAGManager processing.

    This is a convenience function that handles the common pattern:
    1. Create adapter
    2. Get local paths
    3. Return paths and adapter (caller should cleanup)

    Args:
        file_storage: File storage instance
        file_urls: List of file URLs (local or cloud)

    Returns:
        Tuple of (local_paths, adapter)
        Caller should call adapter.cleanup() after RAGManager processing

    Example:
        # Prepare files
        local_paths, adapter = await prepare_files_for_rag(
            file_storage,
            ["s3://bucket/doc.pdf"]
        )

        # Cleanup
        await adapter.cleanup()
    """
    adapter = FileAdapter(file_storage)
    local_paths = await adapter.get_local_paths(file_urls)
    return local_paths, adapter
