import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { PipelineBadgeState } from '@/lib/documentPipelineStatus'
import { formatDate } from '@/lib/dateTime'
import { useTranslation } from 'react-i18next'

const STATE_STYLES: Record<
  PipelineBadgeState,
  { text: string; bg: string; border: string; dot: string }
> = {
  ready: {
    text: 'text-success',
    bg: 'bg-success/10 hover:bg-success/20',
    border: 'border-success/30',
    dot: 'bg-success',
  },
  queued: {
    text: 'text-amber-700 dark:text-amber-400',
    bg: 'bg-amber-500/10 hover:bg-amber-500/20',
    border: 'border-amber-500/30',
    dot: 'bg-amber-500',
  },
  running: {
    text: 'text-blue-700 dark:text-blue-400',
    bg: 'bg-blue-500/10 hover:bg-blue-500/20',
    border: 'border-blue-500/30',
    dot: 'bg-blue-500',
  },
  waiting: {
    text: 'text-muted-foreground',
    bg: 'bg-muted/40 hover:bg-muted/60',
    border: 'border-border',
    dot: 'bg-muted-foreground',
  },
  error: {
    text: 'text-destructive',
    bg: 'bg-destructive/10 hover:bg-destructive/20',
    border: 'border-destructive/30',
    dot: 'bg-destructive',
  },
}

interface PipelineStatusBadgeProps {
  state: PipelineBadgeState
  label: string
  title: string
  timestamp?: string | null
  error?: string | null
}

export default function PipelineStatusBadge({
  state,
  label,
  title,
  timestamp,
  error,
}: PipelineStatusBadgeProps) {
  const { t } = useTranslation()
  const styles = STATE_STYLES[state]

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-medium cursor-pointer transition-colors ${styles.text} ${styles.bg} ${styles.border}`}
          title={t('components.syncStatusIndicator.clickForDetails')}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${styles.dot}`} />
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="start">
        <div className="space-y-2 text-sm">
          <div className="font-medium mb-2.5">{title}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
          {timestamp && (
            <div className="text-xs text-muted-foreground">{formatDate(timestamp)}</div>
          )}
          {error && <div className="text-xs text-destructive break-words">{error}</div>}
        </div>
      </PopoverContent>
    </Popover>
  )
}
