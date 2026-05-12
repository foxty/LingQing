import type { DashboardFilter } from '@/lib/dashboardApi'

const PRESET_KEYS = new Set([
  'today',
  'yesterday',
  'last_7_days',
  'last_30_days',
  'this_month',
  'last_month',
  'this_year',
])

export function getDashboardPeriodFilter(filters: DashboardFilter[]): DashboardFilter | undefined {
  return filters.find((filter) => filter.type === 'time_range' && filter.value)
}

export function getDashboardPeriodLabel(
  filters: DashboardFilter[],
  translatePreset: (preset: string) => string
): string | null {
  const filter = getDashboardPeriodFilter(filters)
  if (!filter?.value) return null

  const preset = typeof filter.value.preset === 'string' ? filter.value.preset : null
  if (preset && PRESET_KEYS.has(preset)) {
    return translatePreset(preset)
  }

  const start = typeof filter.value.start === 'string' ? filter.value.start : null
  const end = typeof filter.value.end === 'string' ? filter.value.end : null
  if (start && end) {
    return `${start} – ${end}`
  }

  return null
}
