import '@/components/settings-users/settingsUsersTabI18n'

import { Alert, AlertDescription } from '@/components/ui/alert'
import CreateUserDialog from '@/components/settings-users/CreateUserDialog'
import DeactivateUserDialog from '@/components/settings-users/DeactivateUserDialog'
import ReactivateUserDialog from '@/components/settings-users/ReactivateUserDialog'
import ResetUserPasswordDialog from '@/components/settings-users/ResetUserPasswordDialog'
import TenantUsersTable from '@/components/settings-users/TenantUsersTable'
import {
  TENANT_USERS_PAGE_SIZE,
  TENANT_USERS_SEARCH_DEBOUNCE_MS,
  useTenantUsersListView,
} from '@/components/settings-users/tenantUsersListModel'
import SettingsListToolbar from '@/components/SettingsListToolbar'
import { EMAIL_RE, validateNewUserPasswordComplexity } from '@/components/settings-users/userFormValidation'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { useTenantUsers } from '@/hooks/useTenantUsers'
import { getApiErrorMessage, mapFastApiValidationToFields } from '@/lib/api'
import { actionRules, PERMISSIONS } from '@/lib/permissionRules'
import { tenantUsersListQueryKey } from '@/lib/tenantUsersQueryKeys'
import type { TenantUserRole } from '@/lib/tenantUsersApi'
import { listTenantUsers } from '@/lib/tenantUsersApi'
import {
  TAG_RESOURCE_TYPES,
  listTagKeys,
  listTagsForResource,
  type TagKeyDTO,
  type TagValueDTO,
} from '@/lib/tagsApi'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

export default function SettingsUsersTab() {
  const { t } = useTranslation()
  const { addUser, deactivateUser, recoverUserMembership, resetPassword, updateUserRole, setBreakGlass, mutationsPending } =
    useTenantUsers()
  const { user: currentUser, hasAny } = useAuth()
  const { showError, showSuccess } = useNotification()

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<TenantUserRole>('member')
  const [password, setPassword] = useState('')

  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [resetUserId, setResetUserId] = useState<number | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [resetPasswordFieldError, setResetPasswordFieldError] = useState<string | undefined>()
  const [resetPasswordFormError, setResetPasswordFormError] = useState<string | null>(null)

  const [deactivateDialogOpen, setDeactivateDialogOpen] = useState(false)
  const [deactivateUserId, setDeactivateUserId] = useState<number | null>(null)

  const [recoverDialogOpen, setRecoverDialogOpen] = useState(false)
  const [recoverUserId, setRecoverUserId] = useState<number | null>(null)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createFieldErrors, setCreateFieldErrors] = useState<{
    username?: string
    email?: string
    password?: string
  }>({})
  const [createFormError, setCreateFormError] = useState<string | null>(null)

  const canReadTags = hasAny(actionRules.canReadTags())
  const canManageTags = hasAny(actionRules.canManageTags())
  const canManageUsers = hasAny([PERMISSIONS.USERS_MANAGE])
  const canManageSso = hasAny([PERMISSIONS.AUTH_PROVIDERS_MANAGE])

  const [tagKeys, setTagKeys] = useState<TagKeyDTO[]>([])
  const [userTags, setUserTags] = useState<Record<number, TagValueDTO[]>>({})

  const {
    searchQuery: userListSearch,
    setSearchQuery: setUserListSearch,
    page: userListPage,
    setPage: setUserListPage,
  } = useTenantUsersListView()

  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedSearch(userListSearch.trim())
    }, TENANT_USERS_SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
  }, [userListSearch])

  useEffect(() => {
    setUserListPage(1)
  }, [debouncedSearch, setUserListPage])

  const userListQuery = useQuery({
    queryKey: [
      ...tenantUsersListQueryKey(currentUser?.tenantId),
      userListPage,
      TENANT_USERS_PAGE_SIZE,
      debouncedSearch,
    ],
    queryFn: () =>
      listTenantUsers({
        page: userListPage,
        page_size: TENANT_USERS_PAGE_SIZE,
        query: debouncedSearch || undefined,
      }),
    enabled: !!currentUser?.tenantId,
    placeholderData: (prev) => prev,
  })

  const pagedUsers = userListQuery.data?.items ?? []
  const userListTotalFiltered = userListQuery.data?.total ?? 0
  const userListTotalInTenant = userListQuery.data?.total_tenant_members ?? 0
  const userListTotalPages = userListQuery.data?.total_pages ?? 0
  const activeAdminCount = userListQuery.data?.active_admin_count ?? 0
  const listLoading = userListQuery.isFetching
  const listErrorMessage = userListQuery.error
    ? getApiErrorMessage(userListQuery.error as Error, t('settings.usersTab.listLoadError'))
    : null

  const pagedUserIdsKey = useMemo(() => pagedUsers.map((u) => u.id).join(','), [pagedUsers])

  useEffect(() => {
    if (!canReadTags) return
    listTagKeys()
      .then(setTagKeys)
      .catch(() => undefined)
  }, [canReadTags])

  useEffect(() => {
    if (!canReadTags || userListTotalFiltered === 0) {
      setUserTags({})
      return
    }
    if (!pagedUserIdsKey) {
      return
    }

    const ids = pagedUserIdsKey
      .split(',')
      .map(Number)
      .filter((id) => !Number.isNaN(id))
    if (ids.length === 0) {
      return
    }

    Promise.all(
      ids.map(async (userId) => {
        const tags = await listTagsForResource(TAG_RESOURCE_TYPES.USER, userId)
        return { userId, tags }
      })
    )
      .then((results) => {
        const next: Record<number, TagValueDTO[]> = {}
        results.forEach(({ userId, tags }) => {
          next[userId] = tags
        })
        setUserTags(next)
      })
      .catch(() => undefined)
  }, [canReadTags, pagedUserIdsKey, userListTotalFiltered])

  const loading = listLoading || mutationsPending
  /** Do not disable the search input while the list refetches — that drops focus. */
  const searchDisabled = mutationsPending

  const validateNewUserForm = useCallback((): boolean => {
    const next: { username?: string; email?: string; password?: string } = {}
    const trimmedUsername = username.trim()
    if (!trimmedUsername) {
      next.username = t('settings.usersTab.newUser.usernameRequired')
    }
    const trimmedEmail = email.trim()
    if (trimmedEmail && !EMAIL_RE.test(trimmedEmail)) {
      next.email = t('settings.usersTab.newUser.emailInvalid')
    }
    if (!password) {
      next.password = t('settings.usersTab.newUser.passwordRequired')
    } else {
      const pwdErr = validateNewUserPasswordComplexity(password, t)
      if (pwdErr) {
        next.password = pwdErr
      }
    }
    setCreateFieldErrors(next)
    return Object.keys(next).length === 0
  }, [email, password, t, username])

  const clearCreateUserFormState = useCallback(() => {
    setUsername('')
    setEmail('')
    setPassword('')
    setRole('member')
    setCreateFieldErrors({})
    setCreateFormError(null)
  }, [])

  const handleCreateUser = async () => {
    setCreateFormError(null)
    if (!validateNewUserForm()) {
      return
    }
    try {
      await addUser({
        username: username.trim(),
        password,
        role,
        email: email.trim() || undefined,
      })
      clearCreateUserFormState()
      setCreateDialogOpen(false)
      showSuccess(t('settings.usersTab.createSuccess'))
    } catch (err: any) {
      const status = err?.response?.status as number | undefined
      const detail = err?.response?.data?.detail
      const fallback = t('settings.usersTab.createFailed')

      if (status === 422 && detail) {
        const mapped = mapFastApiValidationToFields(detail, {
          username: 'username',
          password: 'password',
          email: 'email',
        })
        if (Object.keys(mapped).length > 0) {
          setCreateFieldErrors((prev) => ({ ...prev, ...mapped }))
          return
        }
      }

      if (status === 400 && typeof detail === 'string') {
        const lower = detail.toLowerCase()
        if (lower.includes('password')) {
          setCreateFieldErrors((prev) => ({ ...prev, password: detail }))
          return
        }
      }

      const msg = getApiErrorMessage(err, fallback)
      if (msg.toLowerCase().includes('password') && msg.length < 280) {
        setCreateFieldErrors((prev) => ({ ...prev, password: msg }))
        return
      }

      setCreateFormError(msg)
    }
  }

  const handleResetPassword = async () => {
    if (!resetUserId) {
      return
    }
    setResetPasswordFormError(null)
    if (!resetPasswordValue) {
      setResetPasswordFieldError(t('settings.usersTab.resetPasswordDialog.passwordRequired'))
      return
    }
    const pwdErr = validateNewUserPasswordComplexity(resetPasswordValue, t)
    if (pwdErr) {
      setResetPasswordFieldError(pwdErr)
      return
    }
    setResetPasswordFieldError(undefined)
    try {
      await resetPassword(resetUserId, resetPasswordValue)
      setResetDialogOpen(false)
      setResetPasswordValue('')
      setResetPasswordFieldError(undefined)
      setResetPasswordFormError(null)
      showSuccess(t('settings.usersTab.passwordReset'))
    } catch (err: any) {
      const status = err?.response?.status as number | undefined
      const detail = err?.response?.data?.detail
      const fallback = t('settings.usersTab.passwordResetFailed')

      if (status === 422 && detail) {
        const mapped = mapFastApiValidationToFields(detail, {
          new_password: 'password',
          password: 'password',
        })
        if (mapped.password) {
          setResetPasswordFieldError(mapped.password)
          return
        }
      }

      if (status === 400 && typeof detail === 'string' && detail.toLowerCase().includes('password')) {
        setResetPasswordFieldError(detail)
        return
      }

      const msg = getApiErrorMessage(err, fallback)
      if (msg.toLowerCase().includes('password') && msg.length < 280) {
        setResetPasswordFieldError(msg)
        return
      }
      setResetPasswordFormError(msg)
    }
  }

  const handleDeactivateUser = async () => {
    if (!deactivateUserId) {
      return
    }
    try {
      await deactivateUser(deactivateUserId)
      setDeactivateDialogOpen(false)
      showSuccess(t('settings.usersTab.userDeactivated'))
    } catch (err: any) {
      showError(getApiErrorMessage(err, t('settings.usersTab.deactivateFailed')))
    }
  }

  const handleRecoverUser = async () => {
    if (!recoverUserId) {
      return
    }
    try {
      await recoverUserMembership(recoverUserId)
      setRecoverDialogOpen(false)
      showSuccess(t('settings.usersTab.userReactivated'))
    } catch (err: any) {
      showError(getApiErrorMessage(err, t('settings.usersTab.reactivateFailed')))
    }
  }

  const deactivateBlockedReason = (userId: number, role: TenantUserRole, membershipStatus: string) => {
    if (userId === currentUser?.id) {
      return t('settings.usersTab.cannotDeactivateSelf')
    }
    if (role === 'admin' && membershipStatus !== 'inactive' && activeAdminCount <= 1) {
      return t('settings.usersTab.cannotDeactivateLastAdmin')
    }
    return null
  }

  const handleRoleChange = async (userId: number, nextRole: TenantUserRole) => {
    const targetUser = pagedUsers.find((user) => user.id === userId)
    if (!targetUser || targetUser.role === nextRole) {
      return
    }
    try {
      await updateUserRole(userId, { role: nextRole })
      showSuccess(t('settings.usersTab.roleUpdated'))
    } catch (err: any) {
      showError(getApiErrorMessage(err, t('settings.usersTab.roleUpdateFailed')))
    }
  }

  const handleBreakGlassChange = async (userId: number, next: boolean) => {
    const targetUser = pagedUsers.find((user) => user.id === userId)
    if (!targetUser || targetUser.is_break_glass === next) {
      return
    }
    try {
      await setBreakGlass(userId, next)
      showSuccess(t('settings.usersTab.breakGlassUpdated'))
    } catch (err: any) {
      showError(getApiErrorMessage(err, t('settings.usersTab.breakGlassUpdateFailed')))
    }
  }

  return (
    <SettingsPageShell>
      {listErrorMessage && (
        <Alert variant="destructive">
          <AlertDescription>{listErrorMessage}</AlertDescription>
        </Alert>
      )}

      <SettingsSection
        title={t('settings.usersTab.title')}
        description={t('settings.usersTab.description')}
        contentClassName="space-y-4 p-4 pt-0"
      >
        <SettingsListToolbar
          search={{
            query: userListSearch,
            placeholder: t('settings.usersTab.searchPlaceholder'),
            onQueryChange: setUserListSearch,
            onClear: () => setUserListSearch(''),
            disabled: searchDisabled,
          }}
          onRefresh={() => void userListQuery.refetch()}
          refreshing={loading}
          refreshLabel={t('common.refresh')}
          primaryAction={
            canManageUsers
              ? {
                  label: t('settings.usersTab.newUser.createButton'),
                  onClick: () => setCreateDialogOpen(true),
                  disabled: loading,
                }
              : undefined
          }
        />
        <TenantUsersTable
          users={pagedUsers}
          loading={loading}
          totalInTenant={userListTotalInTenant}
          totalFiltered={userListTotalFiltered}
          page={userListPage}
          totalPages={userListTotalPages}
          onPageChange={setUserListPage}
          canReadTags={canReadTags}
          canManageTags={canManageTags}
          canManageUsers={canManageUsers}
          canManageSso={canManageSso}
          tagKeys={tagKeys}
          userTags={userTags}
          activeAdminCount={activeAdminCount}
          currentUserId={currentUser?.id}
          deactivateBlockedReason={deactivateBlockedReason}
          onRoleChange={handleRoleChange}
          onBreakGlassChange={handleBreakGlassChange}
          onTagsUpdated={(resourceId, tags) =>
            setUserTags((prev) => ({
              ...prev,
              [resourceId]: tags,
            }))
          }
          onOpenReactivate={(userId) => {
            setRecoverUserId(userId)
            setRecoverDialogOpen(true)
          }}
          onOpenResetPassword={(userId) => {
            setResetUserId(userId)
            setResetPasswordValue('')
            setResetPasswordFieldError(undefined)
            setResetPasswordFormError(null)
            setResetDialogOpen(true)
          }}
          onOpenDeactivate={(userId) => {
            setDeactivateUserId(userId)
            setDeactivateDialogOpen(true)
          }}
        />
      </SettingsSection>

      <CreateUserDialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          setCreateDialogOpen(open)
          if (!open) {
            clearCreateUserFormState()
          }
        }}
        loading={loading}
        username={username}
        email={email}
        role={role}
        password={password}
        fieldErrors={createFieldErrors}
        formError={createFormError}
        onUsernameChange={(value) => {
          setUsername(value)
          setCreateFieldErrors((prev) => ({ ...prev, username: undefined }))
          setCreateFormError(null)
        }}
        onEmailChange={(value) => {
          setEmail(value)
          setCreateFieldErrors((prev) => ({ ...prev, email: undefined }))
          setCreateFormError(null)
        }}
        onRoleChange={(next) => {
          setRole(next)
          setCreateFormError(null)
        }}
        onPasswordChange={(value) => {
          setPassword(value)
          setCreateFieldErrors((prev) => ({ ...prev, password: undefined }))
          setCreateFormError(null)
        }}
        onSubmit={() => void handleCreateUser()}
      />

      <ResetUserPasswordDialog
        open={resetDialogOpen}
        onOpenChange={(open) => {
          setResetDialogOpen(open)
          if (!open) {
            setResetPasswordValue('')
            setResetPasswordFieldError(undefined)
            setResetPasswordFormError(null)
          }
        }}
        loading={loading}
        value={resetPasswordValue}
        onValueChange={(value) => {
          setResetPasswordValue(value)
          setResetPasswordFieldError(undefined)
          setResetPasswordFormError(null)
        }}
        fieldError={resetPasswordFieldError}
        formError={resetPasswordFormError}
        onSubmit={() => void handleResetPassword()}
      />

      <DeactivateUserDialog
        open={deactivateDialogOpen}
        onOpenChange={setDeactivateDialogOpen}
        loading={loading}
        onConfirm={() => void handleDeactivateUser()}
      />

      <ReactivateUserDialog
        open={recoverDialogOpen}
        onOpenChange={setRecoverDialogOpen}
        loading={loading}
        onConfirm={() => void handleRecoverUser()}
      />
    </SettingsPageShell>
  )
}
