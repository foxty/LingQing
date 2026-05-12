"""Storage abstraction layer for file storage.

This module provides a pluggable storage interface that supports:
- Local file system
- S3-compatible cloud storage (AWS S3, Aliyun OSS, Tencent COS, MinIO, etc.)
- File adapter for RAGManager integration
"""

from .base import FileStorage
from .file_adapter import FileAdapter, prepare_files_for_rag
from .file_storage import LocalFileStorage, S3FileStorage

__all__ = [
    "FileStorage",
    "LocalFileStorage",
    "S3FileStorage",
    "FileAdapter",
    "prepare_files_for_rag",
]
