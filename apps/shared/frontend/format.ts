/** Locale-aware number, rate, duration, and date-range helpers shared across portals. */

export function formatNumber(value: number, locale?: string): string {
  return new Intl.NumberFormat(locale).format(value)
}

export function formatRate(numerator: number, denominator: number): string {
  if (denominator <= 0) {
    return '—'
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`
}

export function formatDurationMs(value: number | null | undefined): string {
  if (value == null) {
    return '—'
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`
  }
  return `${(value / 1000).toFixed(1)}s`
}

export function buildRelativeIsoRange(days: number): { start_time: string; end_time: string } {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - days)
  return {
    start_time: start.toISOString(),
    end_time: end.toISOString(),
  }
}
