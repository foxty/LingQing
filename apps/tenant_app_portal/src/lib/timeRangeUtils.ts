export type TimePrecision = 'date' | 'datetime'

export interface TimeRangeValueLike {
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
): TimeRangeValueLike | undefined {
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
