import { useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import SearchableCombobox from '@/components/SearchableCombobox'

export interface UserSearchResult {
  id: number
  username: string
}

export interface UserSearchComboboxProps {
  value: number | undefined
  onChange: (userId: number | undefined, username?: string) => void
  searchUsers: (query: string) => Promise<UserSearchResult[]>
  placeholder: string
  searchPlaceholder: string
  emptyMessage: string
  clearLabel: string
  className?: string
  disabled?: boolean
}

export default function UserSearchCombobox({
  value,
  onChange,
  searchUsers,
  placeholder,
  searchPlaceholder,
  emptyMessage,
  clearLabel,
  className,
  disabled = false,
}: UserSearchComboboxProps) {
  const { t } = useTranslation()

  const lastMatches = useRef<Map<string, string>>(new Map())

  const searchOptions = useCallback(
    async (query: string) => {
      const rows = await searchUsers(query)
      const opts = rows.map((u) => {
        lastMatches.current.set(String(u.id), u.username)
        return { value: String(u.id), label: u.username }
      })
      return opts
    },
    [searchUsers]
  )

  return (
    <SearchableCombobox
      className={className}
      value={value != null ? String(value) : ''}
      onChange={(next) => {
        if (!next) {
          onChange(undefined)
          return
        }
        const id = Number(next)
        if (!Number.isFinite(id)) {
          onChange(undefined)
          return
        }
        onChange(id, lastMatches.current.get(next))
      }}
      searchOptions={searchOptions}
      placeholder={placeholder}
      searchPlaceholder={searchPlaceholder}
      emptyMessage={emptyMessage}
      clearLabel={clearLabel}
      loadingMessage={t('common.loading')}
      disabled={disabled}
    />
  )
}