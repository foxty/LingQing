"""Search quality benchmark runner functions.

DEPRECATED: This module is being consolidated into search_quality_benchmark_shared.py.
Import from search_quality_benchmark_shared instead.
"""

# Re-export from shared module for backward compatibility
from tests.integration.search_quality_benchmark_shared import (
    RESOURCE_SPECS,
    execute_topn_cases,
)

__all__ = ["execute_topn_cases", "RESOURCE_SPECS"]