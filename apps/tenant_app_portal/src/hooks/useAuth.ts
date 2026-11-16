import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { User, ApiUser, convertApiUserToUser } from '@/types'
import {
  currentUserProfileQueryKey,
  fetchCurrentUserProfile,
  hasAuthSession,
  useCurrentUserProfile,
} from '@/hooks/useCurrentUserProfile'

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

function applyProfilePermissions(permissions: string[]) {
  localStorage.setItem('permissions', JSON.stringify(permissions))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [permissions, setPermissions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const { data: profile } = useCurrentUserProfile({ enabled: hasAuthSession() })

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
    if (!profile) return
    setPermissions(profile.permissions)
    applyProfilePermissions(profile.permissions)
  }, [profile])

  const login = (userData: User, token: string, perms: string[] = []) => {
    setUser(userData)
    setPermissions(perms)
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
    queryClient.removeQueries({ queryKey: currentUserProfileQueryKey })

    Object.keys(localStorage)
      .filter((key) => key.startsWith('thread_'))
      .forEach((key) => localStorage.removeItem(key))
  }

  const refreshPermissions = async () => {
    try {
      const nextProfile = await fetchCurrentUserProfile(queryClient)
      setPermissions(nextProfile.permissions)
      applyProfilePermissions(nextProfile.permissions)
    } catch (error) {
      console.error('Failed to refresh permissions:', error)
    }
  }

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