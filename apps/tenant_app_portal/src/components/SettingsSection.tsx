import type { ReactNode } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface SettingsSectionProps {
  title: string
  description?: string
  action?: ReactNode
  children?: ReactNode
  className?: string
  contentClassName?: string
}

export default function SettingsSection({
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: SettingsSectionProps) {
  return (
    <Card className={cn('overflow-hidden shadow-sm', className)}>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 gap-4 p-4 pb-3">
        <div className="min-w-0 space-y-1">
          <CardTitle className="text-lg tracking-tight">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
      </CardHeader>
      {children != null ? (
        <CardContent className={cn('p-4 pt-0', contentClassName)}>{children}</CardContent>
      ) : null}
    </Card>
  )
}
