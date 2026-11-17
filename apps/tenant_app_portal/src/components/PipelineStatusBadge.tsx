import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { PipelineBadgeState } from '@/lib/documentPipelineStatus'
import { useFormatUserDateTime } from '@/hooks/useUserDateTimeFormat'
import { Database, FileText, Loader2 } from 'lucide-react'

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
  phase: 'parse' | 'index'
  state: PipelineBadgeState
  label: string
  title: string
  timestamp?: string | null
  error?: string | null
}

export default function PipelineStatusBadge({
  phase,
  state,
  label,
  title,
  timestamp,
  error,
}: PipelineStatusBadgeProps) {
  const formatUserDateTime = useFormatUserDateTime()
  const styles = STATE_STYLES[state]
  const PhaseIcon = phase === 'parse' ? FileText : Database
  const showSpinner = state === 'running'

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${title}: ${label}`}
          className={`relative inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-colors cursor-pointer ${styles.text} ${styles.bg} ${styles.border}`}
        >
          {showSpinner ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <PhaseIcon className="h-3.5 w-3.5" aria-hidden />
          )}
          <span
            className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-background ${styles.dot}`}
            aria-hidden
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 space-y-2 p-3 text-sm" align="start">
        <div className="font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
        {timestamp ? (
          <div className="text-xs tabular-nums text-muted-foreground">{formatUserDateTime(timestamp)}</div>
        ) : null}
        {error ? <div className="text-xs text-destructive break-words">{error}</div> : null}
      </PopoverContent>
    </Popover>
  )
}
