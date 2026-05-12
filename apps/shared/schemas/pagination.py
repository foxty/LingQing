"""Shared pagination schemas and utilities."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response for any resource type.

    Can be used with any item type T, e.g., PaginatedResponse[DocumentInfo].
    """

    items: list[T] = Field(..., description="List of items for the current page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    @staticmethod
    def calculate_offset(page: int, page_size: int) -> int:
        """Calculate database offset from page number.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Database offset (0-indexed)
        """
        return (page - 1) * page_size

    @staticmethod
    def calculate_total_pages(total: int, page_size: int) -> int:
        """Calculate total pages from item count.

        Args:
            total: Total number of items
            page_size: Items per page

        Returns:
            Total number of pages (ceiling division)
        """
        return (total + page_size - 1) // page_size
