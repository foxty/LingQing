"""Test script for Python SDK - demonstrates usage patterns."""

import asyncio
import json
import os
import sys

# Add parent directory to path so we can import lingqing_sdk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up mock environment for testing
os.environ["TASK_RUNTIME_CONTEXT"] = json.dumps(
    {
        "tenant_id": 1,
        "app_id": 42,
        "environment": "dev",
        "access_token": "test-token-placeholder",
        "api_base_url": "http://localhost:8000/api",
    }
)

from .client import APIError, LiveAppClient


async def test_sdk_initialization():
    """Test SDK initialization from environment."""
    print("Testing SDK initialization...")

    try:
        client = LiveAppClient.from_environment()
        print("✓ Client created successfully")
        print(f"  - tenant_id: {client.tenant_id}")
        print(f"  - app_id: {client.app_id}")
        print(f"  - environment: {client.environment}")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        return False


async def test_api_connector_call():
    """Test API connector call (will fail without real server, but tests interface)."""
    print("\nTesting API connector call interface...")

    try:
        async with LiveAppClient.from_environment() as client:
            # This will fail without a real server, but tests the interface
            try:
                result = await client.call_api_connector(
                    "test-operation-uid", parameters={"query": {"city": "Shanghai"}}
                )
                print(f"✓ API call succeeded: status={result.status_code}")
            except APIError as e:
                # Expected to fail without real server
                print(f"✓ API call failed as expected (no server): {e.status_code}")
            except Exception as e:
                print(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


async def test_validation_errors():
    """Test validation errors."""
    print("\nTesting validation errors...")

    # Test missing app_id
    try:
        client = LiveAppClient(tenant_id=1, app_id=None)
        await client.query("SELECT 1")
        print("✗ Should have raised ValueError for missing app_id")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"✗ Wrong exception type: {type(e).__name__}: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("LingQing Python SDK - Test Suite")
    print("=" * 60)

    results = []

    results.append(await test_sdk_initialization())
    results.append(await test_api_connector_call())
    results.append(await test_validation_errors())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
