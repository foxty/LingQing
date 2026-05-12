"""Health check router."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}
