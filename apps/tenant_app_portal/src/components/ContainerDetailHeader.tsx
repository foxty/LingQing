import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronRight, MoreHorizontal, RefreshCw, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export interface ContainerOverflowItem {
  label: string
  icon?: LucideIcon
  onClick: () => void
  destructive?: boolean
  hidden?: boolean
  separatorBefore?: boolean
}

interface ContainerDetailHeaderProps {
  parentLabel: string
  onParentNavigate: () => void
  title: string
  meta?: ReactNode
  primaryAction?: ReactNode
  overflowItems?: ContainerOverflowItem[]
  onRefresh?: () => void
  refreshing?: boolean
  trailingActions?: ReactNode
}

export default function ContainerDetailHeader({
  parentLabel,
  onParentNavigate,
  title,
  meta,
  primaryAction,
  overflowItems,
  onRefresh,
  refreshing,
  trailingActions,
}: ContainerDetailHeaderProps) {
  const { t } = useTranslation()
  const visibleOverflow = (overflowItems ?? []).filter((item) => !item.hidden)

  return (
    <div className="space-y-3">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted-foreground">
        <button
          type="button"
          onClick={onParentNavigate}
          className="hover:text-foreground transition-colors"
        >
          {parentLabel}
        </button>
        <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="truncate text-foreground">{title}</span>
      </nav>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold truncate">{title}</h1>
          {meta ? <div className="text-sm text-muted-foreground">{meta}</div> : null}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {trailingActions}
          {primaryAction}
          {onRefresh ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              onClick={onRefresh}
              disabled={refreshing}
              title={t('common.refresh')}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          ) : null}
          {visibleOverflow.length > 0 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-9 w-9">
                  <MoreHorizontal className="h-4 w-4" />
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
    </div>
  )
}
