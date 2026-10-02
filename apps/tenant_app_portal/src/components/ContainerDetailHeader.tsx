import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'

interface ContainerDetailHeaderProps {
  parentLabel: string
  onParentNavigate: () => void
  title: string
  meta?: ReactNode
}

export default function ContainerDetailHeader({
  parentLabel,
  onParentNavigate,
  title,
  meta,
}: ContainerDetailHeaderProps) {
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

      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl font-semibold truncate">{title}</h1>
        {meta ? <div className="text-sm text-muted-foreground">{meta}</div> : null}
      </div>
    </div>
  )
}
