/**
 * Hooks for tenant settings management
 */

import { useState } from 'react'
import {
  getTenantSettings,
  updateTenantSettings,
  getAvailableModels,
  TenantSettings,
  ModelProviderGroup,
} from '@/lib/tenantApi'

export function useTenantSettings() {
  const [settings, setSettings] = useState<TenantSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchSettings = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTenantSettings()
      setSettings(data)
      return data
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to fetch settings'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const saveSettings = async (newSettings: TenantSettings) => {
    setLoading(true)
    setError(null)
    try {
      const data = await updateTenantSettings(newSettings)
      setSettings(data)
      return data
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to update settings'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  return {
    settings,
    loading,
    error,
    fetchSettings,
    saveSettings,
  }
}

export function useAvailableModels() {
  const [modelGroups, setModelGroups] = useState<ModelProviderGroup[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchModels = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAvailableModels()
      setModelGroups(data)
      return data
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Failed to fetch models'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  return {
    modelGroups,
    models: modelGroups.flatMap((group) => group.models),
    loading,
    error,
    fetchModels,
  }
}
