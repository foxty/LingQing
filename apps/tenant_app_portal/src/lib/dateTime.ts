export type DatePrecision = 'date' | 'time' | 'datetime'

export interface FormatDateOptions {
  locale?: string
  precision?: DatePrecision
  fallback?: string
  hour12?: boolean
}

export function formatDate(
  value: string | Date | null | undefined,
  options: FormatDateOptions = {}
): string {
  const { locale = 'zh-CN', precision = 'datetime', fallback = '—', hour12 } = options
  if (!value) return fallback

  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return fallback

  if (precision === 'date') {
    return date.toLocaleDateString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  }

  if (precision === 'time') {
    return date.toLocaleTimeString(locale, {
      hour: '2-digit',
      minute: '2-digit',
      hour12,
    })
  }

  return date.toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12,
  })
}
