import { useState, useEffect } from 'react'

export type SendKeyPreference = 'enter' | 'ctrl-enter'

interface UserPreferences {
  sendKey: SendKeyPreference
  lastAgentId: number
}

const DEFAULT_PREFERENCES: UserPreferences = {
  sendKey: 'enter',
  lastAgentId: -1,
}

const STORAGE_KEY = 'user_preferences'

export function useUserPreferences() {
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_PREFERENCES)

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as UserPreferences
        setPreferences({ ...DEFAULT_PREFERENCES, ...parsed })
      } catch (error) {
        console.error('Failed to parse user preferences:', error)
      }
    }
  }, [])

  const updatePreferences = (updates: Partial<UserPreferences>) => {
    const newPreferences = { ...preferences, ...updates }
    setPreferences(newPreferences)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newPreferences))
  }

  return {
    preferences,
    updatePreferences,
  }
}

