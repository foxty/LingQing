"""Unified application configuration.

Configuration Principles:
1. Application Constants: Hard-coded values that rarely change
2. Environment-dependent Config: Load from environment variables
3. Secrets: MUST be loaded from env vars, never hard-coded
"""

import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse


def parse_chroma_http_url(url: str) -> tuple[str, int, bool]:
    """Parse CHROMA_URL into chromadb.HttpClient host, port, and ssl flag."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"CHROMA_URL must use http or https scheme, got: {url!r}")
    if not parsed.hostname:
        raise ValueError(f"CHROMA_URL must include a hostname, got: {url!r}")

    ssl = parsed.scheme == "https"
    if parsed.port is not None:
        port = parsed.port
    else:
        port = 443 if ssl else 80
    return parsed.hostname, port, ssl


class AppConfig:
    """Application-level configuration (constants that rarely change)."""

    # ============ Application Constants (Hard-coded) ============

    # API Metadata
    API_TITLE: str = "LingQing API"
    API_DESCRIPTION: str = "企业级 AI 智能体平台 - 多租户智能体管理和交互 API"
    API_VERSION: str = "2.0.0"

    # Security Algorithms
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 1 week

    # Document Processing
    SUPPORTED_DOCUMENT_EXTENSIONS: set[str] = {
        ".pdf",
        ".docx",
        ".ppt",
        ".pptx",
        ".html",
        ".htm",
        ".md",
        ".xlsx",
        ".xls",
    }


class EnvConfig:
    """Environment-dependent configuration (loaded from environment variables)."""

    # ============ Shared Settings ============

    SECRET_KEY: str = os.getenv("SECRET_KEY")
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    CHART_SERVICE_URL: str = os.getenv("CHART_SERVICE_URL")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # ============ LLM Configuration ============
    # LLM configuration has been migrated to tenant-level settings.
    # Configure LLM providers and API keys via frontend Settings page.
    # No environment variables needed for LLM anymore.
    # ============ Observability Configuration ============
    # Metrics Configuration
    # Maximum length for tool input/output preview in extra_context
    # 0 = disabled, -1 = unlimited (not recommended for production)
    METRICS_PREVIEW_MAX_LENGTH: int = int(os.getenv("METRICS_PREVIEW_MAX_LENGTH", "500"))

    # ============ Agent Sandbox Configuration ============
    AGENT_SANDBOX_BASE_URL: str = os.getenv("AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")
    AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS", "15"))
    AGENT_SANDBOX_MAX_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_SANDBOX_MAX_TIMEOUT_SECONDS", "60"))
    AGENT_SANDBOX_OUTPUT_MAX_BYTES: int = int(os.getenv("AGENT_SANDBOX_OUTPUT_MAX_BYTES", "262144"))
    AGENT_SANDBOX_MAX_COMMAND_CHARS: int = int(os.getenv("AGENT_SANDBOX_MAX_COMMAND_CHARS", "24000"))
    AGENT_SANDBOX_CLIENT_TIMEOUT_BUFFER_SECONDS: int = int(
        os.getenv("AGENT_SANDBOX_CLIENT_TIMEOUT_BUFFER_SECONDS", "10")
    )

    # ============ Scheduled Task Execution Configuration ============
    # Optional fixed scheduler instance id. When empty, runtime falls back to host-pid.
    SCHEDULER_INSTANCE_ID: str = os.getenv("SCHEDULER_INSTANCE_ID", "")
    SCHEDULED_TASK_LEASE_TTL_SECONDS: int = int(os.getenv("SCHEDULED_TASK_LEASE_TTL_SECONDS", "90"))
    SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS: int = int(os.getenv("SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS", "15"))
    SCHEDULED_TASK_WATCHDOG_LIMIT: int = int(os.getenv("SCHEDULED_TASK_WATCHDOG_LIMIT", "100"))

    # Sandbox runner API base URL (injected into runner containers for platform API calls)
    SANDBOX_RUNNER_API_BASE_URL: str = os.getenv(
        "SANDBOX_RUNNER_API_BASE_URL", "http://localhost:8000"
    )

    # Tenant app portal origin (used for SSO callback redirects back to the portal)
    PORTAL_ORIGIN: str = os.getenv("PORTAL_ORIGIN", "http://localhost:5173")

    # Public origin of the tenant_app_service API. Used to build absolute OIDC
    # redirect_uri values that the IdP redirects the browser back to. Must match
    # the origin admins register at their IdP for the SSO callback.
    TENANT_APP_API_ORIGIN: str = os.getenv("TENANT_APP_API_ORIGIN", "http://localhost:8000")

    # ============ Storage Configuration ============

    # Data Storage Root
    DATA_ROOT_PATH: str = os.getenv("DATA_ROOT_PATH")

    # ============ Document Processing Configuration ============
    DOCUMENT_PARSER: str = os.getenv("DOCUMENT_PARSER", "default")
    MINERU_SERVICE_URL: str = os.getenv("MINERU_SERVICE_URL", "")
    MINERU_POLL_INTERVAL_SECONDS: int = int(os.getenv("MINERU_POLL_INTERVAL_SECONDS", "5"))
    MINERU_TASK_TIMEOUT_SECONDS: int = int(os.getenv("MINERU_TASK_TIMEOUT_SECONDS", "900"))
    DOCLING_SERVICE_URL: str = os.getenv("DOCLING_SERVICE_URL", "")
    DOCLING_TASK_TIMEOUT_SECONDS: int = int(os.getenv("DOCLING_TASK_TIMEOUT_SECONDS", "600"))
    DOCLING_API_KEY: str = os.getenv("DOCLING_API_KEY", "")
    DOCLING_DO_OCR: bool = os.getenv("DOCLING_DO_OCR", "false").lower() == "true"
    DOCUMENT_PARSE_JOB_BATCH_SIZE: int = int(os.getenv("DOCUMENT_PARSE_JOB_BATCH_SIZE", "10"))
    DOCUMENT_CHUNK_SIZE: int = int(os.getenv("DOCUMENT_CHUNK_SIZE", "512"))
    DOCUMENT_CHUNK_OVERLAP: int = int(os.getenv("DOCUMENT_CHUNK_OVERLAP", "64"))
    DOCUMENT_CHUNK_MIN_CHARS: int = int(os.getenv("DOCUMENT_CHUNK_MIN_CHARS", "80"))
    DOCUMENT_TABLE_MAX_CHARS: int = int(os.getenv("DOCUMENT_TABLE_MAX_CHARS", "3000"))

    # ============ Database Configuration ============
    # PostgreSQL database (application database for all environments)
    # Prefer TENANT_APP_DB_*; APP_DB_* is kept as legacy fallback.
    TENANT_APP_DB_HOST: str = os.getenv("TENANT_APP_DB_HOST", os.getenv("APP_DB_HOST", "localhost"))
    TENANT_APP_DB_PORT: int = int(os.getenv("TENANT_APP_DB_PORT", os.getenv("APP_DB_PORT", "5432")))
    TENANT_APP_DB_USER: str = os.getenv("TENANT_APP_DB_USER", os.getenv("APP_DB_USER", ""))
    TENANT_APP_DB_PASSWORD: str = os.getenv("TENANT_APP_DB_PASSWORD", os.getenv("APP_DB_PASSWORD", ""))
    TENANT_APP_DB_NAME: str = os.getenv("TENANT_APP_DB_NAME", os.getenv("APP_DB_NAME", ""))
    TENANT_APP_DB_SSL_MODE: str = os.getenv(
        "TENANT_APP_DB_SSL_MODE", os.getenv("APP_DB_SSL_MODE", "prefer")
    )  # prefer, require, disable

    # Tenant manager control-plane database (optional, fallback to TENANT_APP_DB_* when empty)
    TENANT_MANAGER_DB_HOST: str = os.getenv("TENANT_MANAGER_DB_HOST", "")
    TENANT_MANAGER_DB_PORT: int = int(os.getenv("TENANT_MANAGER_DB_PORT", "0"))
    TENANT_MANAGER_DB_USER: str = os.getenv("TENANT_MANAGER_DB_USER", "")
    TENANT_MANAGER_DB_PASSWORD: str = os.getenv("TENANT_MANAGER_DB_PASSWORD", "")
    TENANT_MANAGER_DB_NAME: str = os.getenv("TENANT_MANAGER_DB_NAME", "")
    TENANT_MANAGER_DB_SSL_MODE: str = os.getenv("TENANT_MANAGER_DB_SSL_MODE", "")

    # Tenant database naming convention
    TENANT_DB_PREFIX: str = os.getenv("TENANT_DB_PREFIX", "tenant_")
    TENANT_DB_SUFFIX: str = os.getenv("TENANT_DB_SUFFIX", "_analytics")

    # Tenant database connection pooling
    TENANT_POOL_SIZE: int = int(os.getenv("TENANT_POOL_SIZE", "5"))
    TENANT_POOL_MAX_OVERFLOW: int = int(os.getenv("TENANT_POOL_MAX_OVERFLOW", "10"))
    TENANT_POOL_CACHE_SIZE: int = int(os.getenv("TENANT_POOL_CACHE_SIZE", "50"))

    # Asset discovery
    DISCOVERY_ASSET_LIMIT: int = int(os.getenv("DISCOVERY_ASSET_LIMIT", "50"))

    # Vector indexing mode
    # - sync: index immediately during write path
    # - async: defer indexing to scheduler jobs
    VECTOR_INDEXING_MODE: Literal["sync", "async"] = os.getenv("VECTOR_INDEXING_MODE", "sync").lower()

    # Chroma deployment mode
    # - embedded: in-process local storage (persist_directory)
    # - http: connect to external Chroma server via HttpClient
    CHROMA_MODE: Literal["embedded", "http"] = os.getenv("CHROMA_MODE", "embedded").lower()
    CHROMA_URL: str = os.getenv("CHROMA_URL", "")
    CHROMA_COLLECTION_PREFIX: str = os.getenv("CHROMA_COLLECTION_PREFIX", "tenant_")

    @classmethod
    def chroma_http_client_kwargs(cls) -> dict[str, str | int | bool]:
        """Build chromadb.HttpClient kwargs from CHROMA_URL."""
        host, port, ssl = parse_chroma_http_url(cls.CHROMA_URL)
        return {"host": host, "port": port, "ssl": ssl}

    # File Storage Type
    FILE_STORAGE_TYPE: Literal["local", "s3"] = os.getenv("FILE_STORAGE_TYPE", "local")
    # S3 Storage (for AWS/Alibaba/Tencent Cloud via S3 protocol)
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-west-2")
    S3_PREFIX: str = os.getenv("S3_PREFIX", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")  # For S3-compatible services
    S3_USE_SSL: bool = os.getenv("S3_USE_SSL", "true").lower() == "true"
    OBJECT_STORAGE_ACCESS_KEY: str = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "")
    OBJECT_STORAGE_SECRET_KEY: str = os.getenv("OBJECT_STORAGE_SECRET_KEY", "")

    @classmethod
    def validate(cls):
        """Validate critical environment variables."""
        from apps.shared.utils.logger import get_logger

        logger = get_logger(__name__)
        errors = []

        if not cls.DATA_ROOT_PATH:
            errors.append("DATA_ROOT_PATH environment variable must be set")

        # Check PostgreSQL config
        if not cls.TENANT_APP_DB_USER or not cls.TENANT_APP_DB_PASSWORD:
            errors.append("TENANT_APP_DB_USER and TENANT_APP_DB_PASSWORD are required")
        if not cls.TENANT_APP_DB_NAME:
            errors.append("TENANT_APP_DB_NAME is required")
        if not cls.TENANT_APP_DB_HOST:
            errors.append("TENANT_APP_DB_HOST is required")

        # Check S3 config if S3 storage is used
        if cls.FILE_STORAGE_TYPE == "s3" and not cls.S3_BUCKET:
            errors.append("S3_BUCKET is required when FILE_STORAGE_TYPE=s3")

        if cls.VECTOR_INDEXING_MODE not in ("sync", "async"):
            errors.append("VECTOR_INDEXING_MODE must be one of: sync, async")

        if cls.CHROMA_MODE not in ("embedded", "http"):
            errors.append("CHROMA_MODE must be one of: embedded, http")
        if cls.CHROMA_MODE == "http":
            if not cls.CHROMA_URL:
                errors.append("CHROMA_URL is required when CHROMA_MODE=http")
            else:
                try:
                    _, port, _ = parse_chroma_http_url(cls.CHROMA_URL)
                    if port <= 0:
                        errors.append("CHROMA_URL must include a positive port when CHROMA_MODE=http")
                except ValueError as exc:
                    errors.append(str(exc))

        if cls.AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS <= 0:
            errors.append("AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS must be a positive integer")
        if cls.AGENT_SANDBOX_MAX_TIMEOUT_SECONDS <= 0:
            errors.append("AGENT_SANDBOX_MAX_TIMEOUT_SECONDS must be a positive integer")
        if cls.AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS > cls.AGENT_SANDBOX_MAX_TIMEOUT_SECONDS:
            errors.append("AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS must be <= AGENT_SANDBOX_MAX_TIMEOUT_SECONDS")
        if cls.AGENT_SANDBOX_OUTPUT_MAX_BYTES <= 0:
            errors.append("AGENT_SANDBOX_OUTPUT_MAX_BYTES must be a positive integer")
        if cls.AGENT_SANDBOX_MAX_COMMAND_CHARS <= 0:
            errors.append("AGENT_SANDBOX_MAX_COMMAND_CHARS must be a positive integer")
        if cls.AGENT_SANDBOX_CLIENT_TIMEOUT_BUFFER_SECONDS < 0:
            errors.append("AGENT_SANDBOX_CLIENT_TIMEOUT_BUFFER_SECONDS must be >= 0")
        if not cls.AGENT_SANDBOX_BASE_URL:
            errors.append("AGENT_SANDBOX_BASE_URL is required")

        if cls.SCHEDULED_TASK_LEASE_TTL_SECONDS <= 0:
            errors.append("SCHEDULED_TASK_LEASE_TTL_SECONDS must be a positive integer")
        if cls.SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS <= 0:
            errors.append("SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS must be a positive integer")
        if cls.SCHEDULED_TASK_WATCHDOG_LIMIT <= 0:
            errors.append("SCHEDULED_TASK_WATCHDOG_LIMIT must be a positive integer")

        if errors:
            logger.error(f"Configuration warnings: {', '.join(errors)}")
            raise ValueError("Invalid environment configuration.")
            return False

        return True


_file_storage_instance = None


def reset_file_storage_cache() -> None:
    """Clear cached file storage (for tests)."""
    global _file_storage_instance
    _file_storage_instance = None


def get_file_storage():
    """Return a process-wide FileStorage instance based on configuration."""
    global _file_storage_instance
    if _file_storage_instance is not None:
        return _file_storage_instance

    from apps.shared.infra.storage.file_storage import LocalFileStorage, S3FileStorage
    from apps.shared.utils.logger import get_logger

    logger = get_logger(__name__)

    storage_type = EnvConfig.FILE_STORAGE_TYPE.lower()

    if storage_type == "local":
        logger.debug("Using LocalFileStorage with tenant-centric paths")
        _file_storage_instance = LocalFileStorage()

    elif storage_type == "s3":
        if not EnvConfig.S3_BUCKET:
            raise ValueError("S3_BUCKET environment variable is required for S3 storage")

        provider = "AWS S3" if not EnvConfig.S3_ENDPOINT_URL else f"S3-compatible ({EnvConfig.S3_ENDPOINT_URL})"
        logger.debug(
            "Using S3FileStorage: provider=%s, bucket=%s, region=%s",
            provider,
            EnvConfig.S3_BUCKET,
            EnvConfig.S3_REGION,
        )

        _file_storage_instance = S3FileStorage(
            bucket=EnvConfig.S3_BUCKET,
            region=EnvConfig.S3_REGION,
            prefix=EnvConfig.S3_PREFIX,
            endpoint_url=EnvConfig.S3_ENDPOINT_URL or None,
            access_key_id=EnvConfig.OBJECT_STORAGE_ACCESS_KEY or None,
            secret_access_key=EnvConfig.OBJECT_STORAGE_SECRET_KEY or None,
            use_ssl=EnvConfig.S3_USE_SSL,
        )

    else:
        raise ValueError(f"Unknown FILE_STORAGE_TYPE: {storage_type}. Supported types: local, s3")

    return _file_storage_instance


def get_vector_indexing_mode() -> Literal["sync", "async"]:
    """Return vector indexing mode for write paths.

    Returns:
        "sync" to index inline, "async" to defer indexing to scheduler.
    """
    mode = EnvConfig.VECTOR_INDEXING_MODE
    if mode in ("sync", "async"):
        return mode
    return "sync"


def should_index_on_write() -> bool:
    """Whether upload/create paths should perform inline vector indexing."""
    return get_vector_indexing_mode() == "sync"


# ============ Unified Settings (for backward compatibility) ============


@lru_cache
def get_settings():
    """Get unified settings instance (cached)."""

    class Settings:
        # Merge AppConfig and EnvConfig for backward compatibility
        SECRET_KEY = EnvConfig.SECRET_KEY
        ALGORITHM = AppConfig.JWT_ALGORITHM
        ACCESS_TOKEN_EXPIRE_MINUTES = AppConfig.ACCESS_TOKEN_EXPIRE_MINUTES
        API_TITLE = AppConfig.API_TITLE
        API_DESCRIPTION = AppConfig.API_DESCRIPTION
        API_VERSION = AppConfig.API_VERSION
        CORS_ORIGINS = EnvConfig.CORS_ORIGINS
        DATA_ROOT_PATH = EnvConfig.DATA_ROOT_PATH
        LOG_LEVEL = EnvConfig.LOG_LEVEL
        PORTAL_ORIGIN = EnvConfig.PORTAL_ORIGIN
        TENANT_APP_API_ORIGIN = EnvConfig.TENANT_APP_API_ORIGIN

    return Settings()


# ============ Tenant Storage Path Helpers ============


def get_tenant_data_root(tenant_id: int | str) -> str:
    """Get the root directory for a tenant's data.

    Creates the directory if it doesn't exist.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Absolute path to tenant data root: {DATA_ROOT_PATH}/tenants/tenant_{tenant_id}/

    Tenant root layout (planning baseline):
        {tenant_root}/
          workspace/                  # agent workspace
          apps/
            app_{app_id}/             # one app workspace
              .git/                   # app-scoped git repository
              env/
                dev|test|prod/
          documents/                  # uploaded knowledge files
          static/                     # tenant static assets
          vector_stores/              # vector index artifacts
          databases/                  # tenant local db files (if any)

    Example:
        >>> get_tenant_data_root(123)
        '/data/tenants/tenant_123'
    """
    from pathlib import Path

    tenant_path = Path(EnvConfig.DATA_ROOT_PATH) / "tenants" / f"tenant_{tenant_id}"
    tenant_path.mkdir(parents=True, exist_ok=True)
    return str(tenant_path)


def get_tenant_live_apps_root(tenant_id: int | str) -> str:
    """Get live apps workspace root under tenant data root.

    Returns:
        {tenant_root}/apps/
    """
    from pathlib import Path

    root = Path(get_tenant_data_root(tenant_id)) / "apps"
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def get_tenant_live_app_path(tenant_id: int | str, app_id: int | str) -> str:
    """Get path for one live app directory under tenant root.

    Returns:
        {tenant_root}/apps/app_{app_id}/
    """
    from pathlib import Path

    app_path = Path(get_tenant_live_apps_root(tenant_id)) / f"app_{app_id}"
    app_path.mkdir(parents=True, exist_ok=True)
    return str(app_path)


def get_static_path() -> str:
    """Get the static storage path.

    Returns:
        {DATA_ROOT_PATH}/static/
    """
    from pathlib import Path

    static_path = Path(EnvConfig.DATA_ROOT_PATH) / "static"
    static_path.mkdir(parents=True, exist_ok=True)
    return str(static_path)


def get_charts_path() -> str:
    """Get the charts storage path.

    Returns:
        {DATA_ROOT_PATH}/static/charts/
    """
    from pathlib import Path

    charts_path = Path(EnvConfig.DATA_ROOT_PATH) / "static/charts"
    charts_path.mkdir(parents=True, exist_ok=True)
    return str(charts_path)


def get_tenant_documents_path(tenant_id: int | str) -> str:
    """Get the documents storage path for a tenant.

    Creates the directory if it doesn't exist.

    Args:
        tenant_id: Tenant identifier

    Returns:
        {DATA_ROOT_PATH}/tenants/tenant_{tenant_id}/documents/

    Example:
        >>> get_tenant_documents_path(123)
        '/data/tenants/tenant_123/documents'
    """
    from pathlib import Path

    docs_path = Path(get_tenant_data_root(tenant_id)) / "documents"
    docs_path.mkdir(parents=True, exist_ok=True)
    return str(docs_path)


def get_tenant_static_file_path(tenant_id: int) -> str:
    """Get the static file path for a tenant. Will be enable user download or view through the UI.

    Args:
        tenant_id: Tenant identifier

    Returns:
        {DATA_ROOT_PATH}/tenants/tenant_{tenant_id}/static/
    """
    from pathlib import Path

    static_path = Path(get_tenant_data_root(tenant_id)) / "static"
    static_path.mkdir(parents=True, exist_ok=True)
    return str(static_path)


def get_tenant_vector_store_path(tenant_id: int | str) -> str:
    """Get the vector store path for a tenant.

    Creates the directory if it doesn't exist.

    Args:
        tenant_id: Tenant identifier

    Returns:
        {DATA_ROOT_PATH}/tenants/tenant_{tenant_id}/vector_stores/

    Example:
        >>> get_tenant_vector_store_path(123)
        '/data/tenants/tenant_123/vector_stores'
    """
    from pathlib import Path

    vector_path = Path(get_tenant_data_root(tenant_id)) / "vector_stores"
    vector_path.mkdir(parents=True, exist_ok=True)
    return str(vector_path)


def get_tenant_databases_path(tenant_id: int | str) -> str:
    """Get the databases storage path for a tenant (for uploaded SQLite files).

    Creates the directory if it doesn't exist.

    Args:
        tenant_id: Tenant identifier

    Returns:
        {DATA_ROOT_PATH}/tenants/tenant_{tenant_id}/databases/

    Example:
        >>> get_tenant_databases_path(123)
        '/data/tenants/tenant_123/databases'
    """
    from pathlib import Path

    databases_path = Path(get_tenant_data_root(tenant_id)) / "databases"
    databases_path.mkdir(parents=True, exist_ok=True)
    return str(databases_path)


def gen_analytics_db_url(tenant_id: int, ds_id: int) -> str:
    """Get the analytics database URL for a tenant.

    Args:
        tenant_id: Tenant identifier
        ds_id: Data source identifier

    Returns:
        Database URL in the format: sqlite:///path/to/db.db

    Example:
        >>> get_analytics_db_url(123)
        'sqlite:////data/tenants/tenant_123/analytics_db/analytics_<id>.db'
    """
    from pathlib import Path

    analytics_dir = Path(get_tenant_data_root(tenant_id)) / "analytics_db"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(analytics_dir / f"analytics_{ds_id}.db")
    return f"sqlite:///{db_path}"


# Initialize and validate on import
EnvConfig.validate()
