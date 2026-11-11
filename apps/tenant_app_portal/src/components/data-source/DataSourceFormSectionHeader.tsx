import type { LucideIcon } from 'lucide-react'

interface DataSourceFormSectionHeaderProps {
  icon?: LucideIcon
  title: string
  description?: string
}

export default function DataSourceFormSectionHeader({
  icon: Icon,
  title,
  description,
}: DataSourceFormSectionHeaderProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        {Icon ? <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
        <h3 className="text-sm font-semibold leading-tight">{title}</h3>
      </div>
      {description ? <p className="text-xs text-muted-foreground leading-relaxed">{description}</p> : null}
    </div>
  )
}
