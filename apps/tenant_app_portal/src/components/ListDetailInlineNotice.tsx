import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

type Tone = 'info' | 'warn'

const toneStyles: Record<Tone, string> = {
  info: 'border-border',
  warn: 'border-amber-600/70 dark:border-amber-500/50',
}

interface Props {
  tone?: Tone
  icon?: ReactNode
  title?: ReactNode
  children?: ReactNode
  className?: string
}

/** Flat list-detail status (DESIGN §4 list detail — status bar, not a nested card). */
export default function ListDetailInlineNotice({
  tone = 'info',
  icon,
  title,
  children,
  className,
}: Props) {
  return (
    <div
      role={tone === 'warn' ? 'alert' : 'status'}
      className={cn('border-l-[3px] pl-3 text-sm leading-relaxed', toneStyles[tone], className)}
    >
      <div className="flex gap-2">
        {icon ? <span className="mt-0.5 shrink-0 [&>svg]:h-4 [&>svg]:w-4">{icon}</span> : null}
        <div className="min-w-0 space-y-1">
          {title ? <p className="font-medium text-foreground">{title}</p> : null}
          {children ? <p className="text-muted-foreground">{children}</p> : null}
        </div>
      </div>
    </div>
  )
}
