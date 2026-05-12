"""Error hierarchy for analytics database operations."""


class AnalyticsDBError(Exception):
    """Base error for analytics DB operations."""

    pass


class PermissionError(AnalyticsDBError):
    """Attempted write operation on unmanaged database."""

    pass


class QueryExecutionError(AnalyticsDBError):
    """Query execution failed."""

    pass


class ConnectionError(AnalyticsDBError):
    """Database connection failed."""

    pass


class TableNotFoundError(AnalyticsDBError):
    """Table does not exist."""

    pass


class InvalidConfigurationError(AnalyticsDBError):
    """Invalid database configuration."""

    pass
