import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { MoreHorizontal, Search, X, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface ListDetailOverflowItem {
  label: string
  icon?: LucideIcon
  onClick: () => void
  destructive?: boolean
  hidden?: boolean
  separatorBefore?: boolean
}

export interface ListDetailPrimaryAction {
  label: string
  onClick: () => void
  icon?: LucideIcon
  hidden?: boolean
  disabled?: boolean
}

export interface ListDetailBatchAction {
  label: string
  onClick: () => void
  icon?: LucideIcon
  hidden?: boolean
  disabled?: boolean
}

interface ListDetailToolbarProps {
  searchQuery: string
  searchPlaceholder: string
  onSearchQueryChange: (value: string) => void
  onClearSearchQuery: () => void
  onSearchSubmit?: () => void
  primaryAction?: ListDetailPrimaryAction
  batchAction?: ListDetailBatchAction
  overflowItems?: ListDetailOverflowItem[]
}

export default function ListDetailToolbar({
  searchQuery,
  searchPlaceholder,
  onSearchQueryChange,
  onClearSearchQuery,
  onSearchSubmit,
  primaryAction,
  batchAction,
  overflowItems = [],
}: ListDetailToolbarProps) {
  const { t } = useTranslation()
  const visibleOverflow = overflowItems.filter((item) => !item.hidden)
  const PrimaryIcon = primaryAction?.icon
  const BatchIcon = batchAction?.icon

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:w-72">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={searchPlaceholder}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              onSearchSubmit?.()
            }
          }}
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
        {batchAction && !batchAction.hidden ? (
          <Button
            variant="outline"
            className="h-11"
            onClick={batchAction.onClick}
            disabled={batchAction.disabled}
          >
            {BatchIcon ? <BatchIcon className="w-4 h-4 mr-2" /> : null}
            {batchAction.label}
          </Button>
        ) : null}
        {primaryAction && !primaryAction.hidden ? (
          <Button className="h-11" onClick={primaryAction.onClick} disabled={primaryAction.disabled}>
            {PrimaryIcon ? <PrimaryIcon className="w-4 h-4 mr-2" /> : null}
            {primaryAction.label}
          </Button>
        ) : null}
        {visibleOverflow.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" className="h-11 w-11">
                <MoreHorizontal className="h-4 w-4" />
                <span className="sr-only">{t('common.action')}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {visibleOverflow.map((item, index) => (
                <div key={`${item.label}-${index}`}>
                  {item.separatorBefore && index > 0 ? <DropdownMenuSeparator /> : null}
                  <DropdownMenuItem
                    className={item.destructive ? 'text-destructive focus:text-destructive' : undefined}
                    onClick={item.onClick}
                  >
                    {item.icon ? <item.icon className="mr-2 h-4 w-4" /> : null}
                    {item.label}
                  </DropdownMenuItem>
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </div>
  )
}
