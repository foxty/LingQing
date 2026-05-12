"""Pagination utilities for common pagination calculations."""


class PaginationRequest:
    """Helper class to calculate and validate pagination parameters.

    Ensures page and page_size are within valid bounds.
    """

    def __init__(self, page: int = 1, page_size: int = 10, max_page_size: int = 100, total: int = 0):
        """Initialize pagination parameters with validation.

        Args:
            page: Page number (1-indexed). Defaults to 1.
            page_size: Items per page. Defaults to 10.
            max_page_size: Maximum allowed page size. Defaults to 100.
        """
        self.page = max(1, page)  # Ensure page >= 1
        self.page_size = min(max(1, page_size), max_page_size)  # Clamp to valid range
        self.total = max(0, total)
        self.offset = (self.page - 1) * self.page_size

    @property
    def end(self) -> int:
        """End offset (exclusive) for slicing/query windows."""
        return self.offset + self.page_size

    @property
    def total_pages(self) -> int:
        """Total pages derived from total and page size."""
        return self.calculate_total_pages(self.total)

    @staticmethod
    def resolve_window(k: int, page: int, page_size: int | None, max_page_size: int = 100) -> tuple[int, int]:
        """Resolve [start, end) for both legacy and explicit pagination modes.

        Legacy mode: when page_size is None, use `k` directly.
        Pagination mode: validate/clamp via PaginationRequest and return page window.
        """
        if page_size is None:
            return 0, max(0, k)

        params = PaginationRequest(page=page, page_size=page_size, max_page_size=max_page_size)
        return params.offset, params.end

    @classmethod
    def with_total(
        cls,
        *,
        page: int,
        page_size: int,
        total: int,
        max_page_size: int = 100,
    ) -> "PaginationRequest":
        """Build pagination and clamp page within total page bounds.

        This keeps offset aligned with available rows when clients request pages
        larger than total pages.
        """
        normalized_total = max(0, total)
        params = cls(page=page, page_size=page_size, max_page_size=max_page_size, total=normalized_total)
        total_pages = params.calculate_total_pages(normalized_total)
        if total_pages > 0 and params.page > total_pages:
            params.page = total_pages
            params.offset = (params.page - 1) * params.page_size
        return params

    def calculate_total_pages(self, total: int) -> int:
        """Calculate total pages from total item count.

        Args:
            total: Total number of items

        Returns:
            Total number of pages (ceiling division)
        """
        return (total + self.page_size - 1) // self.page_size


# Backward-compatible alias for existing imports.
PaginationParams = PaginationRequest
