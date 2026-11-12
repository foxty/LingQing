"""Integration smoke for /search (FTS, vector, hybrid wiring — not embedding quality)."""

import pytest

from tests.integration.search_integration_smoke_shared import execute_topn_cases
from tests.integration.search_integration_smoke_utils import get_search_integration_smoke_modes


@pytest.mark.parametrize("resource", ["api_connector", "document", "asset"])
@pytest.mark.parametrize("search_mode", get_search_integration_smoke_modes())
def test_search_integration_smoke_topn(
    search_integration_smoke_env, monkeypatch, search_mode: str, resource: str
):
    execute_topn_cases(
        env=search_integration_smoke_env,
        resource=resource,
        search_mode=search_mode,
        monkeypatch=monkeypatch,
    )
