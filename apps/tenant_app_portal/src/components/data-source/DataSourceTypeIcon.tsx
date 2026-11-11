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
  if (managed) {
    return (
      <Building2
        className={cn('h-4 w-4 shrink-0 text-muted-foreground', className)}
        aria-label={typeLabel('platform')}
        title="Platform managed"
      />
    )
  }

  const Icon = type === 'snowflake' ? Snowflake : type === 'databricks' ? Layers : Database

  return (
    <Icon
      className={cn('h-4 w-4 shrink-0 text-muted-foreground', className)}
      aria-label={typeLabel(type)}
      title={typeLabel(type)}
    />
  )
}
