import type { ReactNode } from 'react'

interface PageStatsActionBarProps {
  stats: ReactNode
  actions?: ReactNode
  className?: string
  statsClassName?: string
  actionsClassName?: string
}

export default function PageStatsActionBar({
  stats,
  actions,
  className,
  statsClassName,
  actionsClassName,
}: PageStatsActionBarProps) {
  return (
    <div
      className={`flex items-center justify-between gap-3 p-4 bg-muted/50 rounded-lg border ${className ?? ''}`}
    >
      <div className={`flex items-center gap-6 flex-wrap ${statsClassName ?? ''}`}>{stats}</div>
      {actions ? (
        <div className={`flex items-center gap-2 flex-wrap justify-end ${actionsClassName ?? ''}`}>
          {actions}
        </div>
      ) : null}
    </div>
  )
}
