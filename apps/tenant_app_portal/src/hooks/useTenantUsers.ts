import { useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { tenantUsersListQueryKey } from '@/lib/tenantUsersQueryKeys'
import {
  createTenantUser,
  deactivateTenantUser,
  recoverTenantUser,
  resetTenantUserPassword,
  updateTenantUserRole,
  type TenantUser,
  type TenantUserCreateRequest,
  type TenantUserListResponse,
  type TenantUserUpdateRequest,
} from '@/lib/tenantUsersApi'
import { setUserBreakGlass } from '@/lib/ssoApi'
import { useAuth } from './useAuth'

function applyRowPatchToResponsePages(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: number | undefined,
  userId: number,
  patch: Partial<TenantUser>
) {
  queryClient.setQueriesData<TenantUserListResponse>(
    { queryKey: tenantUsersListQueryKey(tenantId), exact: false },
    (old) => {
      if (!old?.items?.length) {
        return old
      }
      const idx = old.items.findIndex((u) => u.id === userId)
      if (idx < 0) {
        return old
      }
      const nextItems = [...old.items]
      nextItems[idx] = { ...nextItems[idx], ...patch }
      return { ...old, items: nextItems }
    }
  )
}

export function useTenantUsers() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const tenantId = user?.tenantId

  const invalidateTenantUsers = useCallback(() => {
    return queryClient.invalidateQueries({ queryKey: tenantUsersListQueryKey(tenantId) })
  }, [queryClient, tenantId])

  const fetchUsers = useCallback(() => {
    return queryClient.refetchQueries({ queryKey: tenantUsersListQueryKey(tenantId) })
  }, [queryClient, tenantId])

  const addUserMutation = useMutation({
    mutationFn: createTenantUser,
    onSuccess: () => invalidateTenantUsers(),
  })

  const deactivateUserMutation = useMutation({
    mutationFn: deactivateTenantUser,
    onSuccess: (_, userId) => {
      applyRowPatchToResponsePages(queryClient, tenantId, userId, { membership_status: 'inactive' })
      invalidateTenantUsers()
    },
  })

  const recoverUserMutation = useMutation({
    mutationFn: recoverTenantUser,
    onSuccess: (_, userId) => {
      applyRowPatchToResponsePages(queryClient, tenantId, userId, { membership_status: 'active' })
      invalidateTenantUsers()
    },
  })

  const resetPasswordMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: { new_password: string } }) =>
      resetTenantUserPassword(userId, payload),
  })

  const updateUserRoleMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: TenantUserUpdateRequest }) =>
      updateTenantUserRole(userId, payload),
    onSuccess: (updated) => {
      applyRowPatchToResponsePages(queryClient, tenantId, updated.id, updated)
      invalidateTenantUsers()
    },
  })

  const setBreakGlassMutation = useMutation({
    mutationFn: ({ userId, isBreakGlass }: { userId: number; isBreakGlass: boolean }) =>
      setUserBreakGlass(userId, isBreakGlass),
    onSuccess: (_, { userId, isBreakGlass }) => {
      applyRowPatchToResponsePages(queryClient, tenantId, userId, { is_break_glass: isBreakGlass })
      invalidateTenantUsers()
    },
  })

  const addUser = useCallback(
    async (payload: TenantUserCreateRequest) => addUserMutation.mutateAsync(payload),
    [addUserMutation]
  )

  const deactivateUser = useCallback(
    async (userId: number) => deactivateUserMutation.mutateAsync(userId),
    [deactivateUserMutation]
  )

  const recoverUserMembership = useCallback(
    async (userId: number) => recoverUserMutation.mutateAsync(userId),
    [recoverUserMutation]
  )

  const resetPassword = useCallback(
    async (userId: number, newPassword: string) =>
      resetPasswordMutation.mutateAsync({ userId, payload: { new_password: newPassword } }),
    [resetPasswordMutation]
  )

  const updateUserRole = useCallback(
    async (userId: number, payload: TenantUserUpdateRequest) =>
      updateUserRoleMutation.mutateAsync({ userId, payload }),
    [updateUserRoleMutation]
  )

  const setBreakGlass = useCallback(
    async (userId: number, isBreakGlass: boolean) =>
      setBreakGlassMutation.mutateAsync({ userId, isBreakGlass }),
    [setBreakGlassMutation]
  )

  const mutationsPending =
    addUserMutation.isPending ||
    deactivateUserMutation.isPending ||
    recoverUserMutation.isPending ||
    resetPasswordMutation.isPending ||
    updateUserRoleMutation.isPending ||
    setBreakGlassMutation.isPending

  return {
    fetchUsers,
    addUser,
    deactivateUser,
    recoverUserMembership,
    resetPassword,
    updateUserRole,
    setBreakGlass,
    mutationsPending,
  }
}
