"""Tests for PostgreSQL URL helpers."""

from apps.shared.db.url import build_postgres_asyncpg_url, sqlalchemy_url_for_alembic_ini


def test_build_postgres_asyncpg_url_encodes_special_characters():
    url = build_postgres_asyncpg_url(
        user="lq_user",
        password="!p_%^&*",
        host="db.example.com",
        port=5432,
        db_name="lq_app",
        ssl_mode="prefer",
    )
    assert url.startswith("postgresql+asyncpg://lq_user:")
    assert "%25" in url  # literal % in password
    assert url.endswith("?ssl=prefer")


def test_sqlalchemy_url_for_alembic_ini_doubles_percent():
    raw = "postgresql+asyncpg://u:p%25x@host:5432/db"
    assert sqlalchemy_url_for_alembic_ini(raw) == "postgresql+asyncpg://u:p%%25x@host:5432/db"
