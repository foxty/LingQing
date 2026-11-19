import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import UserSearchCombobox from '@/components/UserSearchCombobox'
import { listAclShareCandidates, type AclShareResourceType } from '@/lib/aclSharesApi'

interface AclShareUserComboboxProps {
  resourceType: AclShareResourceType
  resourceId: number
  value: number | undefined
  onChange: (userId: number | undefined, username?: string) => void
  disabled?: boolean
  className?: string
}

/** User picker for ACL share dialog — resource-scoped candidates API. */
export default function AclShareUserCombobox({
  resourceType,
  resourceId,
  value,
  onChange,
  disabled = false,
  className,
}: AclShareUserComboboxProps) {
  const { t } = useTranslation()

  const searchUsers = useCallback(
    async (query: string) => {
      const rows = await listAclShareCandidates(resourceType, resourceId, { q: query, limit: 20 })
      return rows.map((c) => ({ id: c.id, username: c.username }))
    },
    [resourceId, resourceType]
  )

  return (
    <UserSearchCombobox
      className={className}
      value={value}
      onChange={onChange}
      searchUsers={searchUsers}
      disabled={disabled}
      placeholder={t('components.shareDialog.addPeoplePlaceholder')}
      searchPlaceholder={t('components.shareDialog.searchPlaceholder')}
      emptyMessage={t('components.shareDialog.noUsersFound')}
      clearLabel={t('components.shareDialog.clearSelection')}
    />
  )
}