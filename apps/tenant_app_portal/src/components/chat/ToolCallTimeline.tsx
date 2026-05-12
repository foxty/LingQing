import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from 'lucide-react'
import { TurnToolCallItem, ToolCallProgressStatus } from '@/lib/chatTurns'
import { ToolCallMetrics } from '@/types'
import ToolCallWithResult from './ToolCallWithResult'

i18n.addResourceBundle('en', 'translation', {
  components: {
    toolCallTimeline: {
      stepsCompleted: '{{completed}}/{{total}} completed',
      toolsCompleted: '{{count}} tools completed',
      toolsCompletedWithDuration: '{{count}} tools · {{duration}}s',
      expandSteps: 'Show steps',
      collapseSteps: 'Hide steps',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    toolCallTimeline: {
      stepsCompleted: '{{completed}}/{{total}} 已完成',
      toolsCompleted: '{{count}} 个工具已完成',
      toolsCompletedWithDuration: '{{count}} 个工具 · {{duration}}s',
      expandSteps: '展开步骤',
      collapseSteps: '收起步骤',
    },
  },
}, true, true)

const AUTO_COLLAPSE_THRESHOLD = 3

interface ToolCallTimelineProps {
  items: TurnToolCallItem[]
  itemKeys: string[]
  threadId: string
  isStreaming?: boolean
}

function isToolCallMetrics(metrics: unknown): metrics is ToolCallMetrics {
  return typeof metrics === 'object' && metrics !== null && 'tool_call_id' in metrics
}

function getItemDurationMs(item: TurnToolCallItem): number | null {
  const metrics = item.resultMessage?.metrics
  if (isToolCallMetrics(metrics) && metrics.duration_ms) {
    return metrics.duration_ms
  }
  return null
}

function getEffectiveStatus(
  item: TurnToolCallItem
): ToolCallProgressStatus | 'error' | 'completed' {
  if (item.status) return item.status
  const metrics = item.resultMessage?.metrics
  if (isToolCallMetrics(metrics) && metrics.status === 'error') return 'error'
  return 'completed'
}

interface TimelineRowProps {
  item: TurnToolCallItem
  threadId: string
  isLast: boolean
}

function TimelineRow({ item, threadId, isLast }: TimelineRowProps) {
  const [expanded, setExpanded] = useState(false)
  const status = getEffectiveStatus(item)
  const durationMs = getItemDurationMs(item)

  const statusDot =
    status === 'running' ? (
      <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-amber-500 animate-pulse" />
    ) : status === 'hitl_pending' ? (
      <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-amber-600" />
    ) : status === 'error' ? (
      <XCircle className="h-3 w-3 shrink-0 text-red-600 dark:text-red-400" />
    ) : (
      <CheckCircle2 className="h-3 w-3 shrink-0 text-green-600 dark:text-green-400" />
    )

  return (
    <div className="relative pl-4">
      {!isLast && (
        <span
          className="absolute left-[5px] top-[18px] bottom-0 w-px bg-border"
          aria-hidden
        />
      )}
      <span
        className="absolute left-[3px] top-[10px] flex h-[7px] w-[7px] items-center justify-center"
        aria-hidden
      >
        {statusDot}
      </span>

      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 rounded-sm py-1 pr-1 text-left hover:bg-secondary/60"
      >
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
          {item.toolCall.name}
        </span>
        {durationMs !== null && (
          <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
            {(durationMs / 1000).toFixed(1)}s
          </span>
        )}
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="mb-1 ml-1 mt-0.5">
          <ToolCallWithResult
            toolCall={item.toolCall}
            resultMessage={item.resultMessage}
            threadId={threadId}
            status={item.status}
            variant="details-only"
          />
        </div>
      )}
    </div>
  )
}

export default function ToolCallTimeline({
  items,
  itemKeys,
  threadId,
  isStreaming = false,
}: ToolCallTimelineProps) {
  const { t } = useTranslation()

  const completedCount = items.filter((item) => {
    const status = getEffectiveStatus(item)
    return status === 'completed' || status === 'error'
  }).length
  const hasRunning = items.some((item) => getEffectiveStatus(item) === 'running')
  const allComplete =
    items.length > 0 &&
    items.every((item) => {
      const status = getEffectiveStatus(item)
      return status !== 'running' && status !== 'hitl_pending'
    })

  const shouldAutoCollapse =
    !isStreaming && items.length >= AUTO_COLLAPSE_THRESHOLD && allComplete

  const userToggledRef = useRef(false)
  const [listExpanded, setListExpanded] = useState(() => !shouldAutoCollapse)

  useEffect(() => {
    if (shouldAutoCollapse && !userToggledRef.current) {
      setListExpanded(false)
    }
  }, [shouldAutoCollapse])

  const handleListToggle = (expanded: boolean) => {
    userToggledRef.current = true
    setListExpanded(expanded)
  }

  const totalDurationSec = useMemo(() => {
    const totalMs = items.reduce((sum, item) => sum + (getItemDurationMs(item) ?? 0), 0)
    return totalMs > 0 ? (totalMs / 1000).toFixed(1) : null
  }, [items])

  const summaryText = useMemo(() => {
    if (isStreaming && hasRunning) {
      return t('components.toolCallTimeline.stepsCompleted', {
        completed: completedCount,
        total: items.length,
      })
    }
    if (allComplete && totalDurationSec) {
      return t('components.toolCallTimeline.toolsCompletedWithDuration', {
        count: items.length,
        duration: totalDurationSec,
      })
    }
    if (allComplete) {
      return t('components.toolCallTimeline.toolsCompleted', { count: items.length })
    }
    if (isStreaming) {
      return t('components.toolCallTimeline.stepsCompleted', {
        completed: completedCount,
        total: items.length,
      })
    }
    return t('components.toolCallTimeline.stepsCompleted', {
      completed: completedCount,
      total: items.length,
    })
  }, [allComplete, completedCount, hasRunning, isStreaming, items.length, t, totalDurationSec])

  if (items.length === 0) {
    return null
  }

  if (shouldAutoCollapse && !listExpanded) {
    return (
      <button
        type="button"
        onClick={() => handleListToggle(true)}
        className="flex w-full items-center justify-between rounded-sm py-1 text-left text-xs text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      >
        <span>{summaryText}</span>
        <span className="flex items-center gap-1">
          <span className="text-[10px]">{t('components.toolCallTimeline.expandSteps')}</span>
          <ChevronRight className="h-3 w-3" />
        </span>
      </button>
    )
  }

  return (
    <div>
      {shouldAutoCollapse && (
        <button
          type="button"
          onClick={() => handleListToggle(false)}
          className="mb-1 flex w-full items-center justify-between rounded-sm py-1 text-left text-xs text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
        >
          <span>{summaryText}</span>
          <span className="flex items-center gap-1">
            <span className="text-[10px]">{t('components.toolCallTimeline.collapseSteps')}</span>
            <ChevronDown className="h-3 w-3" />
          </span>
        </button>
      )}

      {!shouldAutoCollapse && items.length >= 2 && (
        <div className="mb-1 text-[10px] text-muted-foreground">{summaryText}</div>
      )}

      <div className="space-y-0">
        {items.map((item, index) => (
          <TimelineRow
            key={itemKeys[index] || `${item.toolCall.id}-${index}`}
            item={item}
            threadId={threadId}
            isLast={index === items.length - 1}
          />
        ))}
      </div>
    </div>
  )
}
