"""SQL identifier validation tests."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.utils.sql_utils import validate_sql_identifier


def test_validate_sql_identifier_accepts_simple_names():
    assert validate_sql_identifier("orders_2024") == "orders_2024"


def test_validate_sql_identifier_rejects_injection():
    with pytest.raises(ValidationError):
        validate_sql_identifier("orders; DROP TABLE users")
