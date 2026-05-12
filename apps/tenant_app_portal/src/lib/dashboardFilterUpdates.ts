import type { DashboardFilter, DashboardFilterValueOverride, DashboardWidget } from '@/lib/dashboardApi'

export const FILTER_VALUE_PERSIST_DEBOUNCE_MS = 400

const IMPLICIT_TIME_FILTER_PATTERN = /\$time_filter\s*\(\s*[^:]/

export function getDatasourceOptionsSourceKey(filters: DashboardFilter[]): string {
  return filters
    .filter((filter) => filter.type === 'dropdown_datasource')
    .map((filter) => `${filter.id}\0${filter.dataSourceId ?? ''}\0${filter.optionsQuery ?? ''}`)
    .join('|')
}

export function getDatasourceOptionFilterIds(filters: DashboardFilter[]): string[] {
  return filters.filter((filter) => filter.type === 'dropdown_datasource').map((filter) => filter.id)
}

export function widgetUsesFilter(query: string | undefined, filter: DashboardFilter): boolean {
  if (!query) {
    return false
  }

  const paramKey = filter.paramKey
  if (paramKey) {
    const tokens =
      filter.type === 'time_range'
        ? [
            `:${paramKey}`,
            `:start_${paramKey}`,
            `:end_${paramKey}`,
            `:${paramKey}_start`,
            `:${paramKey}_end`,
          ]
        : [`:${paramKey}`]
    if (tokens.some((token) => query.includes(token))) {
      return true
    }
  }

  return filter.type === 'time_range' && IMPLICIT_TIME_FILTER_PATTERN.test(query)
}

export function getWidgetFilterSignature(
  widget: Pick<DashboardWidget, 'query'>,
  filters: DashboardFilter[]
): string {
  const used = filters.filter((filter) => widgetUsesFilter(widget.query, filter))
  if (used.length === 0) {
    return ''
  }
  return JSON.stringify(used.map((filter) => [filter.id, filter.paramKey ?? '', filter.value ?? null]))
}

export function toFilterValueOverrides(filters: DashboardFilter[]): DashboardFilterValueOverride[] {
  return filters.map((filter) => ({
    id: filter.id,
    paramKey: filter.paramKey,
    value: filter.value,
  }))
}

export function isValueOnlyFilterChange(
  previous: DashboardFilter,
  next: DashboardFilter
): boolean {
  if (previous.id !== next.id) {
    return false
  }
  return (
    serializeFilterWithoutValue(previous) === serializeFilterWithoutValue(next) &&
    JSON.stringify(previous.value) !== JSON.stringify(next.value)
  )
}

export function collectValueOnlyFilterUpdates(
  previousFilters: DashboardFilter[],
  nextFilters: DashboardFilter[],
  newFilterId?: string | null
): Array<{ id: string; value: DashboardFilter['value'] }> {
  const updates: Array<{ id: string; value: DashboardFilter['value'] }> = []

  for (const nextFilter of nextFilters) {
    if (newFilterId && nextFilter.id === newFilterId) {
      continue
    }
    const previousFilter = previousFilters.find((filter) => filter.id === nextFilter.id)
    if (!previousFilter || !isValueOnlyFilterChange(previousFilter, nextFilter)) {
      continue
    }
    updates.push({ id: nextFilter.id, value: nextFilter.value })
  }

  return updates
}

function serializeFilterWithoutValue(filter: DashboardFilter): string {
  const rest = { ...filter }
  delete rest.value
  return JSON.stringify(rest)
}
