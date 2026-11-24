import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Plus, RefreshCw, Search, X, type LucideIcon } from 'lucide-react'

export interface ListIndexPrimaryAction {
  label: string
  onClick: () => void
  icon?: LucideIcon
  hidden?: boolean
  disabled?: boolean
}

interface ListIndexToolbarProps {
  searchQuery: string
  searchPlaceholder: string
  onSearchQueryChange: (value: string) => void
  onClearSearchQuery: () => void
  onRefresh: () => void
  refreshing?: boolean
  refreshLabel: string
  /** Outline peer actions before the solid primary (e.g. Install Pack). */
  secondaryActions?: ListIndexPrimaryAction[]
  primaryAction?: ListIndexPrimaryAction
}

export default function ListIndexToolbar({
  searchQuery,
  searchPlaceholder,
  onSearchQueryChange,
  onClearSearchQuery,
  onRefresh,
  refreshing = false,
  refreshLabel,
  secondaryActions = [],
  primaryAction,
}: ListIndexToolbarProps) {
  const PrimaryIcon = primaryAction?.icon ?? Plus
  const visibleSecondary = secondaryActions.filter((action) => !action.hidden)

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:w-72">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={searchPlaceholder}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          className="pl-8 h-9"
        />
        {searchQuery ? (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-1 top-1 h-7 w-7 p-0"
            onClick={onClearSearchQuery}
          >
            <X className="h-3 w-3" />
          </Button>
        ) : null}
      </div>

      <div className="flex items-center justify-end gap-2 shrink-0">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshLabel}
        </Button>
        {visibleSecondary.map((action) => {
          const Icon = action.icon
          return (
            <Button
              key={action.label}
              type="button"
              variant="outline"
              size="sm"
              onClick={action.onClick}
              disabled={action.disabled}
            >
              {Icon ? <Icon className="w-4 h-4 mr-2" /> : null}
              {action.label}
            </Button>
          )
        })}
        {primaryAction && !primaryAction.hidden ? (
          <Button size="sm" onClick={primaryAction.onClick} disabled={primaryAction.disabled}>
            <PrimaryIcon className="w-4 h-4 mr-2" />
            {primaryAction.label}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
