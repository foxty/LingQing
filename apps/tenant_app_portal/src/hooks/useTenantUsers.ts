import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import {
  createTenantUser,
  deactivateTenantUser,
  listTenantUsers,
  recoverTenantUser,
  resetTenantUserPassword,
  updateTenantUserRole,
  type TenantUser,
  type TenantUserCreateRequest,
  type TenantUserUpdateRequest,
} from '@/lib/tenantUsersApi'
import { setUserBreakGlass } from '@/lib/ssoApi'
import { useAuth } from './useAuth'

export function useTenantUsersList() {
  const { user } = useAuth()

  return useQuery({
    queryKey: ['tenant-users', user?.tenantId],
    queryFn: listTenantUsers,
    enabled: !!user,
    retry: 1,
  })
}

export function useTenantUsers() {
  const [users, setUsers] = useState<TenantUser[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await listTenantUsers()
      setUsers(response)
      return response
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to fetch users'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const addUser = useCallback(async (payload: TenantUserCreateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const created = await createTenantUser(payload)
      setUsers((prev) => [...prev, created])
      return created
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to create user'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const deactivateUser = useCallback(async (userId: number) => {
    setLoading(true)
    setError(null)
    try {
      await deactivateTenantUser(userId)
      setUsers((prev) =>
        prev.map((user) =>
          user.id === userId
            ? {
                ...user,
                membership_status: 'inactive',
              }
            : user
        )
      )
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to deactivate user'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const recoverUserMembership = useCallback(async (userId: number) => {
    setLoading(true)
    setError(null)
    try {
      await recoverTenantUser(userId)
      setUsers((prev) =>
        prev.map((user) =>
          user.id === userId
            ? {
                ...user,
                membership_status: 'active',
              }
            : user
        )
      )
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to recover user'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const resetPassword = useCallback(async (userId: number, newPassword: string) => {
    setLoading(true)
    setError(null)
    try {
      await resetTenantUserPassword(userId, { new_password: newPassword })
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to reset password'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const updateUserRole = useCallback(async (userId: number, payload: TenantUserUpdateRequest) => {
    setLoading(true)
    setError(null)
    try {
      const updated = await updateTenantUserRole(userId, payload)
      setUsers((prev) => prev.map((user) => (user.id === userId ? updated : user)))
      return updated
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update user role'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const setBreakGlass = useCallback(async (userId: number, isBreakGlass: boolean) => {
    setLoading(true)
    setError(null)
    try {
      await setUserBreakGlass(userId, isBreakGlass)
      setUsers((prev) =>
        prev.map((user) => (user.id === userId ? { ...user, is_break_glass: isBreakGlass } : user))
      )
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Failed to update break-glass'
      setError(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    users,
    loading,
    error,
    fetchUsers,
    addUser,
    deactivateUser,
    recoverUserMembership,
    resetPassword,
    updateUserRole,
    setBreakGlass,
  }
}
