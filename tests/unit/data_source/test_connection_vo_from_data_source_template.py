"""Unit tests for data-source connection template factory."""

from apps.shared.domain.value_objects import DataSourceType
from apps.shared.external_systems.data_source.domain import connection_vo_from_data_source_template
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_SHARED, CREDENTIAL_MODE_USER


def test_databricks_user_mode_omits_shared_pat_validation():
    config = {
        "host": "adb-example.azuredatabricks.net",
        "extra_params": {"http_path": "/sql/1.0/warehouses/synthetic"},
        "user_credential_auth_type": "oauth2",
    }
    connection = connection_vo_from_data_source_template(
        config,
        data_source_type=DataSourceType.DATABRICKS,
        credential_mode=CREDENTIAL_MODE_USER,
    )
    assert connection.password is None
    assert connection.user_mode_template is True


def test_databricks_shared_mode_requires_pat():
    import pytest

    config = {
        "host": "adb-example.azuredatabricks.net",
        "extra_params": {"http_path": "/sql/1.0/warehouses/synthetic"},
    }
    with pytest.raises(ValueError, match="password"):
        connection_vo_from_data_source_template(
            config,
            data_source_type=DataSourceType.DATABRICKS,
            credential_mode=CREDENTIAL_MODE_SHARED,
        )


def test_postgres_user_mode_uses_byot_shape_without_flag():
    connection = connection_vo_from_data_source_template(
        {"host": "localhost", "port": 5432, "database": "app"},
        data_source_type=DataSourceType.POSTGRES,
        credential_mode=CREDENTIAL_MODE_USER,
    )
    assert connection.user_mode_template is False
    assert connection.password is None