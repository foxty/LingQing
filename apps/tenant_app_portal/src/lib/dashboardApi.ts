import api from './api'

export interface ChartDisplayConfig {
  title?: string
  xLabel?: string
  yLabel?: string
  seriesLabels?: Record<string, string>
  showLegend?: boolean
  legendPosition?: 'top' | 'bottom' | 'left' | 'right'
  metricFormat?: 'number' | 'currency' | 'percent'
  description?: string
  // Scatter chart specific display configuration
  scatter?: ScatterDisplayConfig
  // Gauge chart specific display configuration
  gauge?: GaugeDisplayConfig
  // Table widget specific display configuration
  table?: TableDisplayConfig
}

export interface TableValueFormat {
  formatType?: 'string' | 'number' | 'currency' | 'percent' | 'datetime' | 'boolean'
  precision?: number
  currency?: string
  dateFormat?: string
  prefix?: string
  suffix?: string
  nullDisplay?: string
  trueLabel?: string
  falseLabel?: string
}

export interface TableColumnConfig {
  field: string
  label?: string
  align?: 'left' | 'center' | 'right'
  width?: number
  minWidth?: number
  maxWidth?: number
  format?: TableValueFormat
}

export interface TableDisplayConfig {
  columns?: TableColumnConfig[]
  defaultFormat?: TableValueFormat
  showHeader?: boolean
  showRowNumbers?: boolean
  zebraStripes?: boolean
  compact?: boolean
}

export interface ScatterDisplayConfig {
  sizeRange?: [number, number]
  colorScaleType?: 'linear' | 'ordinal' | 'log'
  colorRange?: [string, string]
}

export interface GaugeDisplayConfig {
  minValue?: number
  maxValue?: number
  unit?: string
  thresholds?: Array<[number, string]>
  startAngle?: number
  endAngle?: number
  showDetail?: boolean
  showAxisLabel?: boolean
}

export interface DashboardConfig {
  layout: {
    type: string
    cols: number
    rows: number
    gap: number
    rowHeight?: number
  }
  widgets: DashboardWidget[]
  filters?: DashboardFilter[]
}

export interface DashboardWidget {
  id: string
  type: 'chart' | 'table' | 'metric' | 'filter' | 'text'
  position: { x: number; y: number; w: number; h: number }
  chartType?:
    | 'line'
    | 'bar'
    | 'area'
    | 'pie'
    | 'scatter'
    | 'heatmap'
    | 'stacked_bar'
    | 'grouped_bar'
    | 'multi_line'
    | 'multi_area'
    | 'gauge'
  // Domain-level display config
  displayConfig?: ChartDisplayConfig
  // UI-level render overrides
  options?: Record<string, any>
  // Data binding fields (integrated)
  dataSourceId?: number
  query?: string
  fieldMapping?: FieldMapping
}

export interface DashboardFilterOption {
  label: string
  value: any
}

export interface DashboardFilterOptionsResult {
  options: DashboardFilterOption[]
  hasError: boolean
  errorMessage?: string | null
}

export type DashboardFilterType = 'time_range' | 'dropdown_static' | 'dropdown_datasource'

export type DashboardFilterOperator =
  | '='
  | '!='
  | '>'
  | '>='
  | '<'
  | '<='
  | 'in'
  | 'between'
  | 'like'
  | 'ilike'

export interface DashboardFilter {
  id: string
  name: string
  type: DashboardFilterType
  paramKey?: string
  value?: any
  dataSourceId?: number
  optionsQuery?: string
  options?: DashboardFilterOption[]
  allowMultiple?: boolean
  timePrecision?: 'date' | 'datetime'
  description?: string
  required?: boolean
}

export interface QueryPreviewColumn {
  name: string
  type: string
}

export interface QueryPreviewResult {
  columns: QueryPreviewColumn[]
  rows: Array<Record<string, any>>
}

export interface FieldMapping {
  xAxis?: string
  yAxis?: string
  series?: string[] | Array<{ name: string; value: string }>
  value?: string
  size?: string
  color?: string
}

export interface Dashboard {
  id: number
  tenant_id: number
  name: string
  description?: string
  config: DashboardConfig
  owner_id: number
  created_at: string
  updated_at: string
}

export interface DashboardListItem {
  id: number
  tenant_id: number
  name: string
  description?: string | null
  owner_id: number
  owner_username?: string | null
  created_at: string
  updated_at: string
}

export interface DashboardBaseUpdatePayload {
  title?: string
  description?: string
  layout?: DashboardConfig['layout']
}

export interface DashboardWidgetCreatePayload {
  type: DashboardWidget['type']
  chartType?: DashboardWidget['chartType']
  position: DashboardWidget['position']
  dataSourceId?: number
  query?: string
  fieldMapping?: FieldMapping
  displayConfig?: ChartDisplayConfig
}

export interface DashboardWidgetUpdatePayload {
  chartType?: DashboardWidget['chartType']
  position?: DashboardWidget['position']
  dataSourceId?: number
  query?: string
  fieldMapping?: FieldMapping
  displayConfig?: ChartDisplayConfig
}

export interface DashboardFilterCreatePayload {
  name: string
  type: DashboardFilter['type']
  paramKey?: string
  value?: any
  dataSourceId?: number
  optionsQuery?: string
  options?: DashboardFilterOption[]
  allowMultiple?: boolean
  timePrecision?: DashboardFilter['timePrecision']
  description?: string
  required?: boolean
}

export interface DashboardFilterUpdatePayload {
  name?: string
  type?: DashboardFilter['type']
  paramKey?: string
  value?: any
  dataSourceId?: number
  optionsQuery?: string
  options?: DashboardFilterOption[]
  allowMultiple?: boolean
  timePrecision?: DashboardFilter['timePrecision']
  description?: string
  required?: boolean
}

export async function getDashboard(id: number): Promise<Dashboard> {
  const res = await api.get<Dashboard>(`/dashboards/${id}`)
  return res.data
}

export async function listDashboards(): Promise<DashboardListItem[]> {
  const res = await api.get<DashboardListItem[]>('/dashboards')
  return res.data
}

export async function updateDashboard(
  id: number,
  dto: DashboardBaseUpdatePayload
): Promise<Dashboard> {
  const res = await api.put<Dashboard>(`/dashboards/${id}`, dto)
  return res.data
}

export async function deleteDashboard(id: number): Promise<void> {
  await api.delete(`/dashboards/${id}`)
}

export async function createDashboardWidget(
  dashboardId: number,
  dto: DashboardWidgetCreatePayload
): Promise<DashboardWidget> {
  const res = await api.post<DashboardWidget>(`/dashboards/${dashboardId}/widgets`, dto)
  return res.data
}

export async function updateDashboardWidget(
  dashboardId: number,
  widgetId: string,
  dto: DashboardWidgetUpdatePayload
): Promise<DashboardWidget> {
  const res = await api.patch<DashboardWidget>(
    `/dashboards/${dashboardId}/widgets/${widgetId}`,
    dto
  )
  return res.data
}

export async function removeDashboardWidget(
  dashboardId: number,
  widgetId: string
): Promise<Dashboard> {
  const res = await api.delete<Dashboard>(`/dashboards/${dashboardId}/widgets/${widgetId}`)
  return res.data
}

export async function createDashboardFilter(
  dashboardId: number,
  dto: DashboardFilterCreatePayload
): Promise<DashboardFilter> {
  const res = await api.post<DashboardFilter>(`/dashboards/${dashboardId}/filters`, dto)
  return res.data
}

export async function updateDashboardFilter(
  dashboardId: number,
  filterId: string,
  dto: DashboardFilterUpdatePayload
): Promise<DashboardFilter> {
  const res = await api.patch<DashboardFilter>(
    `/dashboards/${dashboardId}/filters/${filterId}`,
    dto
  )
  return res.data
}

export async function removeDashboardFilter(
  dashboardId: number,
  filterId: string
): Promise<Dashboard> {
  const res = await api.delete<Dashboard>(`/dashboards/${dashboardId}/filters/${filterId}`)
  return res.data
}

export interface DashboardFilterValueOverride {
  id: string
  paramKey?: string
  value?: any
}

export async function queryWidgetData(
  dashboardId: number,
  widgetId: string,
  options?: {
    filters?: DashboardFilterValueOverride[]
  }
): Promise<Array<Record<string, any>>> {
  const res = await api.post(
    `/dashboards/${dashboardId}/widgets/${widgetId}/query-data`,
    options?.filters ? { filters: options.filters } : undefined
  )
  return res.data.data ?? []
}

export async function queryDashboardSqlPreview(
  dashboardId: number,
  options: {
    dataSourceId: number
    query: string
    limit?: number
  }
): Promise<QueryPreviewResult> {
  const res = await api.post(`/dashboards/${dashboardId}/widgets/query-preview`, {
    data_source_id: options.dataSourceId,
    query: options.query,
    limit: options.limit ?? 50,
  })
  return res.data
}

export async function queryWidgetPreview(
  dashboardId: number,
  widgetId: string,
  options?: {
    limit?: number
    query?: string | null
    dataSourceId?: number | null
  }
): Promise<QueryPreviewResult> {
  const res = await api.post(`/dashboards/${dashboardId}/widgets/${widgetId}/query-preview`, {
    limit: options?.limit ?? 50,
    query: options?.query ?? undefined,
    data_source_id: options?.dataSourceId ?? undefined,
  })
  return res.data
}

export async function getDashboardFilterOptions(
  dashboardId: number,
  filterId: string
): Promise<DashboardFilterOptionsResult> {
  const res = await api.get(`/dashboards/${dashboardId}/filters/${filterId}/options`)
  return {
    options: res.data.options ?? [],
    hasError: Boolean(res.data.has_error),
    errorMessage: res.data.error_message ?? null,
  }
}

export interface DataSourceOption {
  id: number
  name: string
  type: string
  description?: string
}

export async function listDataSources(): Promise<DataSourceOption[]> {
  const res = await api.get('/data-sources')
  return res.data
}
