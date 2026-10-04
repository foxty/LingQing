import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Plus, RefreshCw, Search, X, type LucideIcon } from 'lucide-react'

export interface SettingsListPrimaryAction {
  label: string
  onClick: () => void
  icon?: LucideIcon
  hidden?: boolean
  disabled?: boolean
}

interface SettingsListToolbarSearch {
  query: string
  placeholder: string
  onQueryChange: (value: string) => void
  onClear: () => void
}

interface SettingsListToolbarProps {
  search?: SettingsListToolbarSearch
  onRefresh?: () => void
  refreshing?: boolean
  refreshLabel?: string
  primaryAction?: SettingsListPrimaryAction
  className?: string
}

/** In-card toolbar for searchable Settings record lists. Lives inside SettingsSection body. */
export default function SettingsListToolbar({
  search,
  onRefresh,
  refreshing = false,
  refreshLabel,
  primaryAction,
  className,
}: SettingsListToolbarProps) {
  const PrimaryIcon = primaryAction?.icon ?? Plus

  return (
    <div className={`flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between ${className ?? ''}`}>
      {search ? (
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={search.placeholder}
            value={search.query}
            onChange={(e) => search.onQueryChange(e.target.value)}
            className="h-9 pl-8"
          />
          {search.query ? (
            <Button
              variant="ghost"
              size="sm"
              className="absolute right-1 top-1 h-7 w-7 p-0"
              onClick={search.onClear}
            >
              <X className="h-3 w-3" />
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="flex-1" />
      )}

      <div className="flex shrink-0 items-center justify-end gap-2">
        {onRefresh && refreshLabel ? (
          <Button variant="outline" className="h-11" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshLabel}
          </Button>
        ) : null}
        {primaryAction && !primaryAction.hidden ? (
          <Button
            className="h-11"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            <PrimaryIcon className="mr-2 h-4 w-4" />
            {primaryAction.label}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
