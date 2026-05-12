"""Pydantic models for LingQing SDK requests and responses."""

from typing import Any

from pydantic import BaseModel


class ApiOperationCallParameters(BaseModel):
    """Typed payload for external API operation runtime arguments."""

    query: dict[str, Any] | None = None
    path: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None


class ApiExecutionResult(BaseModel):
    """Result from executing an API connector operation."""

    status_code: int
    body: Any
    headers: dict[str, str]
    elapsed_ms: float
    error: str | None = None


class LiveAppQueryResult(BaseModel):
    """Result from a SQL query execution."""

    rows: list[list[Any]]
    columns: list[str]
    row_count: int


class LiveAppMutateResult(BaseModel):
    """Result from a data mutation operation."""

    app_id: int
    operation: str
    table: str
    affected_rows: int


class LiveAppImportResult(BaseModel):
    """Result from a CSV import operation."""

    app_id: int
    table: str
    file_name: str
    mode: str
    imported_rows: int
