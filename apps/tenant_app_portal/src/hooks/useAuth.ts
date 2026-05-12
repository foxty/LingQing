import { createContext, createElement, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { User, ApiUser, convertApiUserToUser } from '@/types'
import { getCurrentUserProfile, updateCurrentUserPreferences } from '@/lib/authApi'

interface AuthContextValue {
  user: User | null
  permissions: string[]
  loading: boolean
  login: (userData: User, token: string, perms?: string[]) => void
  logout: () => void
  refreshPermissions: () => Promise<void>
  hasPermission: (permission: string) => boolean
  hasAny: (perms: string[]) => boolean
  hasAll: (perms: string[]) => boolean
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [permissions, setPermissions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  // Load stored user and permissions on app init
  useEffect(() => {
    const storedUser = localStorage.getItem('user')
    const storedPermissions = localStorage.getItem('permissions')
    if (storedUser) {
      try {
        const parsedUser = JSON.parse(storedUser) as ApiUser
        setUser(convertApiUserToUser(parsedUser))
        if (storedPermissions) {
          setPermissions(JSON.parse(storedPermissions))
        }
      } catch (error) {
        console.error('Failed to parse stored user:', error)
        localStorage.removeItem('user')
        localStorage.removeItem('permissions')
      }
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) return

    const syncFromProfile = async () => {
      try {
        const profile = await getCurrentUserProfile()
        setPermissions(profile.permissions)
        localStorage.setItem('permissions', JSON.stringify(profile.permissions))

        if (!profile.preferences?.timezone_iana) {
          const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
          if (browserTimezone) {
            await updateCurrentUserPreferences({ timezone_iana: browserTimezone })
          }
        }
      } catch (error) {
        console.error('Failed to refresh profile on bootstrap:', error)
      }
    }

    void syncFromProfile()
  }, [])

  const login = (userData: User, token: string, perms: string[] = []) => {
    setUser(userData)
    setPermissions(perms)
    // Store in API format for consistency with backend
    const apiUser: ApiUser = {
      id: userData.id,
      username: userData.username,
      role: userData.role,
      tenant_id: userData.tenantId,
      tenant_name: userData.tenantName,
    }
    localStorage.setItem('user', JSON.stringify(apiUser))
    localStorage.setItem('token', token)
    localStorage.setItem('permissions', JSON.stringify(perms))
  }

  const logout = () => {
    setUser(null)
    setPermissions([])
    localStorage.removeItem('user')
    localStorage.removeItem('token')
    localStorage.removeItem('permissions')

    // Clear all thread history for security
    Object.keys(localStorage)
      .filter((key) => key.startsWith('thread_'))
      .forEach((key) => localStorage.removeItem(key))
  }

  // Load permissions from backend after login
  const refreshPermissions = async () => {
    try {
      const profile = await getCurrentUserProfile()
      setPermissions(profile.permissions)
      localStorage.setItem('permissions', JSON.stringify(profile.permissions))
      if (!profile.preferences?.timezone_iana) {
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
        if (browserTimezone) {
          await updateCurrentUserPreferences({ timezone_iana: browserTimezone })
        }
      }
    } catch (error) {
      console.error('Failed to refresh permissions:', error)
    }
  }

  // Permission checkers
  const hasPermission = (permission: string): boolean => {
    return permissions.includes(permission)
  }

  const hasAny = (perms: string[]): boolean => {
    return perms.some((p) => permissions.includes(p))
  }

  const hasAll = (perms: string[]): boolean => {
    return perms.every((p) => permissions.includes(p))
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      permissions,
      loading,
      login,
      logout,
      refreshPermissions,
      hasPermission,
      hasAny,
      hasAll,
    }),
    [user, permissions, loading]
  )

  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
