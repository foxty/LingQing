"""Unit tests for shared chart tool render kwargs."""

from apps.tenant_app_service.agents.tools.chart_support import chart_render_kwargs


def test_chart_render_kwargs_includes_enhancement_fields():
    kwargs = chart_render_kwargs(
        chart_type="line",
        data='[{"x":1}]',
        title="T",
        x_key="x",
        y_key="y",
        subtitle="Sub",
        reference_lines_json='[{"y": 1}]',
        annotations_json='[{"text": "note"}]',
        y_axis_percent=True,
        measure_key="kind",
    )
    assert kwargs["subtitle"] == "Sub"
    assert kwargs["reference_lines_json"] == '[{"y": 1}]'
    assert kwargs["annotations_json"] == '[{"text": "note"}]'
    assert kwargs["y_axis_percent"] is True
    assert kwargs["measure_key"] == "kind"
