import {
  queryOptions,
  useQuery,
  type QueryClient,
} from '@tanstack/react-query'
import {
  getCurrentUserProfile,
  updateCurrentUserPreferences,
  type ProfileResponse,
} from '@/lib/authApi'
import { resolveTimeZone } from '@/lib/dateTime'
import { resolveDateTimeFormat, type DateTimeFormatId } from '@/lib/datetimeFormats'

export const currentUserProfileQueryKey = ['currentUserProfile'] as const

export async function loadCurrentUserProfile(): Promise<ProfileResponse> {
  const profile = await getCurrentUserProfile()
  if (!profile.preferences?.timezone_iana) {
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (browserTimezone) {
      return updateCurrentUserPreferences({ timezone_iana: browserTimezone })
    }
  }
  return profile
}

export function currentUserProfileQueryOptions() {
  return queryOptions({
    queryKey: currentUserProfileQueryKey,
    queryFn: loadCurrentUserProfile,
    staleTime: 5 * 60 * 1000,
  })
}

export function hasAuthSession(): boolean {
  return Boolean(localStorage.getItem('token'))
}

export function useCurrentUserProfile(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? hasAuthSession()
  return useQuery({
    ...currentUserProfileQueryOptions(),
    enabled,
  })
}

export function usePreferredTimezone(): string {
  const { data } = useCurrentUserProfile()
  return resolveTimeZone(data?.preferences?.timezone_iana)
}

export function usePreferredDateTimeFormat(): DateTimeFormatId {
  const { data } = useCurrentUserProfile()
  return resolveDateTimeFormat(data?.preferences?.datetime_format)
}

export async function fetchCurrentUserProfile(queryClient: QueryClient): Promise<ProfileResponse> {
  return queryClient.fetchQuery(currentUserProfileQueryOptions())
}