import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import UserSearchCombobox from '@/components/UserSearchCombobox'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/hooks/useAuth'
import { listTenantUsers } from '@/lib/tenantUsersApi'
import { PERMISSIONS } from '@/lib/permissionRules'

export interface TenantUserFilterComboboxLabels {
  placeholder: string
  searchPlaceholder: string
  emptyMessage: string
  clearLabel: string
  numericFallbackPlaceholder?: string
}

interface TenantUserFilterComboboxProps {
  value: number | undefined
  onChange: (userId: number | undefined, username?: string) => void
  className?: string
  labels?: Partial<TenantUserFilterComboboxLabels>
}

export default function TenantUserFilterCombobox({
  value,
  onChange,
  className,
  labels,
}: TenantUserFilterComboboxProps) {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const canListUsers = hasAny([
    PERMISSIONS.TENANT_ADMIN,
    PERMISSIONS.TENANT_SETTINGS_READ,
    PERMISSIONS.USERS_MANAGE,
  ])

  const searchUsers = useCallback(async (query: string) => {
    const res = await listTenantUsers({
      page: 1,
      page_size: 20,
      query: query.trim() || undefined,
    })
    return res.items.map((u) => ({ id: u.id, username: u.username }))
  }, [])

  const resolvedLabels: TenantUserFilterComboboxLabels = {
    placeholder: labels?.placeholder ?? t('auditLogs.actorUserPlaceholder'),
    searchPlaceholder: labels?.searchPlaceholder ?? t('auditLogs.actorUserSearch'),
    emptyMessage: labels?.emptyMessage ?? t('auditLogs.actorUserEmpty'),
    clearLabel: labels?.clearLabel ?? t('auditLogs.clearActor'),
    numericFallbackPlaceholder: labels?.numericFallbackPlaceholder ?? t('auditLogs.actorUserId'),
  }

  if (!canListUsers) {
    return (
      <Input
        className={className}
        placeholder={resolvedLabels.numericFallbackPlaceholder}
        value={value != null ? String(value) : ''}
        onChange={(e) => {
          const raw = e.target.value.trim()
          if (!raw) {
            onChange(undefined)
            return
          }
          const parsed = Number(raw)
          onChange(Number.isFinite(parsed) ? parsed : undefined)
        }}
      />
    )
  }

  return (
    <UserSearchCombobox
      className={className}
      value={value}
      onChange={onChange}
      searchUsers={searchUsers}
      placeholder={resolvedLabels.placeholder}
      searchPlaceholder={resolvedLabels.searchPlaceholder}
      emptyMessage={resolvedLabels.emptyMessage}
      clearLabel={resolvedLabels.clearLabel}
    />
  )
}