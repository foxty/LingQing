import { cn } from '@/lib/utils'
import { Building2, Database, Layers, Snowflake } from 'lucide-react'

type Props = {
  type: string
  managed?: boolean
  className?: string
}

function typeLabel(type: string): string {
  return type.replace(/_/g, ' ').toUpperCase()
}

export default function DataSourceTypeIcon({ type, managed = false, className }: Props) {
  const iconClass = cn('h-4 w-4 shrink-0 text-muted-foreground', className)

  if (managed) {
    return (
      <span className="inline-flex shrink-0" title="Platform managed">
        <Building2 className={iconClass} aria-hidden />
      </span>
    )
  }

  const Icon = type === 'snowflake' ? Snowflake : type === 'databricks' ? Layers : Database
  const label = typeLabel(type)

  return (
    <span className="inline-flex shrink-0" title={label}>
      <Icon className={iconClass} aria-hidden />
    </span>
  )
}
