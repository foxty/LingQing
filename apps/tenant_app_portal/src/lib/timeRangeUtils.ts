export type TimePrecision = 'date' | 'datetime'

/** Value shape for {@link TimeRangePicker} and dashboard filters. */
export interface TimeRangeValue {
  mode?: 'relative' | 'absolute'
  preset?: string
  start?: string
  end?: string
}

export function normalizeForPrecision(
  value: string | undefined,
  precision: TimePrecision
): string | undefined {
  if (!value) return value
  if (precision === 'date') return value.split('T')[0]
  if (value.includes('T')) return value.slice(0, 16)
  return `${value}T00:00`
}

export function normalizeTimeRangeValue(
  value: any,
  precision: TimePrecision
): TimeRangeValue | undefined {
  if (!value || typeof value !== 'object') {
    return {}
  }

  if (value.mode !== 'absolute') {
    return { ...value }
  }

  if (precision === 'date') {
    return {
      ...value,
      start: normalizeForPrecision(value.start, 'date'),
      end: normalizeForPrecision(value.end, 'date'),
    }
  }

  return {
    ...value,
    start: normalizeForPrecision(value.start, 'datetime'),
    end: normalizeForPrecision(value.end, 'datetime'),
  }
}

const MS_PER_DAY = 86_400_000

function startOfLocalDay(date: Date): Date {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

function endOfLocalDay(date: Date): Date {
  const copy = new Date(date)
  copy.setHours(23, 59, 59, 999)
  return copy
}

function parseAbsoluteBound(raw: string, bound: 'start' | 'end', precision: TimePrecision): Date | undefined {
  if (!raw) return undefined
  if (precision === 'date' || !raw.includes('T')) {
    const day = new Date(`${raw.split('T')[0]}T00:00:00`)
    if (Number.isNaN(day.getTime())) return undefined
    return bound === 'start' ? startOfLocalDay(day) : endOfLocalDay(day)
  }
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return undefined
  return parsed
}

function resolveRelativePreset(preset: string, now: Date): [Date, Date] | undefined {
  switch (preset) {
    case 'today':
      return [startOfLocalDay(now), now]
    case 'yesterday': {
      const day = new Date(now)
      day.setDate(day.getDate() - 1)
      const start = startOfLocalDay(day)
      const end = new Date(start)
      end.setDate(end.getDate() + 1)
      return [start, end]
    }
    case 'last_7_days':
      return [new Date(now.getTime() - 7 * MS_PER_DAY), now]
    case 'last_30_days':
      return [new Date(now.getTime() - 30 * MS_PER_DAY), now]
    case 'this_month': {
      const start = new Date(now.getFullYear(), now.getMonth(), 1)
      return [startOfLocalDay(start), now]
    }
    case 'last_month': {
      const firstThisMonth = new Date(now.getFullYear(), now.getMonth(), 1)
      const lastMonthEnd = new Date(firstThisMonth.getTime() - MS_PER_DAY)
      const start = new Date(lastMonthEnd.getFullYear(), lastMonthEnd.getMonth(), 1)
      return [startOfLocalDay(start), firstThisMonth]
    }
    case 'this_year': {
      const start = new Date(now.getFullYear(), 0, 1)
      return [startOfLocalDay(start), now]
    }
    default:
      return undefined
  }
}

/** Map TimeRangePicker value to API ``from`` / ``to`` ISO strings (audit, exports, etc.). */
export function resolveTimeRangeToIsoBounds(
  value: TimeRangeValue | null | undefined,
  precision: TimePrecision = 'datetime'
): { from?: string; to?: string } {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const now = new Date()

  if (value.mode === 'relative' && value.preset) {
    const range = resolveRelativePreset(value.preset, now)
    if (!range) return {}
    const [start, end] = range
    return { from: start.toISOString(), to: end.toISOString() }
  }

  if (value.mode === 'absolute' && value.start && value.end) {
    const start = parseAbsoluteBound(value.start, 'start', precision)
    const end = parseAbsoluteBound(value.end, 'end', precision)
    if (!start || !end) return {}
    return { from: start.toISOString(), to: end.toISOString() }
  }

  return {}
}

/** Default token-usage filter (matches legacy 30-day window). */
export const DEFAULT_USAGE_TIME_RANGE: TimeRangeValue = {
  mode: 'relative',
  preset: 'last_30_days',
}

export function formatTimeRangeSummary(
  value: TimeRangeValue | null | undefined,
  precision: TimePrecision,
  t: (key: string) => string
): string {
  if (!value) return t('components.timeRangePicker.selectTimeRange')
  if (value.mode === 'relative' && value.preset) {
    const labelKey = `components.timeRangePicker.${value.preset}`
    const label = t(labelKey)
    return label !== labelKey ? label : t('components.timeRangePicker.selectTimeRange')
  }
  if (value.mode === 'absolute' && (value.start || value.end)) {
    const start =
      normalizeForPrecision(value.start, precision) ?? t('components.timeRangePicker.start').split(' ')[0]
    const end =
      normalizeForPrecision(value.end, precision) ?? t('components.timeRangePicker.end').split(' ')[0]
    return `${start} ~ ${end}`
  }
  return t('components.timeRangePicker.selectTimeRange')
}

export function usageTimeRangeBounds(value: TimeRangeValue | null | undefined): {
  start_time?: string
  end_time?: string
} {
  const resolved = value ?? DEFAULT_USAGE_TIME_RANGE
  const { from, to } = resolveTimeRangeToIsoBounds(resolved, 'datetime')
  return { start_time: from, end_time: to }
}
