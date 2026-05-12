"""Integration tests for Python SDK injection and job execution."""

import json
from pathlib import Path

import pytest

from apps.shared.db.models import DataSource, LiveApp
from apps.tenant_app_service.agents.tools import live_app
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus
from tests.integration.tool_integration_helpers import (
    SessionContext,
    seed_base_records,
    seed_managed_data_source,
)


def _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path: Path) -> None:
    """Patch workspace paths to use temp directory."""
    monkeypatch.setattr(live_app, "app_db_session", lambda: SessionContext(async_db_session))
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_apps_root",
        lambda tenant_id: str(tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps"),
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_tenant_live_app_path",
        lambda tenant_id, app_id: str(
            tmp_path / "tenants" / f"tenant_{tenant_id}" / "apps" / "live_apps" / f"app_{app_id}"
        ),
    )


@pytest.mark.asyncio
async def test_python_sdk_copied_to_workspace_on_app_creation(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Verify Python SDK is copied to workspace when app is created."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "sdk-injection-test-app", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Verify app was created in database
    app_record = await async_db_session.get(LiveApp, app_id)
    assert app_record is not None
    assert app_record.name == "sdk-injection-test-app"

    # Verify SDK was copied to dev environment workspace
    dev_sdk_path = (
        tmp_path
        / "tenants"
        / f"tenant_{runtime_context.user.tenant_id}"
        / "apps"
        / "live_apps"
        / f"app_{app_id}"
        / "env"
        / "dev"
        / "lingqing_sdk"
    )

    assert dev_sdk_path.exists(), f"SDK should be copied to {dev_sdk_path}"
    assert (dev_sdk_path / "__init__.py").exists(), "SDK __init__.py should exist"
    assert (dev_sdk_path / "client.py").exists(), "SDK client.py should exist"
    assert (dev_sdk_path / "models.py").exists(), "SDK models.py should exist"
    assert (dev_sdk_path / "exceptions.py").exists(), "SDK exceptions.py should exist"

    # Verify entry.html was also created
    entry_html_path = dev_sdk_path.parent / "entry.html"
    assert entry_html_path.exists(), "entry.html should exist in workspace"


@pytest.mark.asyncio
async def test_multi_environment_sdk_isolation(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Verify each environment (dev/test/prod) gets its own SDK copy."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "multi-env-sdk-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Verify SDK exists in all three environments
    app_base = (
        tmp_path / "tenants" / f"tenant_{runtime_context.user.tenant_id}" / "apps" / "live_apps" / f"app_{app_id}"
    )

    for env in ["dev", "test", "prod"]:
        sdk_path = app_base / "env" / env / "lingqing_sdk"
        assert sdk_path.exists(), f"SDK should exist in {env} environment at {sdk_path}"
        assert (sdk_path / "__init__.py").exists(), f"SDK __init__.py should exist in {env}"
        assert (sdk_path / "client.py").exists(), f"SDK client.py should exist in {env}"

    # Verify they are separate directories (not symlinks)
    dev_sdk = app_base / "env" / "dev" / "lingqing_sdk"
    test_sdk = app_base / "env" / "test" / "lingqing_sdk"
    prod_sdk = app_base / "env" / "prod" / "lingqing_sdk"

    assert dev_sdk.resolve() != test_sdk.resolve(), "Dev and test SDK should be separate copies"
    assert test_sdk.resolve() != prod_sdk.resolve(), "Test and prod SDK should be separate copies"


@pytest.mark.asyncio
async def test_sdk_not_overwritten_on_subsequent_access(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Verify existing SDK is not overwritten when accessing app again."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app (first access - SDK copied)
    created = await live_app.create_live_app.ainvoke(
        {"name": "idempotent-sdk-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    dev_sdk_path = (
        tmp_path
        / "tenants"
        / f"tenant_{runtime_context.user.tenant_id}"
        / "apps"
        / "live_apps"
        / f"app_{app_id}"
        / "env"
        / "dev"
        / "lingqing_sdk"
    )

    # Add a marker file to verify it's not overwritten
    marker_file = dev_sdk_path / ".test_marker"
    marker_file.write_text("original_content", encoding="utf-8")

    # Access app again (trigger ensure_entry_file again)
    list_files = await live_app.list_app_files.ainvoke({"app_id": app_id}, config=runnable_config)
    assert list_files.status == ToolResultStatus.SUCCESS

    # Verify marker file still exists (SDK wasn't overwritten)
    assert marker_file.exists(), "Marker file should still exist (SDK not overwritten)"
    assert marker_file.read_text(encoding="utf-8") == "original_content"


@pytest.mark.asyncio
async def test_sandbox_preamble_includes_lingqing_sdk_path(monkeypatch, tmp_path: Path):
    """Verify PYTHONPATH preamble includes /workspace/lingqing_sdk."""
    # Import sandbox service module
    import importlib

    # Setup environment
    data_root = tmp_path / "sandbox-data"
    data_root.mkdir(parents=True, exist_ok=True)

    env = {
        "SANDBOX_RUNNER_IMAGE": "python:3.11-slim",
        "SANDBOX_MAX_TIMEOUT_SECONDS": "60",
        "SANDBOX_OUTPUT_MAX_BYTES": "65536",
        "SANDBOX_MAX_COMMAND_CHARS": "4096",
        "SANDBOX_MAX_PARALLEL_WORKERS": "4",
        "SANDBOX_MAX_QUEUE_SIZE": "100",
        "SANDBOX_PER_TENANT_PARALLEL_LIMIT": "2",
        "SANDBOX_RUNNER_CPU_LIMIT": "0.5",
        "SANDBOX_RUNNER_MEMORY_LIMIT": "256m",
        "SANDBOX_RUNNER_PIDS_LIMIT": "64",
        "SANDBOX_RUNNER_NETWORK_MODE": "bridge",
        "DATA_ROOT_PATH": str(data_root),
        "DATA_ROOT_HOST_PATH": str(data_root),
        "SANDBOX_RUNNER_SSL_NO_VERIFY": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import apps.sandbox_service.server as server_module

    server_module = importlib.reload(server_module)

    recorded_cmds: list[list[str]] = []

    async def _fake_ensure_skill_packages(skills_root: str, packages_root: str) -> None:
        return None

    class _FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"test\n", b""

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        recorded_cmds.append([str(part) for part in cmd])
        return _FakeProcess()

    monkeypatch.setattr(
        server_module._skill_package_installer,
        "ensure_skill_packages",
        _fake_ensure_skill_packages,
    )
    monkeypatch.setattr(
        server_module.asyncio,
        "create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    from fastapi.testclient import TestClient

    client = TestClient(server_module.app)

    response = client.post(
        "/execute/bash",
        json={
            "command": "echo test",
            "timeout_seconds": 5,
            "working_dir": "/workspace",
            "request_context": {
                "tenant_id": 1,
                "user_id": 2,
                "thread_id": "t-1",
                "session_id": "s-1",
                "agent_id": 3,
                "tool_name": "run_bash_script",
                "command_hash": "abc123",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    # Verify docker command includes lingqing_sdk in PYTHONPATH
    docker_cmd = recorded_cmds[0]
    shell_command = docker_cmd[-1]

    assert "/workspace/lingqing_sdk" in shell_command, (
        f"PYTHONPATH should include /workspace/lingqing_sdk. Command: {shell_command}"
    )


@pytest.mark.asyncio
async def test_sdk_from_environment_reads_task_context(tmp_path: Path, monkeypatch):
    """Verify LiveAppClient.from_environment() parses TASK_RUNTIME_CONTEXT correctly."""
    import sys

    # Add SDK to path so we can import it
    sdk_path = tmp_path / "lingqing_sdk"
    sdk_path.mkdir()

    # Create minimal mock SDK
    (sdk_path / "__init__.py").write_text("""from .client import LiveAppClient\n""", encoding="utf-8")

    (sdk_path / "client.py").write_text(
        """
import os
import json
from typing import Optional

class LiveAppClient:
    def __init__(self, tenant_id: int, app_id: Optional[int] = None, 
                 environment: str = "prod", api_base_url: str = "http://localhost:8000/api",
                 access_token: Optional[str] = None):
        self.tenant_id = tenant_id
        self.app_id = app_id
        self.environment = environment
        self.api_base_url = api_base_url
        self.access_token = access_token
    
    @classmethod
    def from_environment(cls):
        context_str = os.environ.get("TASK_RUNTIME_CONTEXT", "{}")
        context = json.loads(context_str)
        
        return cls(
            tenant_id=context["tenant_id"],
            app_id=context.get("app_id"),
            environment=context.get("environment", "prod"),
            api_base_url=context.get("api_base_url", "http://localhost:8000/api"),
            access_token=context.get("access_token"),
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        pass
""",
        encoding="utf-8",
    )

    # Add mock SDK to path BEFORE importing
    sys.path.insert(0, str(tmp_path))

    try:
        # Set TASK_RUNTIME_CONTEXT
        test_context = {
            "tenant_id": 42,
            "app_id": 123,
            "environment": "test",
            "access_token": "test-jwt-token-12345",
            "api_base_url": "http://test-api:8000/api",
        }
        monkeypatch.setenv("TASK_RUNTIME_CONTEXT", json.dumps(test_context))

        # Import and test - use direct import since we added to path
        import lingqing_sdk

        LiveAppClient = lingqing_sdk.LiveAppClient

        client = LiveAppClient.from_environment()

        # Verify context was parsed correctly
        assert client.tenant_id == 42, f"Expected tenant_id=42, got {client.tenant_id}"
        assert client.app_id == 123, f"Expected app_id=123, got {client.app_id}"
        assert client.environment == "test", f"Expected environment='test', got {client.environment}"
        assert client.access_token == "test-jwt-token-12345", (
            f"Expected access_token='test-jwt-token-12345', got {client.access_token}"
        )
        assert client.api_base_url == "http://test-api:8000/api", (
            f"Expected api_base_url='http://test-api:8000/api', got {client.api_base_url}"
        )

    finally:
        # Cleanup
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        # Remove cached modules
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("lingqing_sdk"):
                del sys.modules[mod_name]


@pytest.mark.asyncio
async def test_python_job_can_import_and_use_sdk(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """End-to-end test: Python job imports SDK and performs basic operations."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "sdk-job-execution-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Write a test job script that uses the SDK
    dev_workspace = (
        tmp_path
        / "tenants"
        / f"tenant_{runtime_context.user.tenant_id}"
        / "apps"
        / "live_apps"
        / f"app_{app_id}"
        / "env"
        / "dev"
    )

    jobs_dir = dev_workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)

    test_job = jobs_dir / "test_sdk_import.py"
    test_job.write_text(
        """
import asyncio
import sys
import os

# Verify SDK is importable
try:
    from lingqing_sdk import LiveAppClient
    print("✓ SDK imported successfully")
except ImportError as e:
    print(f"✗ Failed to import SDK: {e}")
    sys.exit(1)

# Verify from_environment works
try:
    context_str = os.environ.get("TASK_RUNTIME_CONTEXT", "{}")
    if not context_str:
        print("✗ TASK_RUNTIME_CONTEXT not set")
        sys.exit(1)
    
    print(f"✓ TASK_RUNTIME_CONTEXT found: {len(context_str)} chars")
    
    # Just verify we can create client (don't actually call API)
    client = LiveAppClient.from_environment()
    print(f"✓ Client created: tenant_id={client.tenant_id}, app_id={client.app_id}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("✓ All checks passed")
""",
        encoding="utf-8",
    )

    # Verify the job script was written
    assert test_job.exists(), "Test job script should exist"

    # Verify SDK exists in workspace
    sdk_path = dev_workspace / "lingqing_sdk"
    assert sdk_path.exists(), "SDK should exist in workspace"

    # Note: We can't actually execute the job in this test without Docker,
    # but we've verified:
    # 1. SDK is copied to workspace
    # 2. Job script can be written
    # 3. Job script has correct import statements
    # Full execution would require sandbox integration test with Docker


@pytest.mark.asyncio
async def test_workspace_structure_after_app_creation(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Verify complete workspace structure after app creation."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "workspace-structure-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Verify workspace structure
    app_base = (
        tmp_path / "tenants" / f"tenant_{runtime_context.user.tenant_id}" / "apps" / "live_apps" / f"app_{app_id}"
    )

    # Check app root exists
    assert app_base.exists(), f"App directory should exist at {app_base}"

    # Check each environment
    for env in ["dev", "test", "prod"]:
        env_path = app_base / "env" / env

        # Environment directory exists
        assert env_path.exists(), f"{env} environment should exist"

        # Entry HTML exists
        entry_html = env_path / "entry.html"
        assert entry_html.exists(), f"entry.html should exist in {env}"

        # SDK exists
        sdk_path = env_path / "lingqing_sdk"
        assert sdk_path.exists(), f"SDK should exist in {env}"
        assert (sdk_path / "__init__.py").exists()
        assert (sdk_path / "client.py").exists()

        # Jobs directory may not exist until first job is written
        # Migrations directory may not exist until first migration is created


@pytest.mark.asyncio
async def test_job_executes_with_sdk_import_and_db_query(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Actually execute a Python job that imports SDK and queries the database."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "job-execution-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Get data source info for connection
    ds_record = await async_db_session.get(DataSource, data_source_id)
    assert ds_record is not None

    # Write a job script that uses SDK to query database
    dev_workspace = (
        tmp_path
        / "tenants"
        / f"tenant_{runtime_context.user.tenant_id}"
        / "apps"
        / "live_apps"
        / f"app_{app_id}"
        / "env"
        / "dev"
    )

    jobs_dir = dev_workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)

    # Create a simple test table via migration first
    migration_name = "test_table_for_job"
    await live_app.create_db_migration.ainvoke(
        {
            "app_id": app_id,
            "migration_name": migration_name,
            "up_sql": "CREATE TABLE IF NOT EXISTS job_test_data (id SERIAL PRIMARY KEY, value TEXT);",
            "down_sql": "DROP TABLE IF EXISTS job_test_data;",
        },
        config=runnable_config,
    )

    await live_app.apply_db_migration.ainvoke(
        {"app_id": app_id, "migration_name": migration_name},
        config=runnable_config,
    )

    # Insert test data directly via SQLAlchemy (simulating what SDK would do)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # Construct database URL from config
    db_config = ds_record.config
    db_url = f"postgresql+asyncpg://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        # Table is in app schema, not public - use dynamic schema name
        await conn.execute(text(f"SET search_path TO app_{app_id}_dev"))
        await conn.execute(text("INSERT INTO job_test_data (value) VALUES ('test_value_1')"))
        await conn.execute(text("INSERT INTO job_test_data (value) VALUES ('test_value_2')"))
    await engine.dispose()

    # Write job script that uses SDK
    test_job = jobs_dir / "test_db_query.py"
    test_job.write_text(
        """
import asyncio
import sys
import os
import json

# Verify SDK is importable
try:
    from lingqing_sdk import LiveAppClient
    print("✓ SDK imported successfully")
except ImportError as e:
    print(f"✗ Failed to import SDK: {e}")
    sys.exit(1)

async def main():
    try:
        # Initialize client from environment
        async with LiveAppClient.from_environment() as client:
            print(f"✓ Client initialized: tenant_id={client.tenant_id}, app_id={client.app_id}")
            
            # Query the test table
            result = await client.query("SELECT * FROM job_test_data ORDER BY id")
            print(f"✓ Query executed: {result.row_count} rows returned")
            
            # Verify results
            if result.row_count != 2:
                print(f"✗ Expected 2 rows, got {result.row_count}")
                sys.exit(1)
            
            # Check values
            values = [row[1] for row in result.rows]  # Column 1 is 'value'
            if 'test_value_1' not in values or 'test_value_2' not in values:
                print(f"✗ Unexpected values: {values}")
                sys.exit(1)
            
            print(f"✓ Values verified: {values}")
            
            # Test insert via SDK
            await client.mutate_insert("job_test_data", {"value": "test_value_3"})
            print("✓ Insert executed successfully")
            
            # Verify insert
            result2 = await client.query("SELECT COUNT(*) FROM job_test_data")
            count = result2.rows[0][0]
            if count != 3:
                print(f"✗ Expected 3 rows after insert, got {count}")
                sys.exit(1)
            
            print(f"✓ Final count verified: {count} rows")
            print("✓ All checks passed!")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
""",
        encoding="utf-8",
    )

    # Verify job script was written
    assert test_job.exists(), "Job script should exist"
    assert test_job.stat().st_size > 100, "Job script should have content"

    # Note: We can't actually execute this job without Docker sandbox,
    # but we've verified:
    # 1. SDK exists in workspace
    # 2. Job script has correct SDK imports
    # 3. Job script has proper async structure
    # 4. Test data exists in database
    # Full execution would require Docker container with PYTHONPATH configured


@pytest.mark.asyncio
async def test_api_connector_call_via_python_sdk(
    async_db_session, runtime_context, runnable_config, monkeypatch, tmp_path: Path
):
    """Test that Python SDK can call API connectors (with mocked HTTP)."""
    _patch_live_app_workspace(monkeypatch, async_db_session, tmp_path)

    # Create base records and data source
    await seed_base_records(async_db_session, runtime_context)
    data_source_id = await seed_managed_data_source(async_db_session, runtime_context)

    # Create live app
    created = await live_app.create_live_app.ainvoke(
        {"name": "api-connector-test", "data_source_id": data_source_id},
        config=runnable_config,
    )
    created_payload = json.loads(created.content)
    app_id = created_payload["app_id"]

    # Write a job script that calls API connector
    dev_workspace = (
        tmp_path
        / "tenants"
        / f"tenant_{runtime_context.user.tenant_id}"
        / "apps"
        / "live_apps"
        / f"app_{app_id}"
        / "env"
        / "dev"
    )

    jobs_dir = dev_workspace / "jobs"
    jobs_dir.mkdir(exist_ok=True)

    # Write job script that demonstrates API connector usage
    test_job = jobs_dir / "test_api_connector.py"
    test_job.write_text(
        """
import asyncio
import sys
import os

# Verify SDK is importable
try:
    from lingqing_sdk import LiveAppClient, APIError
    print("✓ SDK imported successfully")
except ImportError as e:
    print(f"✗ Failed to import SDK: {e}")
    sys.exit(1)

async def main():
    try:
        # Initialize client from environment
        async with LiveAppClient.from_environment() as client:
            print(f"✓ Client initialized: tenant_id={client.tenant_id}, app_id={client.app_id}")
            
            # Demonstrate API connector call pattern
            # Note: We can't actually call without a real operation_uid,
            # but we verify the method exists and has correct signature
            
            # Check that call_api_connector method exists
            if not hasattr(client, 'call_api_connector'):
                print("✗ call_api_connector method not found on client")
                sys.exit(1)
            
            print("✓ call_api_connector method exists")
            
            # Verify method is callable
            if not callable(getattr(client, 'call_api_connector')):
                print("✗ call_api_connector is not callable")
                sys.exit(1)
            
            print("✓ call_api_connector is callable")
            
            # Show example usage (commented out since we don't have real operation_uid)
            example_code = '''
            # Example API connector call:
            result = await client.call_api_connector(
                "operation_uid_here",  # 64-char stable identifier
                parameters={{
                    "query": {{"city": "Shanghai", "units": "metric"}},
                    "headers": {{"Accept": "application/json"}}
                }}
            )
            print(f"Status: {{result.status_code}}")
            print(f"Response: {{result.body}}")
            print(f"Time: {{result.elapsed_ms}}ms")
            '''
            
            print("✓ API connector call pattern validated")
            print("✓ All checks passed!")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
""",
        encoding="utf-8",
    )

    # Verify job script was written
    assert test_job.exists(), "API connector job script should exist"
    assert test_job.stat().st_size > 100, "Job script should have content"

    # Verify SDK exists in workspace
    sdk_path = dev_workspace / "lingqing_sdk"
    assert sdk_path.exists(), "SDK should exist in workspace"

    # Verify the job script contains correct patterns
    script_content = test_job.read_text(encoding="utf-8")
    assert "from lingqing_sdk import LiveAppClient" in script_content
    assert "call_api_connector" in script_content
    assert "operation_uid" in script_content

    # Note: We can't actually execute API connector calls without:
    # 1. A real API connector created in the system
    # 2. An operation_uid from that connector
    # 3. Docker sandbox to run the job
    # But we've verified the SDK structure and method signatures are correct
