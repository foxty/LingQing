import { useState } from 'react'
import {
  getCurrentUserProfile,
  changePassword,
  updateCurrentUserPreferences,
  ProfileResponse,
  ChangePasswordData,
} from '@/lib/authApi'
import { getApiErrorMessage } from '@/lib/api'
import { useNotification } from '@/hooks/useNotification'
import i18n from '@/i18n/config'

export function useUserProfile() {
  const { showSuccess } = useNotification()
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchProfile = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getCurrentUserProfile()
      setProfile(data)
      return data
    } catch (err: unknown) {
      const errorMsg = getApiErrorMessage(err, i18n.t('userProfile.loadFailed'))
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const handleChangePassword = async (data: ChangePasswordData) => {
    setLoading(true)
    setError(null)
    try {
      await changePassword(data)
      showSuccess(i18n.t('common.updateSuccess'))
    } catch (err: unknown) {
      const errorMsg = getApiErrorMessage(err, i18n.t('userProfile.passwordChangeFailed'))
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateTimezone = async (timezoneIana: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await updateCurrentUserPreferences({ timezone_iana: timezoneIana })
      setProfile(data)
      showSuccess(i18n.t('common.updateSuccess'))
      return data
    } catch (err: unknown) {
      const errorMsg = getApiErrorMessage(err, i18n.t('userProfile.timezoneUpdateFailed'))
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }

  return {
    profile,
    loading,
    error,
    fetchProfile,
    handleChangePassword,
    handleUpdateTimezone,
  }
}
