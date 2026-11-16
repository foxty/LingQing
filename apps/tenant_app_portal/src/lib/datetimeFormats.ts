export const DATETIME_FORMAT_IDS = [
  'locale',
  'ymd_hms_24',
  'ymd_hms_12',
  'ymd',
  'mdy_hm_12',
] as const

export type DateTimeFormatId = (typeof DATETIME_FORMAT_IDS)[number]

export const DEFAULT_DATETIME_FORMAT: DateTimeFormatId = 'locale'

export function isDateTimeFormatId(value: string): value is DateTimeFormatId {
  return (DATETIME_FORMAT_IDS as readonly string[]).includes(value)
}

export function resolveDateTimeFormat(preferred?: string | null): DateTimeFormatId {
  if (preferred && isDateTimeFormatId(preferred)) {
    return preferred
  }
  return DEFAULT_DATETIME_FORMAT
}