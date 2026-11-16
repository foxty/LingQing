import {
  DEFAULT_DATETIME_FORMAT,
  type DateTimeFormatId,
  resolveDateTimeFormat,
} from '@/lib/datetimeFormats'

export type DatePrecision = 'date' | 'time' | 'datetime'

export interface FormatInstantOptions {
  locale?: string
  timeZone?: string | null
  formatId?: DateTimeFormatId | string | null
  fallback?: string
  precision?: DatePrecision
}

export function resolveTimeZone(preferred?: string | null): string {
  const trimmed = preferred?.trim()
  if (trimmed) {
    try {
      Intl.DateTimeFormat(undefined, { timeZone: trimmed })
      return trimmed
    } catch {
      /* invalid IANA — fall back */
    }
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

function parseDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date
}

function ymdInZone(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export function calendarDateKey(date: Date, timeZone: string): string {
  return ymdInZone(date, timeZone)
}

function formatLocaleInstant(
  date: Date,
  locale: string,
  timeZone: string | undefined,
  precision: DatePrecision,
  hour12?: boolean
): string {
  const zoneFields = timeZone ? { timeZone } : {}
  if (precision === 'date') {
    return date.toLocaleDateString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      ...zoneFields,
    })
  }
  if (precision === 'time') {
    return date.toLocaleTimeString(locale, {
      hour: '2-digit',
      minute: '2-digit',
      hour12,
      ...zoneFields,
    })
  }
  return date.toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12,
    ...zoneFields,
  })
}

function formatWithPreset(
  date: Date,
  formatId: DateTimeFormatId,
  timeZone: string,
  locale: string,
  precision: DatePrecision
): string {
  if (precision === 'date' || formatId === 'ymd') {
    if (formatId === 'mdy_hm_12') {
      return new Intl.DateTimeFormat('en-US', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(date)
    }
    return ymdInZone(date, timeZone)
  }

  if (precision === 'time') {
    return formatChatTimePart(date, formatId, timeZone, locale)
  }

  switch (formatId) {
    case 'ymd_hms_24': {
      return `${ymdInZone(date, timeZone)} ${formatChatTimePart(date, formatId, timeZone, locale)}`
    }
    case 'ymd_hms_12': {
      const time = new Intl.DateTimeFormat('en-US', {
        timeZone,
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      }).format(date)
      return `${ymdInZone(date, timeZone)} ${time}`
    }
    case 'mdy_hm_12': {
      return new Intl.DateTimeFormat('en-US', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      }).format(date)
    }
    case 'locale':
    default:
      return formatLocaleInstant(date, locale, timeZone, precision)
  }
}

/** Format one instant using the user's display format and timezone. */
export function formatInstant(
  value: string | Date | null | undefined,
  options: FormatInstantOptions = {}
): string {
  const {
    locale = 'zh-CN',
    fallback = '—',
    precision = 'datetime',
    timeZone: timeZoneOpt,
    formatId: formatIdOpt,
  } = options

  const date = parseDate(value)
  if (!date) return fallback

  const formatId = resolveDateTimeFormat(formatIdOpt ?? DEFAULT_DATETIME_FORMAT)
  const timeZone = timeZoneOpt ? resolveTimeZone(timeZoneOpt) : resolveTimeZone(null)

  if (formatId === 'locale') {
    return formatLocaleInstant(date, locale, timeZone, precision)
  }

  return formatWithPreset(date, formatId, timeZone, locale, precision)
}

function formatChatTimePart(
  date: Date,
  formatId: DateTimeFormatId,
  timeZone: string,
  locale?: string
): string {
  if (formatId === 'ymd_hms_12' || formatId === 'mdy_hm_12') {
    const useSeconds = formatId === 'ymd_hms_12'
    return new Intl.DateTimeFormat(locale || 'en-US', {
      timeZone,
      hour: 'numeric',
      minute: '2-digit',
      second: useSeconds ? '2-digit' : undefined,
      hour12: true,
    }).format(date)
  }

  if (formatId === 'ymd' || formatId === 'locale') {
    return new Intl.DateTimeFormat(locale, {
      timeZone,
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date)
  }

  return new Intl.DateTimeFormat(locale, {
    timeZone,
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

export interface FormatChatTimestampOptions {
  timeZone?: string | null
  locale?: string
  fallback?: string
  formatId?: DateTimeFormatId | string | null
}

/** Chat turn timestamps: time-only for today in the user's zone; full format otherwise. */
export function formatChatTimestamp(
  value: string | Date | null | undefined,
  options: FormatChatTimestampOptions = {}
): string {
  const { locale, fallback = '', formatId: formatIdOpt } = options
  const date = parseDate(value)
  if (!date) return fallback

  const timeZone = resolveTimeZone(options.timeZone)
  const formatId = resolveDateTimeFormat(formatIdOpt ?? DEFAULT_DATETIME_FORMAT)
  const isToday = calendarDateKey(date, timeZone) === calendarDateKey(new Date(), timeZone)

  if (isToday) {
    return formatChatTimePart(date, formatId, timeZone, locale)
  }

  return formatInstant(date, {
    locale,
    timeZone,
    formatId,
    precision: 'datetime',
    fallback,
  })
}