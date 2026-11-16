import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { formatInstant, type FormatInstantOptions } from '@/lib/dateTime'
import { usePreferredDateTimeFormat, usePreferredTimezone } from '@/hooks/useCurrentUserProfile'

export function useUserDateTimeFormatOptions(): Pick<
  FormatInstantOptions,
  'locale' | 'timeZone' | 'formatId'
> {
  const { i18n } = useTranslation()
  const timeZone = usePreferredTimezone()
  const formatId = usePreferredDateTimeFormat()
  return useMemo(
    () => ({
      locale: i18n.language,
      timeZone,
      formatId,
    }),
    [formatId, i18n.language, timeZone]
  )
}

/** Format timestamps using the signed-in user's profile timezone and date/time format. */
export function useFormatUserDateTime() {
  const base = useUserDateTimeFormatOptions()
  return useCallback(
    (
      value: Parameters<typeof formatInstant>[0],
      options?: Omit<FormatInstantOptions, 'locale' | 'timeZone' | 'formatId'>
    ) => formatInstant(value, { ...base, ...options }),
    [base]
  )
}