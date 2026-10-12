"""Clip SQL authz filters to an agent's attached resource IDs (intersection with user scope)."""

from __future__ import annotations

from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.authz.authz_query_builder import AuthzSqlFilter


def combine_agent_scope(
    *,
    user_scope: AuthzSqlFilter,
    id_column: ColumnElement,
    allowed_ids: list[int] | None,
) -> AuthzSqlFilter:
    """Restrict a SQL authz filter to the agent attachment set (user scope ∩ allowed_ids).

    ``allowed_ids is None``: no agent clip (system Agent One).
    Empty ``allowed_ids``: deny all.
    """
    if allowed_ids is None:
        return user_scope
    if not allowed_ids:
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)

    allowed_clause = id_column.in_(allowed_ids)
    if user_scope.allow_all:
        return AuthzSqlFilter(allow_all=False, deny_all=False, clause=allowed_clause)
    if user_scope.deny_all or user_scope.clause is None:
        return AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    return AuthzSqlFilter(allow_all=False, deny_all=False, clause=and_(user_scope.clause, allowed_clause))
