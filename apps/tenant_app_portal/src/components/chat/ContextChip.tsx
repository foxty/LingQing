/**
 * Context Chip Component
 * Displays a selected resource as a removable chip in the chat input area.
 */

import { Button } from '@/components/ui/button'
import { ContextResource } from '@/types'
import {
  BarChart3,
  FileText,
  Database,
  Clock,
  AppWindow,
  X,
  FileSpreadsheet,
} from 'lucide-react'

interface ContextChipProps {
  resource: ContextResource
  onRemove?: () => void
  readOnly?: boolean
  variant?: 'input' | 'message'
}

const RESOURCE_TYPE_CONFIG: Record<string, { icon: React.ReactNode }> = {
  document: { icon: <FileText className="w-3 h-3" /> },
  dashboard: { icon: <BarChart3 className="w-3 h-3" /> },
  report: { icon: <FileSpreadsheet className="w-3 h-3" /> },
  scheduled_task: { icon: <Clock className="w-3 h-3" /> },
  app: { icon: <AppWindow className="w-3 h-3" /> },
  asset: { icon: <Database className="w-3 h-3" /> },
}

export default function ContextChip({
  resource,
  onRemove,
  readOnly = false,
  variant = 'input',
}: ContextChipProps) {
  const config = RESOURCE_TYPE_CONFIG[resource.resource_type] ?? {
    icon: <FileText className="w-3 h-3" />,
  }

  const displayTitle = resource.subtitle
    ? `${resource.title} (${resource.subtitle})`
    : resource.title

  const chipClassName =
    variant === 'message'
      ? 'inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-md border border-primary-foreground/25 bg-primary-foreground/15 text-primary-foreground shrink-0'
      : 'inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-md border border-border bg-secondary text-foreground shrink-0'

  return (
    <span className={chipClassName}>
      {config.icon}
      <span className="truncate max-w-[160px]">{displayTitle}</span>
      {!readOnly && onRemove && (
        <Button
          variant="ghost"
          size="icon"
          className="h-4 w-4 p-0 hover:bg-transparent -ml-1 -mr-1"
          onClick={onRemove}
        >
          <X className="w-3 h-3" />
        </Button>
      )}
    </span>
  )
}
