"""Shared constants for the API."""

# Supported document file types (must match RAG manager capabilities)
SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".html",
    ".htm",
    ".md",
    ".xlsx",
    ".xls",
}

# MIME type mappings for file validation
SUPPORTED_DOCUMENT_MIMES = {
    # PDF
    "application/pdf",
    # Word
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # PowerPoint
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Excel
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    # HTML
    "text/html",
    # Markdown
    "text/markdown",
    "text/x-markdown",
}
