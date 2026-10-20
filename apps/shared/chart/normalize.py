"""Map agent-facing chart_type inputs to Plotly renderer types."""

from apps.shared.chart.types import (
    AGENT_CHART_INPUT_TYPES,
    PLOTLY_CHART_TYPES,
    PlotlyChartType,
)


def normalize_plotly_chart_type(
    chart_type: PlotlyChartType,
    series_keys: list[str] | None,
    stacked: bool,
) -> PlotlyChartType:
    """Map chart_type to the Plotly renderer variant (grouped/stacked/multi when needed).

    Accepts ``AgentChartInputType`` values plus legacy explicit names
    (``grouped_bar``, ``stacked_bar``, ``multi_line``, ``multi_area``).
    Agent tools should only pass the six public input types.
    """
    if chart_type not in PLOTLY_CHART_TYPES:
        agent_list = ", ".join(f"'{t}'" for t in sorted(AGENT_CHART_INPUT_TYPES))
        raise ValueError(
            f"Unknown chart_type '{chart_type}'. "
            f"Valid types: {agent_list}. "
            f"For multi-series bar/line/area, use the type and provide series_key or series_keys."
        )
    if chart_type == "bar" and series_keys:
        return "stacked_bar" if stacked else "grouped_bar"
    if chart_type == "line" and series_keys:
        return "multi_line"
    if chart_type == "area" and series_keys:
        return "multi_area"
    return chart_type
