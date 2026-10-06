"""Integration test configuration.

Spins up a real PostgreSQL container (via testcontainers) once per test session
and provides a per-test session with SAVEPOINT-based rollback for isolation.

Why testcontainers?
- Zero pre-setup: Docker pulls postgres:16-alpine automatically.
- Same image as dev.yml, so behaviour is identical.
- Works locally and in CI without extra services blocks.

Session isolation strategy:
  Each test function gets an AsyncSession bound to an outer connection whose
  transaction is never committed.  The session is configured with
  join_transaction_mode="create_savepoint", so when the code under test calls
  session.commit() it merely releases a SAVEPOINT, leaving the outer
  transaction intact.  After the test the outer transaction is rolled back,
  leaving the database pristine for the next test.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import docker
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.core.container import DockerContainer

# Test-only secret key (must match the one set in tests/conftest.py)
TEST_SECRET_KEY = "test-secret-key"


def _ensure_docker_host() -> None:
    """Resolve the Docker socket when DOCKER_HOST is not set.

    Docker Desktop exposes /var/run/docker.sock.  Colima (the lightweight
    macOS alternative) exposes the socket at ~/.colima/default/docker.sock
    instead.  Testcontainers reads DOCKER_HOST, so we set it here if it is
    missing and the standard socket does not exist.
    """
    if os.environ.get("DOCKER_HOST"):
        return  # already configured — trust it

    standard = Path("/var/run/docker.sock")
    if standard.exists():
        return  # Docker Desktop or compatible — standard path works

    # Colima default socket
    colima = Path.home() / ".colima" / "default" / "docker.sock"
    if colima.exists():
        os.environ["DOCKER_HOST"] = f"unix://{colima}"
        return

    # Rancher Desktop socket
    rancher = Path.home() / ".rd" / "docker.sock"
    if rancher.exists():
        os.environ["DOCKER_HOST"] = f"unix://{rancher}"
        return

    raise RuntimeError(
        "Docker socket not found.  Start Docker Desktop, Colima, or Rancher Desktop, "
        "or set the DOCKER_HOST environment variable explicitly."
    )


# _ensure_docker_host() is called lazily inside fixtures so pytest can still
# collect (discover) integration tests even when Docker is not running.

# Ryuk is the testcontainers resource-reaper sidecar.  It is downloaded from
# Docker Hub at test startup and therefore fails when the registry is
# unreachable (e.g. Colima with no internet, CI with no pull credentials).
# Disabling it is safe: testcontainers registers an atexit handler that stops
# all managed containers when the Python process exits.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _wait_for_chroma_http(host: str, port: int, timeout_seconds: int = 30) -> None:
    """Wait until Chroma HTTP heartbeat endpoint is available."""

    deadline = time.time() + timeout_seconds
    url = f"http://{host}:{port}/api/v2/heartbeat"

    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 - controlled local test endpoint
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            time.sleep(0.5)

    raise TimeoutError(f"Chroma HTTP endpoint did not become ready: {url}")


def _ensure_docker_daemon_available() -> None:
    """Skip test when Docker daemon is unavailable for testcontainers."""

    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for integration tests: {exc}")


def _run_tenant_app_migrations(host: str, port: str, user: str, password: str, db_name: str) -> None:
    """Run tenant app Alembic migrations against the integration test database."""

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["TENANT_APP_DB_HOST"] = host
    env["TENANT_APP_DB_PORT"] = str(port)
    env["TENANT_APP_DB_USER"] = user
    env["TENANT_APP_DB_PASSWORD"] = password
    env["TENANT_APP_DB_NAME"] = db_name

    uv_bin = shutil.which("uv")
    if uv_bin:
        cmd = [
            uv_bin,
            "run",
            "alembic",
            "-c",
            "apps/tenant_app_service/alembic.ini",
            "upgrade",
            "head",
        ]
    else:
        # Fallback for environments where pytest's subprocess PATH does not include uv.
        cmd = [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/tenant_app_service/alembic.ini",
            "upgrade",
            "head",
        ]

    subprocess.run(cmd, cwd=repo_root, env=env, check=True)


# ─── Container + schema (session-scoped, fully synchronous) ───────────────────


@pytest.fixture(scope="session")
def pg_container():
    """Start a postgres:16-alpine container and create the schema once per session.

    Schema creation is done with a *synchronous* SQLAlchemy engine so that no
    async event loop is involved at session scope.  Function-scoped async tests
    each create their own asyncpg engine and therefore never cross event-loop
    boundaries with a shared engine.
    """
    import socket
    import time

    from testcontainers.postgres import PostgresContainer

    _ensure_docker_host()
    with PostgresContainer("postgres:16-alpine") as pg:
        # ── Wait for host-side port-forward to be ready ──────────────────────
        # testcontainers' own wait strategy checks inside the container; on
        # Colima the Lima port-forward to the macOS host can take an extra
        # moment to come up.
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        deadline = time.time() + 30
        while True:
            try:
                with socket.create_connection((host, int(port)), timeout=1):
                    break
            except (ConnectionRefusedError, OSError):
                if time.time() >= deadline:
                    raise TimeoutError(f"Postgres port {host}:{port} not accessible after 30 s")
                time.sleep(0.5)

        # ── Patch env-vars so app modules pick up the test DB coordinates ────
        os.environ["TENANT_APP_DB_HOST"] = host
        os.environ["TENANT_APP_DB_PORT"] = str(port)
        os.environ["TENANT_APP_DB_USER"] = pg.username
        os.environ["TENANT_APP_DB_PASSWORD"] = pg.password
        os.environ["TENANT_APP_DB_NAME"] = pg.dbname

        # ── Create schema via Alembic migrations to mirror production behavior ─
        _run_tenant_app_migrations(
            host=host,
            port=str(port),
            user=pg.username,
            password=pg.password,
            db_name=pg.dbname,
        )

        # Yield the asyncpg URL; the container stays alive until session ends.
        sync_url: str = pg.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        yield async_url


@pytest.fixture(scope="session", autouse=True)
def chroma_http_endpoint(pg_container):
    """Start a Chroma HTTP server container and configure env vars for tests.

    HTTP Chroma is integration-only. Unit tests must not inherit CHROMA_MODE=http
    from the root conftest (that caused chromadb.HttpClient heartbeats to hang).

    This fixture is autouse=True and depends on pg_container to ensure proper
    fixture ordering. CHROMA_MODE and CHROMA_URL are set so application code uses
    the test ChromaDB instance.

    After setting up ChromaDB, we reload apps.config to pick up the new values.
    """

    _ensure_docker_daemon_available()

    with (
        DockerContainer("chromadb/chroma:1.4.1")
        .with_exposed_ports(8000)
        .with_env("CHROMA_SERVER_HOST", "0.0.0.0")
        .with_env("CHROMA_SERVER_HTTP_PORT", "8000")
    ) as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(8000))
        _wait_for_chroma_http(host, port)

        # Configure environment variables for ChromaDB HTTP mode
        os.environ["CHROMA_MODE"] = "http"
        os.environ["CHROMA_URL"] = f"http://{host}:{port}"

        # Force reload of apps.config to pick up the new ChromaDB settings
        import importlib

        import apps.config

        importlib.reload(apps.config)

        # Also reload modules that may have cached the config
        import apps.shared.infra.rag.chroma_backend

        importlib.reload(apps.shared.infra.rag.chroma_backend)

        yield host, port


# ─── Per-test session with SAVEPOINT rollback ─────────────────────────────────


@pytest_asyncio.fixture
async def pg_async_db_session(pg_container):
    """Function-scoped AsyncSession that rolls back all changes after each test.

    Each test gets a *fresh* async engine so there is no asyncpg connection
    pool shared across different pytest-asyncio event loops (which would cause
    "cannot perform operation: another operation is in progress" errors with
    pytest-asyncio ≥ 1.x).

    Uses SQLAlchemy's join_transaction_mode="create_savepoint" so that calls to
    session.commit() inside the code under test release a SAVEPOINT rather than
    actually committing, keeping the outer transaction intact.  The outer
    transaction is rolled back when the fixture tears down.
    """
    engine = create_async_engine(pg_container, echo=False, future=True)
    try:
        async with engine.connect() as connection:
            async with connection.begin() as transaction:
                session = AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                yield session
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def async_db_session(pg_async_db_session):
    """Backward-compatible alias for integration tests expecting async_db_session.

    Integration tests should use PostgreSQL-backed sessions.
    """
    yield pg_async_db_session


# ─── Shared data fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def sample_tenant_user_thread(pg_async_db_session):
    """Insert Tenant + User + ChatThread and return (thread, tenant_id, user_id)."""
    from apps.shared.db.models import ChatThread, Tenant, User

    tenant = Tenant(name="Integration Tenant", slug="integration-tenant", status="active")
    pg_async_db_session.add(tenant)
    await pg_async_db_session.flush()

    user = User(
        username="integ_user",
        email="integ@example.com",
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
        status="active",
    )
    pg_async_db_session.add(user)
    await pg_async_db_session.flush()

    thread = ChatThread(
        id="integ-thread-001",
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=1,
        title="Integration Test Thread",
        message_count=0,
    )
    pg_async_db_session.add(thread)
    await pg_async_db_session.commit()

    return thread, tenant.id, user.id


# ─── Slack integration fixtures ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def slack_test_setup(pg_async_db_session: AsyncSession):
    """Set up two tenants with Slack integrations and a fake Slack client.

    Yields a dict with:
      - client: TestClient wired to the test DB
      - fake_slack: FakeSlackClient instance (shared across services)
      - tenants: {tenant_a, tenant_b} with tenant, admin user, admin token
      - secrets: {tenant_a: signing_secret, tenant_b: signing_secret}
    """
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from jose import jwt

    from apps.shared.db.session import get_db
    from apps.shared.db.models import Tenant, TenantMembership, User
    from apps.tenant_app_service.server import app
    from apps.tenant_app_service.agent_ingress.slack.client import SlackWebClient
    from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository
    from tests.slack.fake_slack import FakeSlackClient
    from tests.slack.session_factory import build_serializing_savepoint_sessions

    connection = await pg_async_db_session.connection()
    TestSessionLocal, override_get_db, fake_app_db_session = build_serializing_savepoint_sessions(
        connection
    )

    app.dependency_overrides[get_db] = override_get_db

    from apps.tenant_app_service.agent_ingress.slack import ingress_router as ingress_router_module

    original_app_db_session = ingress_router_module.__dict__.get("app_db_session")
    from apps.shared.db import session as _db_session_module

    _db_session_module.app_db_session = fake_app_db_session

    fake_slack = FakeSlackClient()

    async def _fake_auth_test(self, *, bot_token):
        return await fake_slack.auth_test(bot_token=bot_token)

    async def _fake_users_info(self, *, bot_token, user_id):
        return await fake_slack.users_info(bot_token=bot_token, user_id=user_id)

    async def _fake_chat_post_message(self, *, bot_token, channel, text, thread_ts=None, blocks=None):
        return await fake_slack.chat_post_message(
            bot_token=bot_token, channel=channel, text=text, thread_ts=thread_ts, blocks=blocks
        )

    async def _fake_chat_update(self, *, bot_token, channel, ts, text, blocks=None):
        return await fake_slack.chat_update(
            bot_token=bot_token, channel=channel, ts=ts, text=text, blocks=blocks
        )

    async def _fake_conversations_open(self, *, bot_token, users):
        return await fake_slack.conversations_open(bot_token=bot_token, users=users)

    SlackWebClient.auth_test = _fake_auth_test  # type: ignore
    SlackWebClient.users_info = _fake_users_info  # type: ignore
    SlackWebClient.chat_post_message = _fake_chat_post_message  # type: ignore
    SlackWebClient.chat_update = _fake_chat_update  # type: ignore
    SlackWebClient.conversations_open = _fake_conversations_open  # type: ignore

    def _create_token(user_id, username, role, tenant_id, tenant_name):
        expire = datetime.now(timezone.utc) + timedelta(hours=24)
        to_encode = {
            "user_id": user_id,
            "sub": username,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": expire,
        }
        return jwt.encode(to_encode, TEST_SECRET_KEY, algorithm="HS256")

    setup = {"fake_slack": fake_slack, "tenants": {}, "secrets": {}, "endpoint_keys": {}}

    async with TestSessionLocal() as seed_session:
        for label in ("tenant_a", "tenant_b"):
            suffix = uuid4().hex[:8]
            tenant = Tenant(
                name=f"slack_test_{label}_{suffix}",
                slug=f"slack_test_{label}_{suffix}",
                config=None,
            )
            seed_session.add(tenant)
            await seed_session.flush()

            admin = User(
                username=f"admin_{label}_{suffix}",
                email=f"admin_{label}_{suffix}@test.local.{suffix}",
                hashed_password="$2b$12$dummy",
                tenant_id=tenant.id,
                role="admin",
            )
            seed_session.add(admin)
            await seed_session.flush()

            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=admin.id,
                status="active",
            )
            seed_session.add(membership)
            await seed_session.flush()

            token = _create_token(admin.id, admin.username, "admin", tenant.id, tenant.name)
            signing_secret = f"signing_secret_{label}_{suffix}"
            bot_token = f"xoxb-{label}-{suffix}"

            setup["tenants"][label] = {
                "tenant": tenant,
                "admin": admin,
                "token": token,
                "external_domain": f"external.com.{suffix}",
            }
            setup["secrets"][label] = signing_secret

            from apps.tenant_app_service.agent_ingress.slack.source_repository import (
                SlackIdentitySourceRepository,
            )

            source_repo = SlackIdentitySourceRepository(seed_session)
            team_id = f"T_{label.upper()}"
            identity_source = await source_repo.ensure_slack_workspace_source(
                tenant_id=tenant.id,
                team_id=team_id,
            )
            repo = SlackRepository(seed_session)
            endpoint = await repo.create_endpoint(
                tenant_id=tenant.id,
                bot_token=bot_token,
                signing_secret=signing_secret,
                agent_id=-1,
                enabled=True,
                team_id=team_id,
                identity_source_id=identity_source.id,
            )
            setup["endpoint_keys"][label] = endpoint.endpoint_key

            # Allow the email domains used by test Slack users through the
            # tenant login-domain allowlist (empty list means deny-all).
            # Domain names are globally unique, so suffix them per tenant.
            from apps.shared.db.models import TenantLoginDomain

            for base in ("test.local", "external.com"):
                domain = f"{base}.{suffix}"
                seed_session.add(TenantLoginDomain(tenant_id=tenant.id, domain=domain))
            await seed_session.commit()

    setup["session_factory"] = TestSessionLocal

    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        setup["client"] = async_client
        yield setup

    app.dependency_overrides.clear()
    if original_app_db_session is not None:
        _db_session_module.app_db_session = original_app_db_session


def make_auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_oidc_adapter(monkeypatch):
    """Inject FakeOidcAdapter into SsoLoginService for integration tests."""
    from apps.tenant_app_service.sso.login_service import SsoLoginService
    from tests.sso.fake_oidc import FakeOidcAdapter

    fake = FakeOidcAdapter()
    original_init = SsoLoginService.__init__

    def patched_init(self, db, adapter=None, token_issuer=None, binding_service=None):
        original_init(self, db, adapter=fake, token_issuer=token_issuer, binding_service=binding_service)

    monkeypatch.setattr(SsoLoginService, "__init__", patched_init)
    return fake


# expose the shared helper for slack tests
from tests.slack.fake_slack import FakeSlackClient  # noqa: E402,F401
from tests.integration.search_quality_benchmark_shared import search_quality_benchmark_env  # noqa: E402,F401
