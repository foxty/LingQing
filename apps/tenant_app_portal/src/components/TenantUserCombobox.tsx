import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronsUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { searchTenantUserDirectory, type TenantUserDirectoryEntry } from '@/lib/tenantUserDirectoryApi'

export interface TenantUserComboboxProps {
  id?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  disabled?: boolean
  placeholder: string
  searchPlaceholder: string
  searchingLabel: string
  emptyLabel: string
  excludeUserIds?: number[]
  selectedUserId: number | null
  selectedUsername: string
  onSelect: (user: TenantUserDirectoryEntry) => void
  onSearchError?: (message: string) => void
}

export default function TenantUserCombobox({
  id,
  open,
  onOpenChange,
  disabled,
  placeholder,
  searchPlaceholder,
  searchingLabel,
  emptyLabel,
  excludeUserIds = [],
  selectedUserId,
  selectedUsername,
  onSelect,
  onSearchError,
}: TenantUserComboboxProps) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<TenantUserDirectoryEntry[]>([])

  const excludeKey = useMemo(() => excludeUserIds.slice().sort((a, b) => a - b).join(','), [excludeUserIds])

  useEffect(() => {
    if (!open || disabled) {
      return
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true)
        try {
          const rows = await searchTenantUserDirectory({
            q: query,
            limit: 20,
            exclude_user_ids: excludeUserIds.length > 0 ? excludeUserIds : undefined,
          })
          setResults(rows)
        } catch (error: unknown) {
          setResults([])
          const detail =
            error &&
            typeof error === 'object' &&
            'response' in error &&
            error.response &&
            typeof error.response === 'object' &&
            'data' in error.response &&
            error.response.data &&
            typeof error.response.data === 'object' &&
            'detail' in error.response.data
              ? String((error.response.data as { detail: unknown }).detail)
              : undefined
          onSearchError?.(detail ?? 'Failed to load users')
        } finally {
          setLoading(false)
        }
      })()
    }, 250)
    return () => window.clearTimeout(timer)
    // excludeKey tracks excludeUserIds; onSearchError intentionally omitted (unstable caller refs)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- excludeKey encodes excludeUserIds
  }, [open, disabled, query, excludeKey])

  const triggerLabel = useMemo(() => {
    if (selectedUsername) {
      return selectedUsername
    }
    const matched = results.find((row) => row.user_id === selectedUserId)
    return matched?.username ?? ''
  }, [results, selectedUserId, selectedUsername])

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between font-normal"
        >
          <span className="truncate">{triggerLabel || placeholder}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <div className="border-b p-2">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={searchPlaceholder}
            autoFocus
          />
        </div>
        <div className="max-h-64 overflow-y-auto p-1">
          {loading ? (
            <div className="px-2 py-6 text-sm text-muted-foreground">{searchingLabel}</div>
          ) : results.length === 0 ? (
            <div className="px-2 py-6 text-sm text-muted-foreground">{emptyLabel}</div>
          ) : (
            results.map((row) => {
              const isSelected = selectedUserId === row.user_id
              return (
                <button
                  key={row.user_id}
                  type="button"
                  className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                  onClick={() => {
                    onSelect(row)
                    onOpenChange(false)
                  }}
                >
                  <span className="truncate">{row.username}</span>
                  {isSelected && <Check className="ml-2 h-4 w-4 shrink-0" />}
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
