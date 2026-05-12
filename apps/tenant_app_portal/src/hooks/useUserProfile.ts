import { useState } from 'react'
import { toast } from 'sonner'
import {
  getCurrentUserProfile,
  changePassword,
  updateCurrentUserPreferences,
  ProfileResponse,
  ChangePasswordData,
} from '@/lib/authApi'
import i18n from '@/i18n/config'

export function useUserProfile() {
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
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch profile'
      setError(errorMsg)
      toast.error(errorMsg)
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
      toast.success(i18n.t('common.updateSuccess'))
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to change password'
      setError(errorMsg)
      toast.error(errorMsg)
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
      toast.success(i18n.t('common.updateSuccess'))
      return data
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update timezone'
      setError(errorMsg)
      toast.error(errorMsg)
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
