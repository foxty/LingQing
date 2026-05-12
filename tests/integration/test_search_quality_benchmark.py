import pytest

from tests.integration.search_quality_benchmark_runner import execute_topn_cases
from tests.integration.search_quality_test_utils import get_search_quality_modes


@pytest.mark.parametrize("resource", ["api_connector", "document", "asset"])
@pytest.mark.parametrize("search_mode", get_search_quality_modes())
def test_search_quality_topn(search_quality_benchmark_env, monkeypatch, search_mode: str, resource: str):
    execute_topn_cases(
        env=search_quality_benchmark_env,
        resource=resource,
        search_mode=search_mode,
        monkeypatch=monkeypatch,
    )
