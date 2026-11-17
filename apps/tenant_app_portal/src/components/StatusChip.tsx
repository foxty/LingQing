import { Badge } from '@/components/ui/badge'
import { statusChipHeaderClass, statusChipTableClass } from '@/lib/uiControlPatterns'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

type StatusChipVariant = 'default' | 'secondary' | 'destructive' | 'outline'

export function StatusChip({
  variant,
  size,
  icon,
  children,
  className,
}: {
  variant: StatusChipVariant
  size: 'table' | 'header'
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  const sizeClass = size === 'table' ? statusChipTableClass : statusChipHeaderClass
  return (
    <Badge variant={variant} className={cn(sizeClass, className)}>
      {icon}
      {children}
    </Badge>
  )
}