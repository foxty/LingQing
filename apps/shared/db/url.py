"""PostgreSQL URL helpers for SQLAlchemy/asyncpg and Alembic."""

from urllib.parse import quote_plus


def build_postgres_asyncpg_url(
    *,
    user: str,
    password: str,
    host: str,
    port: int | str,
    db_name: str,
    ssl_mode: str | None = None,
) -> str:
    """Build a postgresql+asyncpg URL with URL-encoded credentials."""
    user_q = quote_plus(user or "")
    password_q = quote_plus(password or "")
    url = f"postgresql+asyncpg://{user_q}:{password_q}@{host}:{port}/{db_name}"
    if ssl_mode:
        url += f"?ssl={ssl_mode}"
    return url


def build_postgres_psycopg2_url(
    *,
    user: str,
    password: str,
    host: str,
    port: int | str,
    db_name: str,
    ssl_mode: str | None = None,
) -> str:
    """Build a postgresql+psycopg2 URL (libpq ``sslmode`` query param)."""
    user_q = quote_plus(user or "")
    password_q = quote_plus(password or "")
    url = f"postgresql+psycopg2://{user_q}:{password_q}@{host}:{port}/{db_name}"
    if ssl_mode:
        url += f"?sslmode={quote_plus(ssl_mode)}"
    return url


def build_postgres_psycopg_url(
    *,
    user: str,
    password: str,
    host: str,
    port: int | str,
    db_name: str,
    ssl_mode: str | None = None,
) -> str:
    """Build a postgresql:// URL for psycopg3 (LangGraph Postgres checkpointer)."""
    user_q = quote_plus(user or "")
    password_q = quote_plus(password or "")
    url = f"postgresql://{user_q}:{password_q}@{host}:{port}/{db_name}"
    if ssl_mode:
        url += f"?sslmode={quote_plus(ssl_mode)}"
    return url


def sqlalchemy_url_for_alembic_ini(url: str) -> str:
    """Escape a URL for Alembic ConfigParser (``%`` → ``%%``)."""
    return url.replace("%", "%%")
