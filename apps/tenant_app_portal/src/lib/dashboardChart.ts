import type { DashboardWidget, FieldMapping } from './dashboardApi'

type DataRow = Record<string, any>

const TOKEN_RGB_FALLBACK: Record<string, [number, number, number]> = {
  '--primary': [32, 163, 88],
  '--foreground': [40, 45, 52],
  '--chart-1': [32, 163, 88],
  '--chart-2': [28, 148, 168],
  '--chart-3': [214, 154, 42],
  '--chart-4': [196, 88, 72],
  '--chart-5': [118, 82, 168],
  '--chart-6': [196, 72, 132],
  '--chart-7': [72, 108, 168],
  '--chart-8': [214, 132, 48],
  '--chart-9': [48, 158, 178],
  '--chart-10': [132, 88, 148],
}

const CHART_BAND_TOKENS = [
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--chart-6',
  '--chart-7',
  '--chart-8',
  '--chart-9',
  '--chart-10',
] as const

function readTokenChannels(token: string): string {
  if (typeof document !== 'undefined') {
    const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
    if (value) return value
  }
  return ''
}

function cssToRgbBytes(cssColor: string, fallback: [number, number, number]): [number, number, number] {
  if (typeof document === 'undefined') return fallback
  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return fallback
  ctx.fillStyle = cssColor
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  if (a === 0) return fallback
  return [r, g, b]
}

function resolveTokenRgb(token: string, alpha?: number): string {
  const fallback = TOKEN_RGB_FALLBACK[token] ?? TOKEN_RGB_FALLBACK['--primary']
  const channels = readTokenChannels(token)
  const [r, g, b] = channels
    ? cssToRgbBytes(`oklch(${channels})`, fallback)
    : fallback
  return alpha == null ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function chartColorBand(): string[] {
  return CHART_BAND_TOKENS.map((token) => resolveTokenRgb(token))
}

function formatChartNumber(value: unknown): string {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return value == null ? '' : String(value)
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(numeric)
}

function applyReadableTooltip(options: Record<string, any>, trigger: 'axis' | 'item'): void {
  options.tooltip = {
    ...options.tooltip,
    trigger,
    valueFormatter: (value: unknown) => formatChartNumber(value),
  }
}

function pieTooltipFormatter(params: Record<string, any>): string {
  const name = sliceName(params?.name)
  const value = formatChartNumber(params?.value)
  const percent = typeof params?.percent === 'number' ? ` (${params.percent}%)` : ''
  const marker = params?.marker ?? ''
  return name ? `${marker} ${name}<br/>${value}${percent}` : `${marker} ${value}${percent}`
}

function sliceName(raw: unknown): string {
  if (raw == null) return ''
  const name = String(raw).trim()
  if (!name || name === '-' || name === '--') return ''
  return name
}

type SupportedChartType = NonNullable<DashboardWidget['chartType']>

const AXIS_SERIES_CHART_TYPES: SupportedChartType[] = [
  'line',
  'bar',
  'area',
  'stacked_bar',
  'grouped_bar',
  'multi_line',
  'multi_area',
]

const GRID_CHART_TYPES: SupportedChartType[] = [...AXIS_SERIES_CHART_TYPES, 'scatter', 'heatmap']

type AxisBuildConfig = {
  seriesType: 'line' | 'bar'
  area: boolean
  stacked: boolean
}

/**
 * Default chart option templates by chart type.
 * Backend no longer provides these; UI layer generates them from domain model.
 */
const CHART_TEMPLATES: Record<string, any> = {
  line: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  bar: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  area: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  pie: {
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', bottom: 4, left: 'center', icon: 'circle' },
    series: [{ type: 'pie', radius: ['36%', '60%'], avoidLabelOverlap: true }],
  },
  scatter: {
    tooltip: { trigger: 'item' },
    xAxis: { type: 'value' },
    yAxis: { type: 'value' },
    series: [{ type: 'scatter', symbolSize: 8 }],
  },
  heatmap: {
    tooltip: { position: 'top' },
    xAxis: { type: 'category' },
    yAxis: { type: 'category' },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 10,
    },
    series: [
      {
        type: 'heatmap',
        data: [],
        label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' } },
      },
    ],
  },
  stacked_bar: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  grouped_bar: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  multi_line: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  multi_area: {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category' },
    yAxis: { type: 'value' },
    series: [],
  },
  gauge: {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        splitNumber: 10,
        axisLine: {
          lineStyle: {
            width: 8,
          },
        },
        pointer: { width: 6 },
        detail: { fontSize: 18, valueAnimation: true },
        data: [{ value: 0 }],
      },
    ],
  },
}

export function buildChartOptions(
  widget: DashboardWidget,
  data: DataRow[]
): Record<string, any> | null {
  const mapping = widget.fieldMapping
  if (!mapping) return widget.options || null

  const chartType = widget.chartType
  if (!chartType) return widget.options || null

  // Route to chart-type-specific builder
  if (chartType === 'pie') {
    return buildPieChartOptions(widget, data)
  }

  if (chartType === 'line') {
    return buildAxisChartOptions(widget, data, 'line', {
      seriesType: 'line',
      area: false,
      stacked: false,
    })
  }

  if (chartType === 'bar') {
    return buildAxisChartOptions(widget, data, 'bar', {
      seriesType: 'bar',
      area: false,
      stacked: false,
    })
  }

  if (chartType === 'area') {
    return buildAxisChartOptions(widget, data, 'area', {
      seriesType: 'line',
      area: true,
      stacked: false,
    })
  }

  if (chartType === 'stacked_bar') {
    return buildAxisChartOptions(widget, data, 'stacked_bar', {
      seriesType: 'bar',
      area: false,
      stacked: true,
    })
  }

  if (chartType === 'grouped_bar') {
    return buildAxisChartOptions(widget, data, 'grouped_bar', {
      seriesType: 'bar',
      area: false,
      stacked: false,
    })
  }

  if (chartType === 'multi_line') {
    return buildAxisChartOptions(widget, data, 'multi_line', {
      seriesType: 'line',
      area: false,
      stacked: false,
    })
  }

  if (chartType === 'multi_area') {
    return buildAxisChartOptions(widget, data, 'multi_area', {
      seriesType: 'line',
      area: true,
      stacked: false,
    })
  }

  if (chartType === 'scatter') {
    return buildScatterChartOptions(widget, data)
  }

  if (chartType === 'heatmap') {
    return buildHeatmapChartOptions(widget, data)
  }

  if (chartType === 'gauge') {
    return buildGaugeChartOptions(widget, data)
  }

  return widget.options || null
}

/**
 * Build options for line and bar charts.
 */
function buildAxisChartOptions(
  widget: DashboardWidget,
  data: DataRow[],
  chartType: SupportedChartType,
  axisConfig: AxisBuildConfig
): Record<string, any> | null {
  const baseOptions = widget.options || CHART_TEMPLATES[chartType]
  if (!baseOptions) return null

  const options = cloneOptions(baseOptions)
  options.color = chartColorBand()
  applyReadableTooltip(options, 'axis')

  // Apply axis data mapping
  const mapping = widget.fieldMapping
  if (mapping) {
    applyAxisMapping(options, data, mapping, axisConfig)
  }

  // Apply display config (series labels must be applied after mapping builds series)
  applyDisplayConfig(options, widget)
  applySeriesLabels(options, widget)

  return options
}

/**
 * Build options for pie charts.
 */
function buildPieChartOptions(
  widget: DashboardWidget,
  data: DataRow[]
): Record<string, any> | null {
  // Always start from the pie template. Saved widget.options often carry bar
  // axes / grid from a previous chart type and would render a leftover Y-axis.
  const options = cloneOptions(CHART_TEMPLATES['pie'])
  options.color = chartColorBand()
  delete options.xAxis
  delete options.yAxis
  delete options.grid
  applyReadableTooltip(options, 'item')
  options.tooltip = {
    ...options.tooltip,
    formatter: pieTooltipFormatter,
  }

  applyDisplayConfig(options, widget)
  delete options.xAxis
  delete options.yAxis
  delete options.grid

  const mapping = widget.fieldMapping
  if (mapping) {
    applyPieMapping(options, data, mapping)
  }

  return options
}

/**
 * Build options for scatter charts.
 */
function buildScatterChartOptions(
  widget: DashboardWidget,
  data: DataRow[]
): Record<string, any> | null {
  const baseOptions = widget.options || CHART_TEMPLATES['scatter']
  if (!baseOptions) return null

  const options = cloneOptions(baseOptions)
  options.color = chartColorBand()

  // Apply scatter data mapping
  const mapping = widget.fieldMapping
  if (mapping) {
    applyScatterMapping(options, data, mapping, widget.displayConfig)
  }

  // Apply display config
  applyDisplayConfig(options, widget)

  return options
}

/**
 * Build options for heatmap charts.
 */
function buildHeatmapChartOptions(
  widget: DashboardWidget,
  data: DataRow[]
): Record<string, any> | null {
  const baseOptions = widget.options || CHART_TEMPLATES['heatmap']
  if (!baseOptions) return null

  const options = cloneOptions(baseOptions)

  const mapping = widget.fieldMapping
  if (mapping) {
    applyHeatmapMapping(options, data, mapping)
  }

  applyDisplayConfig(options, widget)

  return options
}

/**
 * Build options for gauge charts.
 */
function buildGaugeChartOptions(
  widget: DashboardWidget,
  data: DataRow[]
): Record<string, any> | null {
  const baseOptions = widget.options || CHART_TEMPLATES['gauge']
  if (!baseOptions) return null

  const options = cloneOptions(baseOptions)
  const series = Array.isArray(options.series) ? options.series : [{ type: 'gauge' }]
  const baseSeries = series[0] ?? { type: 'gauge' }
  series[0] = {
    ...baseSeries,
    axisLine: {
      ...baseSeries.axisLine,
      lineStyle: {
        ...baseSeries.axisLine?.lineStyle,
        color: [[1, resolveTokenRgb('--primary')]],
      },
    },
  }
  options.series = series

  // Apply display config
  applyDisplayConfig(options, widget)
  applyGaugeDisplayConfig(options, widget.displayConfig)

  // Apply gauge data mapping (single value)
  const value = extractMetricValue(data, widget)
  if (value !== null) {
    const series = Array.isArray(options.series) ? options.series : [{ type: 'gauge' }]
    const baseSeries = series[0] ?? { type: 'gauge' }
    series[0] = {
      ...baseSeries,
      data: [{ value }],
    }
    options.series = series
  }

  return options
}

/**
 * Apply displayConfig (domain layer) to chart options (UI layer).
 * Converts semantic display config to Echarts-specific option structures.
 */
function applyDisplayConfig(options: Record<string, any>, widget: DashboardWidget): void {
  const display = widget.displayConfig
  const chartType = widget.chartType
  if (!display) return

  // Apply title
  if (display.title) {
    options.title = {
      ...options.title,
      text: display.title,
      top: 10,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold' },
    }
  }

  // Axis names belong on cartesian charts only. Pie / gauge inherit leftover
  // xLabel / yLabel from a previous widget type and would draw a stray axis.
  const cartesian = Boolean(chartType && GRID_CHART_TYPES.includes(chartType))
  if (cartesian && display.xLabel) {
    options.xAxis = {
      ...options.xAxis,
      name: display.xLabel,
      nameLocation: 'middle',
      nameTextStyle: { fontSize: 12 },
      nameGap: 30,
    }
  }
  if (cartesian && display.yLabel) {
    options.yAxis = {
      ...options.yAxis,
      name: display.yLabel,
      nameLocation: 'middle',
      nameTextStyle: { fontSize: 12 },
      nameGap: 50,
    }
  }

  // Apply legend config
  if (display.showLegend !== undefined) {
    if (options.legend === undefined) {
      options.legend = {}
    }

    if (!display.showLegend) {
      options.legend.show = false
    } else {
      options.legend.show = true
      // Apply position if specified
      if (display.legendPosition) {
        const positionMap: Record<string, any> = {
          top: { orient: 'horizontal', top: 40, left: 'center' },
          bottom: { orient: 'horizontal', bottom: 10, left: 'center' },
          left: { orient: 'vertical', left: 10, top: 60 },
          right: { orient: 'vertical', right: 10, top: 60 },
        }
        options.legend = {
          ...options.legend,
          ...positionMap[display.legendPosition],
        }
      } else {
        // Default: legend on top for axis charts, bottom for pie
        if (chartType && AXIS_SERIES_CHART_TYPES.includes(chartType)) {
          options.legend = {
            ...options.legend,
            orient: 'horizontal',
            top: 40,
            left: 'center',
          }
        } else {
          options.legend = {
            ...options.legend,
            orient: 'horizontal',
            bottom: 10,
            left: 'center',
          }
        }
      }
    }
  }

  // Calculate and apply grid margins
  // Pie and gauge charts ignore grid, others can leverage dynamic margins.
  if (chartType && GRID_CHART_TYPES.includes(chartType)) {
    options.grid = calculateGridMargins(options.grid, display)
  }
}

function applySeriesLabels(options: Record<string, any>, widget: DashboardWidget): void {
  const display = widget.displayConfig
  if (!display?.seriesLabels || !Array.isArray(options.series)) return

  options.series = options.series.map((s: any) => {
    const label = display.seriesLabels?.[s.name || s.key]
    return label ? { ...s, name: label } : s
  })
}

function applyGaugeDisplayConfig(
  options: Record<string, any>,
  displayConfig: DashboardWidget['displayConfig']
): void {
  const gauge = displayConfig?.gauge
  if (!gauge) return

  const series = Array.isArray(options.series) ? options.series : [{ type: 'gauge' }]
  const baseSeries = series[0] ?? { type: 'gauge' }

  const nextSeries = {
    ...baseSeries,
    min: gauge.minValue ?? baseSeries.min,
    max: gauge.maxValue ?? baseSeries.max,
    startAngle: gauge.startAngle ?? baseSeries.startAngle,
    endAngle: gauge.endAngle ?? baseSeries.endAngle,
  }

  if (gauge.thresholds?.length) {
    nextSeries.axisLine = {
      ...baseSeries.axisLine,
      lineStyle: {
        ...baseSeries.axisLine?.lineStyle,
        color: gauge.thresholds,
      },
    }
  }

  if (gauge.showDetail !== undefined) {
    nextSeries.detail = {
      ...baseSeries.detail,
      show: gauge.showDetail,
    }
  }

  if (gauge.showAxisLabel !== undefined) {
    nextSeries.axisLabel = {
      ...baseSeries.axisLabel,
      show: gauge.showAxisLabel,
    }
  }

  if (gauge.unit) {
    nextSeries.detail = {
      ...baseSeries.detail,
      formatter: `{value} ${gauge.unit}`,
    }
  }

  series[0] = nextSeries
  options.series = series
}

export function extractMetricValue(data: DataRow[], widget: DashboardWidget): number | null {
  if (!data.length) return null
  const mapping = widget.fieldMapping
  const valueKey = mapping?.value
  if (!valueKey) return null
  const value = data[0]?.[valueKey]
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

/**
 * Calculate grid margins based on display config and chart type.
 * Dynamically adjusts spacing to prevent overlaps with title, legend, axis labels.
 */
function calculateGridMargins(
  existingGrid: Record<string, any> | undefined,
  display: any
): Record<string, any> {
  const SPACE_TITLE = 25
  const SPACE_LEGEND = 25
  const SPACE_LABEL = 25
  const BASE_MARGIN = 20

  const grid = existingGrid || {
    left: BASE_MARGIN,
    right: BASE_MARGIN,
    top: BASE_MARGIN,
    bottom: BASE_MARGIN,
    containLabel: true,
  }

  // Ensure all margins exist
  if (grid.left === undefined) grid.left = BASE_MARGIN
  if (grid.right === undefined) grid.right = BASE_MARGIN
  if (grid.top === undefined) grid.top = BASE_MARGIN
  if (grid.bottom === undefined) grid.bottom = BASE_MARGIN

  // Add space for title
  if (display?.title) {
    grid.top += SPACE_TITLE
  }

  // Add space for legend based on position and visibility
  if (display?.showLegend) {
    const legendPos = display.legendPosition
    switch (legendPos) {
      case 'top':
      case 'left':
      case 'right':
        grid.top += SPACE_LEGEND
        break
      case 'bottom':
        grid.bottom += SPACE_LEGEND
        break
    }
  }

  if (display.xLabel) {
    grid.bottom += SPACE_LABEL
  }

  if (display.yLabel) {
    grid.left += SPACE_LABEL
  }
  return grid
}

function applyAxisMapping(
  options: Record<string, any>,
  data: DataRow[],
  mapping: FieldMapping,
  axisConfig: AxisBuildConfig
): void {
  const xKey = mapping.xAxis
  const seriesKeys = Array.isArray(mapping.series) ? (mapping.series as string[]) : []

  // Apply x-axis data
  if (xKey) {
    options.xAxis = { ...options.xAxis, data: data.map((row) => row[xKey]) }
  }

  // Build series data
  const baseSeries = Array.isArray(options.series) ? options.series : []
  const palette = Array.isArray(options.color) && options.color.length ? options.color : chartColorBand()
  const categoricalBars =
    axisConfig.seriesType === 'bar' && !axisConfig.stacked && seriesKeys.length === 1
  const nextSeries = seriesKeys.map((key, index) => {
    const base = baseSeries[index] ?? { type: axisConfig.seriesType }
    const seriesColor = palette[index % palette.length]
    const dataPoints = categoricalBars
      ? data.map((row, rowIndex) => {
          const color = palette[rowIndex % palette.length]
          return {
            value: row[key],
            itemStyle: { color },
            emphasis: { itemStyle: { color, opacity: 1 } },
          }
        })
      : data.map((row) => row[key])
    const series: Record<string, any> = {
      ...base,
      name: base.name ?? key,
      type: axisConfig.seriesType,
      data: dataPoints,
      itemStyle: categoricalBars ? { ...base.itemStyle } : { ...base.itemStyle, color: seriesColor },
      lineStyle:
        axisConfig.seriesType === 'line'
          ? { width: 2, ...base.lineStyle, color: seriesColor }
          : base.lineStyle,
      emphasis: categoricalBars
        ? { disabled: false, focus: 'none' }
        : {
            disabled: false,
            focus: 'none',
            itemStyle: { color: seriesColor, opacity: 1 },
            lineStyle: { color: seriesColor, opacity: 1, width: 2 },
          },
      blur: {
        itemStyle: { opacity: 1 },
        lineStyle: { opacity: 1 },
      },
    }

    if (axisConfig.area) {
      series.areaStyle = {
        ...(base.areaStyle ?? {}),
      }
    }

    if (axisConfig.stacked) {
      series.stack = typeof base.stack === 'string' ? base.stack : 'total'
    }

    return series
  })

  if (nextSeries.length) {
    options.series = nextSeries
  }
}

function applyHeatmapMapping(
  options: Record<string, any>,
  data: DataRow[],
  mapping: FieldMapping
): void {
  const xKey = mapping.xAxis
  const yKey = mapping.yAxis
  const valueKey = mapping.value

  if (!xKey || !yKey || !valueKey) return

  const xValues = Array.from(new Set(data.map((row) => row[xKey])))
  const yValues = Array.from(new Set(data.map((row) => row[yKey])))

  options.xAxis = {
    ...options.xAxis,
    type: 'category',
    data: xValues,
  }
  options.yAxis = {
    ...options.yAxis,
    type: 'category',
    data: yValues,
  }

  const matrixData = data
    .map((row) => {
      const x = xValues.indexOf(row[xKey])
      const y = yValues.indexOf(row[yKey])
      const raw = row[valueKey]
      const value = typeof raw === 'number' ? raw : Number(raw)
      if (x < 0 || y < 0 || Number.isNaN(value)) {
        return null
      }
      return [x, y, value]
    })
    .filter((item): item is [number, number, number] => item !== null)

  const values = matrixData.map((item) => item[2])
  const minValue = values.length ? Math.min(...values) : 0
  const maxValue = values.length ? Math.max(...values) : 0

  options.visualMap = {
    ...options.visualMap,
    min: minValue,
    max: maxValue,
  }

  const series = Array.isArray(options.series) ? options.series : [{ type: 'heatmap' }]
  const baseSeries = series[0] ?? { type: 'heatmap' }
  series[0] = {
    ...baseSeries,
    type: 'heatmap',
    data: matrixData,
  }
  options.series = series
}

function applyPieMapping(
  options: Record<string, any>,
  data: DataRow[],
  mapping: FieldMapping
): void {
  // Pie chart supports two formats:
  // 1. series: [{ name: "nameKey", value: "valueKey" }] - old format
  // 2. xAxis + value - new format (more consistent with other charts)

  let nameKey: string | undefined
  let valueKey: string | undefined

  // Try to get from series (old format)
  if (Array.isArray(mapping.series) && mapping.series[0]) {
    const seriesMapping = mapping.series[0]
    if (typeof seriesMapping === 'object') {
      nameKey = seriesMapping.name
      valueKey = seriesMapping.value
    }
  }

  // Fallback to xAxis + value (new format)
  if (!nameKey || !valueKey) {
    nameKey = mapping.xAxis
    valueKey = mapping.value
  }

  if (!nameKey || !valueKey) return

  const palette = Array.isArray(options.color) && options.color.length ? options.color : chartColorBand()
  const pieSeries = Array.isArray(options.series) ? options.series : [{ type: 'pie' }]
  const slices = data.map((row, index) => {
    const color = palette[index % palette.length]
    return {
      name: sliceName(row[nameKey]),
      value: row[valueKey],
      itemStyle: { color },
      emphasis: { itemStyle: { color, opacity: 1 } },
    }
  })

  pieSeries[0] = {
    ...pieSeries[0],
    type: 'pie',
    radius: pieSeries[0]?.radius ?? ['36%', '60%'],
    avoidLabelOverlap: true,
    label: {
      formatter: (params: Record<string, any>) =>
        typeof params.percent === 'number' && params.percent >= 6 && sliceName(params.name)
          ? params.name
          : '',
    },
    labelLine: { show: true, length: 12, length2: 8 },
    data: slices,
  }

  options.legend = {
    type: 'scroll',
    bottom: 4,
    left: 'center',
    icon: 'circle',
    ...options.legend,
    data: slices.map((slice) => slice.name).filter(Boolean),
  }

  options.series = pieSeries
}

/**
 * Apply scatter chart data mapping.
 *
 * Maps field names to scatter plot dimensions:
 * - xAxis: horizontal position (required)
 * - yAxis: vertical position (required)
 * - size: bubble size (optional, uses column values)
 * - color: bubble color (optional, by category from color field)
 */
function applyScatterMapping(
  options: Record<string, any>,
  data: DataRow[],
  mapping: FieldMapping,
  displayConfig: any
): void {
  const xKey = mapping.xAxis
  const yKey = mapping.yAxis
  const sizeKey = mapping.size
  const colorKey = mapping.color

  if (!xKey || !yKey) return

  // Group data by color field if provided
  let groupedData: Record<string, DataRow[]> = {}

  if (colorKey) {
    // Group by color field
    groupedData = data.reduce(
      (acc, row) => {
        const category = row[colorKey]
        if (!acc[category]) {
          acc[category] = []
        }
        acc[category].push(row)
        return acc
      },
      {} as Record<string, DataRow[]>
    )
  } else {
    // Single series
    groupedData['default'] = data
  }

  // Compute size range for normalization
  let minSize = Infinity
  let maxSize = -Infinity

  if (sizeKey) {
    data.forEach((row) => {
      const val = Number(row[sizeKey])
      if (!isNaN(val)) {
        minSize = Math.min(minSize, val)
        maxSize = Math.max(maxSize, val)
      }
    })
  }

  // Get size range from display config or use defaults
  const [minSymbolSize, maxSymbolSize] = displayConfig?.scatter?.sizeRange ||
    displayConfig?.scatterSizeRange || [8, 20]

  // Build series for each color group
  const series = Object.entries(groupedData).map(([colorName, groupData]) => {
    return {
      type: 'scatter',
      name: colorName !== 'default' ? colorName : undefined,
      symbolSize: (params: any) => {
        // params[2] contains the size value if sizeKey is provided
        if (!sizeKey || minSize === maxSize) {
          return minSymbolSize
        }

        // Size value is stored as third element in data point
        const sizeVal = params[2]
        if (sizeVal === undefined || isNaN(sizeVal)) {
          return minSymbolSize
        }

        // Normalize to size range
        const ratio = (sizeVal - minSize) / (maxSize - minSize || 1)
        return minSymbolSize + ratio * (maxSymbolSize - minSymbolSize)
      },
      data: groupData.map((row) => {
        const sizeVal = sizeKey ? Number(row[sizeKey]) : undefined
        return [row[xKey], row[yKey], sizeVal]
      }),
    }
  })

  // Remove undefined names (from 'default' series)
  series.forEach((s) => {
    if (s.name === undefined) {
      delete s.name
    }
  })

  options.series = series

  // Determine axis types based on data
  // If X axis data contains non-numeric values, use category axis
  const xValues = data.map((row) => row[xKey])
  const hasNonNumericX = xValues.some((val) => typeof val === 'string' || isNaN(Number(val)))

  if (hasNonNumericX) {
    // Use category axis for X (e.g., dates, URLs, etc.)
    const uniqueXValues = Array.from(new Set(xValues))
    options.xAxis = {
      ...options.xAxis,
      type: 'category',
      data: uniqueXValues,
    }

    // Re-map series data to use category indices, preserving size value
    options.series = series.map((s) => ({
      ...s,
      data: s.data.map(([xVal, yVal, sizeVal]: any) => {
        const xIndex = uniqueXValues.indexOf(xVal)
        return [xIndex, yVal, sizeVal] // Keep size value as third element
      }),
    }))
  } else {
    // Use value axis for numeric X
    options.xAxis = {
      ...options.xAxis,
      type: 'value',
    }
  }

  // Y axis is always numeric for scatter
  options.yAxis = {
    ...options.yAxis,
    type: 'value',
  }
}

function cloneOptions(options: Record<string, any>): Record<string, any> {
  return JSON.parse(JSON.stringify(options))
}
