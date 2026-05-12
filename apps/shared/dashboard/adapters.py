"""Adapters for dashboard module conversions."""

from typing import Any, TypeVar

from pydantic import BaseModel

from apps.shared.dashboard.domain import (
    ChartDisplayConfig,
    DashboardConfig,
    DashboardDomain,
    DashboardFilter,
    DashboardFilterOption,
    DashboardLayout,
    DashboardWidget,
    FieldMapping,
    GaugeDisplayConfig,
    ScatterDisplayConfig,
    TableColumnConfig,
    TableDisplayConfig,
    TableValueFormat,
    WidgetPosition,
)
from apps.shared.dashboard.schemas import (
    ChartDisplayConfigDTO,
    DashboardConfigDTO,
    DashboardFilterDTO,
    DashboardFilterOptionDTO,
    DashboardLayoutDTO,
    DashboardResponse,
    DashboardWidgetDTO,
    FieldMappingDTO,
    GaugeDisplayConfigDTO,
    ScatterDisplayConfigDTO,
    TableColumnConfigDTO,
    TableDisplayConfigDTO,
    TableValueFormatDTO,
    WidgetPositionDTO,
)
from apps.shared.db import models as db_models

T = TypeVar("T", bound=BaseModel)


# ============================================================================
# Generic Mapping Utilities
# ============================================================================


def auto_map_to_dto(source: Any, dto_class: type[T], **overrides) -> T:
    """Auto-map domain object fields to DTO with optional overrides.

    Args:
        source: Source domain object (dataclass or dict)
        dto_class: Target Pydantic DTO class
        **overrides: Explicit field overrides (e.g., custom_field=value)

    Returns:
        Instance of dto_class

    Example:
        position_dto = auto_map_to_dto(widget.position, WidgetPositionDTO)
        layout_dto = auto_map_to_dto(config.layout, DashboardLayoutDTO, type="grid")
    """
    # Build field dict from source
    if hasattr(source, "__dataclass_fields__"):
        # Source is a dataclass
        field_values = {field: getattr(source, field) for field in source.__dataclass_fields__}
    elif isinstance(source, dict):
        # Source is a dict
        field_values = source.copy()
    else:
        # Try to access as object attributes
        field_values = {field: getattr(source, field, None) for field in dto_class.model_fields.keys()}

    # Apply overrides
    field_values.update(overrides)

    # Filter to only fields that exist in DTO
    dto_fields = {k: v for k, v in field_values.items() if k in dto_class.model_fields}

    return dto_class(**dto_fields)


# ============================================================================
# Dashboard Filter Adapters
# ============================================================================


def table_value_format_dto_to_domain(dto: TableValueFormatDTO | None) -> TableValueFormat | None:
    """Convert TableValueFormatDTO to domain TableValueFormat."""
    if dto is None:
        return None
    return TableValueFormat(
        format_type=dto.format_type,
        precision=dto.precision,
        currency=dto.currency,
        date_format=dto.date_format,
        prefix=dto.prefix,
        suffix=dto.suffix,
        null_display=dto.null_display,
        true_label=dto.true_label,
        false_label=dto.false_label,
    )


def table_column_config_dto_to_domain(dto: TableColumnConfigDTO) -> TableColumnConfig:
    """Convert TableColumnConfigDTO to domain TableColumnConfig."""
    return TableColumnConfig(
        field=dto.field,
        label=dto.label,
        align=dto.align,
        width=dto.width,
        min_width=dto.min_width,
        max_width=dto.max_width,
        format=table_value_format_dto_to_domain(dto.format),
    )


def table_display_config_dto_to_domain(dto: TableDisplayConfigDTO | None) -> TableDisplayConfig | None:
    """Convert TableDisplayConfigDTO to domain TableDisplayConfig."""
    if dto is None:
        return None
    return TableDisplayConfig(
        columns=[table_column_config_dto_to_domain(col) for col in dto.columns] if dto.columns else None,
        default_format=table_value_format_dto_to_domain(dto.default_format),
        show_header=dto.show_header,
        show_row_numbers=dto.show_row_numbers,
        zebra_stripes=dto.zebra_stripes,
        compact=dto.compact,
    )


def gauge_display_config_dto_to_domain(dto: GaugeDisplayConfigDTO | None) -> GaugeDisplayConfig | None:
    """Convert GaugeDisplayConfigDTO to domain GaugeDisplayConfig."""
    if dto is None:
        return None
    return GaugeDisplayConfig(
        min_value=dto.min_value,
        max_value=dto.max_value,
        unit=dto.unit,
        thresholds=dto.thresholds,
        start_angle=dto.start_angle,
        end_angle=dto.end_angle,
        show_detail=dto.show_detail,
        show_axis_label=dto.show_axis_label,
    )


def scatter_display_config_dto_to_domain(dto: ScatterDisplayConfigDTO | None) -> ScatterDisplayConfig | None:
    """Convert ScatterDisplayConfigDTO to domain ScatterDisplayConfig."""
    if dto is None:
        return None
    return ScatterDisplayConfig(
        size_range=dto.size_range,
        color_scale_type=dto.color_scale_type,
        color_range=dto.color_range,
    )


def chart_display_config_dto_to_domain(dto: ChartDisplayConfigDTO | None) -> ChartDisplayConfig | None:
    """Convert ChartDisplayConfigDTO to domain ChartDisplayConfig."""
    if dto is None:
        return None
    return ChartDisplayConfig(
        title=dto.title,
        description=dto.description,
        x_label=dto.x_label,
        y_label=dto.y_label,
        series_labels=dto.series_labels,
        show_legend=dto.show_legend,
        legend_position=dto.legend_position,
        metric_format=dto.metric_format,
        scatter=scatter_display_config_dto_to_domain(dto.scatter),
        gauge=gauge_display_config_dto_to_domain(dto.gauge),
        table=table_display_config_dto_to_domain(dto.table),
    )


def widget_position_dto_to_domain(dto: WidgetPositionDTO) -> WidgetPosition:
    """Convert WidgetPositionDTO to domain WidgetPosition."""
    return WidgetPosition(
        x=dto.x,
        y=dto.y,
        w=dto.w,
        h=dto.h,
    )


def field_mapping_dto_to_domain(dto: FieldMappingDTO | None) -> FieldMapping | None:
    """Convert FieldMappingDTO to domain FieldMapping."""
    if dto is None:
        return None
    return FieldMapping(
        x_axis=dto.x_axis,
        y_axis=dto.y_axis,
        series=dto.series,
        value=dto.value,
        size=dto.size,
        color=dto.color,
        extra=dto.extra,
    )


def dashboard_filter_option_dto_to_domain(dto: DashboardFilterOptionDTO) -> DashboardFilterOption:
    """Convert DashboardFilterOptionDTO to domain DashboardFilterOption."""
    return DashboardFilterOption(
        label=dto.label,
        value=dto.value,
    )


def dashboard_filter_dto_to_domain(dto: DashboardFilterDTO) -> DashboardFilter:
    """Convert DashboardFilterDTO to domain DashboardFilter."""
    return DashboardFilter(
        id=dto.id,
        name=dto.name,
        type=dto.type,
        param_key=dto.param_key,
        value=dto.value,
        data_source_id=dto.data_source_id,
        options_query=dto.options_query,
        options=[dashboard_filter_option_dto_to_domain(opt) for opt in dto.options] if dto.options else None,
        allow_multiple=dto.allow_multiple,
        time_precision=dto.time_precision,
        description=dto.description,
        required=bool(dto.required),
    )


def filter_dto_to_domain(filter_dto: DashboardFilterDTO) -> DashboardFilter:
    """Convert DashboardFilterDTO to DashboardFilter domain model.

    Args:
        filter_dto: Filter DTO from API/tool layer

    Returns:
        DashboardFilter domain model
    """
    option_models = None
    if filter_dto.options is not None:
        option_models = [DashboardFilterOption(label=opt.label, value=opt.value) for opt in filter_dto.options]

    return DashboardFilter(
        id=filter_dto.id,
        name=filter_dto.name,
        type=filter_dto.type,
        param_key=filter_dto.param_key,
        value=filter_dto.value,
        data_source_id=filter_dto.data_source_id,
        options_query=filter_dto.options_query,
        options=option_models,
        allow_multiple=filter_dto.allow_multiple,
        time_precision=filter_dto.time_precision,
        description=filter_dto.description,
        required=bool(filter_dto.required),
    )


def dashboard_config_dto_to_domain(dto: DashboardConfigDTO) -> DashboardConfig:
    """Convert DashboardConfigDTO to domain DashboardConfig."""
    layout = DashboardLayout(
        type=dto.layout.type,
        cols=dto.layout.cols,
        rows=dto.layout.rows,
        gap=dto.layout.gap,
        row_height=dto.layout.row_height,
    )

    widgets = [
        DashboardWidget(
            id=widget.id,
            type=widget.type,
            position=widget_position_dto_to_domain(widget.position),
            chart_type=widget.chart_type,
            display_config=chart_display_config_dto_to_domain(widget.display_config),
            options=widget.options,
            data_source_id=widget.data_source_id,
            query=widget.query,
            field_mapping=field_mapping_dto_to_domain(widget.field_mapping),
        )
        for widget in dto.widgets
    ]

    filters = [dashboard_filter_dto_to_domain(f) for f in dto.filters] if dto.filters else None

    return DashboardConfig(
        layout=layout,
        widgets=widgets,
        filters=filters,
    )


def dict_options_to_dto_options(options: list[dict] | None) -> list[DashboardFilterOptionDTO] | None:
    """Convert list of dict options to DashboardFilterOptionDTO list.

    Args:
        options: List of dict with 'label' and 'value' keys, or None

    Returns:
        List of DashboardFilterOptionDTO or None
    """
    if options is None:
        return None
    return [DashboardFilterOptionDTO(label=str(opt.get("label", "")), value=opt.get("value")) for opt in options]


# ============================================================================
# Table Format Adapters
# ============================================================================


def _table_format_to_dict(format_config: TableValueFormat | None) -> dict | None:
    if not format_config:
        return None

    return {
        "formatType": format_config.format_type,
        "precision": format_config.precision,
        "currency": format_config.currency,
        "dateFormat": format_config.date_format,
        "prefix": format_config.prefix,
        "suffix": format_config.suffix,
        "nullDisplay": format_config.null_display,
        "trueLabel": format_config.true_label,
        "falseLabel": format_config.false_label,
    }


def _dict_to_table_format(format_dict: dict | None) -> TableValueFormat | None:
    if not format_dict:
        return None

    return TableValueFormat(
        format_type=format_dict.get("formatType"),
        precision=format_dict.get("precision"),
        currency=format_dict.get("currency"),
        date_format=format_dict.get("dateFormat"),
        prefix=format_dict.get("prefix"),
        suffix=format_dict.get("suffix"),
        null_display=format_dict.get("nullDisplay"),
        true_label=format_dict.get("trueLabel"),
        false_label=format_dict.get("falseLabel"),
    )


def display_config_to_dict(display: ChartDisplayConfig | None) -> dict | None:
    """Convert ChartDisplayConfig to dict for JSON serialization.

    Converts snake_case Python fields to camelCase for frontend consumption.
    Returns None if display config is None.
    """
    if not display:
        return None

    gauge_config = None
    if display.gauge:
        gauge_config = {
            "minValue": display.gauge.min_value,
            "maxValue": display.gauge.max_value,
            "unit": display.gauge.unit,
            "thresholds": display.gauge.thresholds,
            "startAngle": display.gauge.start_angle,
            "endAngle": display.gauge.end_angle,
            "showDetail": display.gauge.show_detail,
            "showAxisLabel": display.gauge.show_axis_label,
        }

    scatter_config = None
    if display.scatter:
        scatter_config = {
            "sizeRange": display.scatter.size_range,
            "colorScaleType": display.scatter.color_scale_type,
            "colorRange": display.scatter.color_range,
        }

    table_config = None
    if display.table:
        columns = None
        if display.table.columns is not None:
            columns = [
                {
                    "field": column.field,
                    "label": column.label,
                    "align": column.align,
                    "width": column.width,
                    "minWidth": column.min_width,
                    "maxWidth": column.max_width,
                    "format": _table_format_to_dict(column.format),
                }
                for column in display.table.columns
            ]

        table_config = {
            "columns": columns,
            "defaultFormat": _table_format_to_dict(display.table.default_format),
            "showHeader": display.table.show_header,
            "showRowNumbers": display.table.show_row_numbers,
            "zebraStripes": display.table.zebra_stripes,
            "compact": display.table.compact,
        }

    return {
        "title": display.title,
        "xLabel": display.x_label,
        "yLabel": display.y_label,
        "seriesLabels": display.series_labels,
        "showLegend": display.show_legend,
        "legendPosition": display.legend_position,
        "metricFormat": display.metric_format,
        "description": display.description,
        "scatter": scatter_config,
        "gauge": gauge_config,
        "table": table_config,
    }


def dict_to_display_config(display_dict: dict | None) -> ChartDisplayConfig | None:
    """Convert dict to ChartDisplayConfig domain model.

    Handles conversion from JSON (camelCase) to typed domain model (snake_case).
    Returns None only if display_dict is None, empty dict creates config with defaults.
    """
    if display_dict is None:
        return None

    gauge_dict = display_dict.get("gauge")
    gauge_config = None
    if gauge_dict:
        gauge_config = GaugeDisplayConfig(
            min_value=gauge_dict.get("minValue"),
            max_value=gauge_dict.get("maxValue"),
            unit=gauge_dict.get("unit"),
            thresholds=gauge_dict.get("thresholds"),
            start_angle=gauge_dict.get("startAngle"),
            end_angle=gauge_dict.get("endAngle"),
            show_detail=gauge_dict.get("showDetail"),
            show_axis_label=gauge_dict.get("showAxisLabel"),
        )

    scatter_dict = display_dict.get("scatter")
    scatter_config = None
    if scatter_dict:
        scatter_config = ScatterDisplayConfig(
            size_range=scatter_dict.get("sizeRange"),
            color_scale_type=scatter_dict.get("colorScaleType"),
            color_range=scatter_dict.get("colorRange"),
        )
    elif (
        display_dict.get("scatterSizeRange") is not None
        or display_dict.get("colorScaleType") is not None
        or display_dict.get("colorRange") is not None
    ):
        scatter_config = ScatterDisplayConfig(
            size_range=display_dict.get("scatterSizeRange"),
            color_scale_type=display_dict.get("colorScaleType"),
            color_range=display_dict.get("colorRange"),
        )

    table_dict = display_dict.get("table")
    table_config = None
    if table_dict:
        columns = None
        column_dicts = table_dict.get("columns")
        if column_dicts is not None:
            columns = [
                TableColumnConfig(
                    field=column.get("field", ""),
                    label=column.get("label"),
                    align=column.get("align"),
                    width=column.get("width"),
                    min_width=column.get("minWidth"),
                    max_width=column.get("maxWidth"),
                    format=_dict_to_table_format(column.get("format")),
                )
                for column in column_dicts
            ]

        table_config = TableDisplayConfig(
            columns=columns,
            default_format=_dict_to_table_format(table_dict.get("defaultFormat")),
            show_header=table_dict.get("showHeader", True),
            show_row_numbers=table_dict.get("showRowNumbers", False),
            zebra_stripes=table_dict.get("zebraStripes"),
            compact=table_dict.get("compact"),
        )

    return ChartDisplayConfig(
        title=display_dict.get("title"),
        x_label=display_dict.get("xLabel"),
        y_label=display_dict.get("yLabel"),
        series_labels=display_dict.get("seriesLabels"),
        show_legend=display_dict.get("showLegend", True),
        legend_position=display_dict.get("legendPosition"),
        metric_format=display_dict.get("metricFormat"),
        description=display_dict.get("description"),
        scatter=scatter_config,
        gauge=gauge_config,
        table=table_config,
    )


def dict_to_dashboard_config(config_dict: dict) -> DashboardConfig:
    """Convert dict to DashboardConfig domain model.

    Handles conversion from JSON config stored in database to typed domain model.
    """
    layout_dict = config_dict.get("layout", {})
    layout = DashboardLayout(
        type=layout_dict.get("type", "grid"),
        cols=layout_dict.get("cols", 12),
        rows=layout_dict.get("rows", 12),
        gap=layout_dict.get("gap", 16),
        row_height=layout_dict.get("rowHeight", 80),
    )

    widgets = []
    for w in config_dict.get("widgets", []):
        pos_dict = w.get("position", {})
        position = WidgetPosition(
            x=pos_dict.get("x", 0),
            y=pos_dict.get("y", 0),
            w=pos_dict.get("w", 12),
            h=pos_dict.get("h", 6),
        )

        # Parse field_mapping if present
        fm_dict = w.get("fieldMapping")
        field_mapping = None
        if fm_dict:
            field_mapping = FieldMapping(
                x_axis=fm_dict.get("xAxis"),
                y_axis=fm_dict.get("yAxis"),
                series=fm_dict.get("series"),
                value=fm_dict.get("value"),
                color=fm_dict.get("color"),
                size=fm_dict.get("size"),
                extra=fm_dict.get("extra"),
            )

        # Parse display_config if present
        display_config = dict_to_display_config(w.get("displayConfig"))

        widget = DashboardWidget(
            id=w["id"],
            type=w["type"],
            position=position,
            chart_type=w.get("chartType"),
            display_config=display_config,
            options=w.get("options"),
            data_source_id=w.get("dataSourceId"),
            query=w.get("query"),
            field_mapping=field_mapping,
        )
        widgets.append(widget)

    filters = []
    for f in config_dict.get("filters", []) or []:
        options = None
        option_dicts = f.get("options")
        if option_dicts is not None:
            options = [
                DashboardFilterOption(label=opt.get("label", ""), value=opt.get("value")) for opt in option_dicts
            ]

        filters.append(
            DashboardFilter(
                id=f.get("id", ""),
                name=f.get("name", ""),
                type=f.get("type"),
                param_key=f.get("paramKey"),
                value=f.get("value"),
                data_source_id=f.get("dataSourceId"),
                options_query=f.get("optionsQuery"),
                options=options,
                allow_multiple=f.get("allowMultiple"),
                time_precision=f.get("timePrecision"),
                description=f.get("description"),
                required=bool(f.get("required", False)),
            )
        )

    return DashboardConfig(
        layout=layout,
        widgets=widgets,
        filters=filters or None,
    )


def dashboard_config_to_dict(config: DashboardConfig) -> dict:
    """Convert DashboardConfig domain model to dict for JSON serialization."""
    return {
        "layout": {
            "type": config.layout.type,
            "cols": config.layout.cols,
            "rows": config.layout.rows,
            "gap": config.layout.gap,
            "rowHeight": config.layout.row_height,
        },
        "widgets": [
            {
                "id": w.id,
                "type": w.type,
                "position": {
                    "x": w.position.x,
                    "y": w.position.y,
                    "w": w.position.w,
                    "h": w.position.h,
                },
                "chartType": w.chart_type,
                "displayConfig": display_config_to_dict(w.display_config),
                "options": w.options,
                "dataSourceId": w.data_source_id,
                "query": w.query,
                "fieldMapping": {
                    "xAxis": w.field_mapping.x_axis,
                    "yAxis": w.field_mapping.y_axis,
                    "series": w.field_mapping.series,
                    "value": w.field_mapping.value,
                    "size": w.field_mapping.size,
                    "color": w.field_mapping.color,
                    "extra": w.field_mapping.extra,
                }
                if w.field_mapping
                else None,
            }
            for w in config.widgets
        ],
        "filters": [
            {
                "id": f.id,
                "name": f.name,
                "type": f.type,
                "paramKey": f.param_key,
                "value": f.value,
                "dataSourceId": f.data_source_id,
                "optionsQuery": f.options_query,
                "options": [{"label": option.label, "value": option.value} for option in (f.options or [])]
                if f.options is not None
                else None,
                "allowMultiple": f.allow_multiple,
                "timePrecision": f.time_precision,
                "description": f.description,
                "required": f.required,
            }
            for f in (config.filters or [])
        ]
        if config.filters is not None
        else None,
    }


def db_dashboard_to_domain(
    db_dashboard: db_models.Dashboard | None,
    *,
    owner_username: str | None = None,
) -> DashboardDomain | None:
    """Convert DB Dashboard model to domain model."""
    if not db_dashboard:
        return None

    # Convert JSON config dict to typed DashboardConfig
    config = dict_to_dashboard_config(db_dashboard.config or {})

    return DashboardDomain(
        id=db_dashboard.id,
        tenant_id=db_dashboard.tenant_id,
        name=db_dashboard.name,
        description=db_dashboard.description,
        config=config,
        owner_id=db_dashboard.owner_id,
        owner_username=owner_username,
        created_at=db_dashboard.created_at,
        updated_at=db_dashboard.updated_at,
    )


def domain_dashboard_to_response(domain: DashboardDomain) -> DashboardResponse:
    """Convert domain dashboard to response DTO."""
    # Convert domain config to DTO
    config_dto = domain_config_to_dto(domain.config)

    return DashboardResponse(
        id=domain.id,
        tenant_id=domain.tenant_id,
        name=domain.name,
        description=domain.description,
        config=config_dto,
        owner_id=domain.owner_id,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


# ============================================================================
# Domain → DTO converters (for API responses)
# ============================================================================


def _table_format_to_dto(format_domain: TableValueFormat | None) -> TableValueFormatDTO | None:
    """Convert domain TableValueFormat to DTO."""
    if not format_domain:
        return None
    return auto_map_to_dto(format_domain, TableValueFormatDTO)


def _display_config_to_dto(display: ChartDisplayConfig | None) -> ChartDisplayConfigDTO | None:
    """Convert domain ChartDisplayConfig to DTO."""
    if not display:
        return None

    # Convert nested configs
    gauge_dto = auto_map_to_dto(display.gauge, GaugeDisplayConfigDTO) if display.gauge else None
    scatter_dto = auto_map_to_dto(display.scatter, ScatterDisplayConfigDTO) if display.scatter else None

    table_dto = None
    if display.table:
        columns_dto = None
        if display.table.columns is not None:
            columns_dto = [
                auto_map_to_dto(col, TableColumnConfigDTO, format=_table_format_to_dto(col.format))
                for col in display.table.columns
            ]

        table_dto = auto_map_to_dto(
            display.table,
            TableDisplayConfigDTO,
            columns=columns_dto,
            default_format=_table_format_to_dto(display.table.default_format),
        )

    return auto_map_to_dto(display, ChartDisplayConfigDTO, scatter=scatter_dto, gauge=gauge_dto, table=table_dto)


def domain_filter_to_dto(filter_domain: DashboardFilter) -> DashboardFilterDTO:
    """Convert domain DashboardFilter to DashboardFilterDTO for API responses."""
    options_dto = None
    if filter_domain.options is not None:
        options_dto = [auto_map_to_dto(opt, DashboardFilterOptionDTO) for opt in filter_domain.options]

    param_names = None
    macro_template = None
    try:
        param_names = filter_domain.get_param_names()
        macro_template = filter_domain.get_macro_template()
    except ValueError:
        pass

    return auto_map_to_dto(
        filter_domain,
        DashboardFilterDTO,
        options=options_dto,
        param_names=param_names,
        macro_template=macro_template,
    )


def domain_widget_to_dto(widget: DashboardWidget) -> DashboardWidgetDTO:
    """Convert domain DashboardWidget to DTO for API responses."""
    position_dto = auto_map_to_dto(widget.position, WidgetPositionDTO)
    field_mapping_dto = auto_map_to_dto(widget.field_mapping, FieldMappingDTO) if widget.field_mapping else None
    display_config_dto = _display_config_to_dto(widget.display_config)

    return auto_map_to_dto(
        widget,
        DashboardWidgetDTO,
        position=position_dto,
        display_config=display_config_dto,
        field_mapping=field_mapping_dto,
    )


def domain_config_to_dto(config: DashboardConfig) -> DashboardConfigDTO:
    """Convert domain DashboardConfig to DTO for API responses."""
    # Convert layout using auto_map
    layout_dto = auto_map_to_dto(config.layout, DashboardLayoutDTO)

    # Convert widgets
    widgets_dto = []
    for widget in config.widgets:
        widgets_dto.append(domain_widget_to_dto(widget))

    # Convert filters
    filters_dto = None
    if config.filters:
        filters_dto = [domain_filter_to_dto(f) for f in config.filters]

    return DashboardConfigDTO(
        layout=layout_dto,
        widgets=widgets_dto,
        filters=filters_dto,
    )
