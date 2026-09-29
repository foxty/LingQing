"""Backward-compatible re-export. Prefer apps.shared.document.parse_pipeline."""

from apps.shared.document.parse_pipeline import DocumentParsePipeline

DocumentProcessingService = DocumentParsePipeline

__all__ = ["DocumentParsePipeline", "DocumentProcessingService"]
