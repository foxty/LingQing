import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  changePassword,
  updateCurrentUserPreferences,
  type ChangePasswordData,
  type ProfileResponse,
  type UpdateProfilePreferencesRequest,
} from '@/lib/authApi'
import { getApiErrorMessage } from '@/lib/api'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'
import {
  currentUserProfileQueryKey,
  useCurrentUserProfile,
} from '@/hooks/useCurrentUserProfile'
import { isValidIanaTimeZone } from '@/lib/timezones'
import { isDateTimeFormatId } from '@/lib/datetimeFormats'

export {
  useCurrentUserProfile,
  usePreferredTimezone,
  usePreferredDateTimeFormat,
} from '@/hooks/useCurrentUserProfile'
export { useFormatUserDateTime, useUserDateTimeFormatOptions } from '@/hooks/useUserDateTimeFormat'

export function useUserProfile() {
  const queryClient = useQueryClient()
  const { showSuccess } = useNotification()
  const { data: profile, isLoading, isFetching, error, refetch } = useCurrentUserProfile()

  const passwordMutation = useMutation({
    mutationFn: (data: ChangePasswordData) => changePassword(data),
    onSuccess: () => {
      showSuccess(i18n.t('common.updateSuccess'))
    },
  })

  const preferencesMutation = useMutation({
    mutationFn: (payload: UpdateProfilePreferencesRequest) => updateCurrentUserPreferences(payload),
    onSuccess: (data: ProfileResponse) => {
      queryClient.setQueryData(currentUserProfileQueryKey, data)
      showSuccess(i18n.t('common.updateSuccess'))
    },
  })

  const fetchProfile = () => refetch()

  const handleChangePassword = async (data: ChangePasswordData) => {
    try {
      await passwordMutation.mutateAsync(data)
    } catch (err: unknown) {
      const errorMsg = getApiErrorMessage(err, i18n.t('userProfile.passwordChangeFailed'))
      throw new Error(errorMsg)
    }
  }

  const handleUpdateDateTimePreferences = async (payload: {
    timezone_iana: string
    datetime_format: string
  }) => {
    if (!isValidIanaTimeZone(payload.timezone_iana)) {
      throw new Error(i18n.t('userProfile.timezoneInvalid'))
    }
    if (!isDateTimeFormatId(payload.datetime_format)) {
      throw new Error(i18n.t('userProfile.dateTimeFormatInvalid'))
    }
    try {
      return await preferencesMutation.mutateAsync({
        timezone_iana: payload.timezone_iana.trim(),
        datetime_format: payload.datetime_format,
      })
    } catch (err: unknown) {
      const errorMsg = getApiErrorMessage(err, i18n.t('userProfile.dateTimeUpdateFailed'))
      throw new Error(errorMsg)
    }
  }

  const loading =
    isLoading || isFetching || passwordMutation.isPending || preferencesMutation.isPending

  const errorMessage = error
    ? getApiErrorMessage(error, i18n.t('userProfile.loadFailed'))
    : passwordMutation.error
      ? getApiErrorMessage(passwordMutation.error, i18n.t('userProfile.passwordChangeFailed'))
      : preferencesMutation.error
        ? getApiErrorMessage(preferencesMutation.error, i18n.t('userProfile.dateTimeUpdateFailed'))
        : null

  return {
    profile: profile ?? null,
    loading,
    error: errorMessage,
    fetchProfile,
    handleChangePassword,
    handleUpdateDateTimePreferences,
  }
}