"""LingQing Platform SDK - Unified API clients and components.

Structure:
- js-api/: TypeScript/JavaScript SDK for browser frontend
- py-api/: Python SDK for scheduled jobs and agent skills
- frontend-components/: Web components for UI

Usage:
    # Python SDK
    from apps.shared.sdk.py_api import LiveAppClient

    async with LiveAppClient.from_environment() as client:
        result = await client.query("SELECT 1")
"""

__version__ = "1.0.0"
