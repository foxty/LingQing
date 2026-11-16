/** Shown when the search box is empty (full IANA list still searchable). */
export const TIMEZONE_QUICK_PICKS = [
  'UTC',
  'Asia/Hong_Kong',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Asia/Seoul',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Australia/Sydney',
  'Pacific/Auckland',
] as const

const FALLBACK_TIMEZONE_IDS: string[] = [...TIMEZONE_QUICK_PICKS]

let cachedAllTimeZones: string[] | null = null

export function getAllIanaTimeZones(): string[] {
  if (cachedAllTimeZones) {
    return cachedAllTimeZones
  }
  const supportedValuesOf = (
    Intl as typeof Intl & { supportedValuesOf?: (key: 'timeZone') => string[] }
  ).supportedValuesOf
  if (typeof supportedValuesOf === 'function') {
    try {
      cachedAllTimeZones = [...supportedValuesOf('timeZone')].sort()
      return cachedAllTimeZones
    } catch {
      /* fall through */
    }
  }
  cachedAllTimeZones = [...FALLBACK_TIMEZONE_IDS]
  return cachedAllTimeZones
}

export function isValidIanaTimeZone(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) {
    return false
  }
  try {
    Intl.DateTimeFormat(undefined, { timeZone: trimmed })
    return true
  } catch {
    return false
  }
}

const SEARCH_RESULT_LIMIT = 80

export function filterIanaTimeZones(
  query: string,
  selectedValue?: string,
  allZones: string[] = getAllIanaTimeZones()
): string[] {
  const normalized = query.trim().toLowerCase()
  if (!normalized) {
    const quick = new Set<string>(TIMEZONE_QUICK_PICKS)
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (browserTz) {
      quick.add(browserTz)
    }
    if (selectedValue?.trim()) {
      quick.add(selectedValue.trim())
    }
    return Array.from(quick).sort()
  }

  return allZones.filter((tz) => tz.toLowerCase().includes(normalized)).slice(0, SEARCH_RESULT_LIMIT)
}