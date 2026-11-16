import { ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AiTurn } from '@/lib/chatTurns'
import { formatChatTimestamp } from '@/lib/dateTime'
import type { DateTimeFormatId } from '@/lib/datetimeFormats'
import MarkdownDocument from '@/components/markdown/MarkdownDocument'
import ToolCallTimeline from './ToolCallTimeline'
import HitlApprovalCard from './HitlApprovalCard'
import type { ProcessRenderGroup } from './aiTurnMessageUtils'

interface AiTurnExecutionDetailsProps {
  turn: AiTurn
  threadId?: string
  isStreaming: boolean
  processBadges: string[]
  processGroups: ProcessRenderGroup[]
  expanded: boolean
  onToggle: () => void
  timeZone: string
  dateTimeFormat: DateTimeFormatId
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
}

export default function AiTurnExecutionDetails({
  turn,
  threadId,
  isStreaming,
  processBadges,
  processGroups,
  expanded,
  onToggle,
  timeZone,
  dateTimeFormat,
  onHitlApprovedContinue,
  onHitlRejected,
}: AiTurnExecutionDetailsProps) {
  const { t, i18n } = useTranslation()

  return (
    <div className="mb-3 min-w-0 border-l-2 border-border pl-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-foreground">{t('workbench.executionDetails')}</div>
          {processBadges.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {processBadges.map((badge) => (
                <span
                  key={badge}
                  className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-secondary-foreground"
                >
                  {badge}
                </span>
              ))}
            </div>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded ? (
        <div className="mt-2 max-h-64 min-w-0 space-y-2 overflow-x-hidden overflow-y-auto overscroll-y-contain pr-2 [scrollbar-gutter:stable]">
          {processGroups.map((group) => {
            if (group.type === 'tools') {
              return (
                <ToolCallTimeline
                  key={group.keys.join('-')}
                  items={group.items.map((item) => item.toolItem)}
                  itemKeys={group.keys}
                  threadId={threadId || ''}
                  sessionId={turn.sessionId}
                  isStreaming={isStreaming}
                />
              )
            }

            if (group.type === 'approval') {
              const item = group.item
              const index = group.index
              const itemTime = formatChatTimestamp(item.timestamp, {
                timeZone,
                locale: i18n.language,
                formatId: dateTimeFormat,
              })
              return (
                <div key={item.key || `${turn.id}-approval-${index}`} className="min-w-0">
                  <div className="mb-1 flex min-w-0 items-center justify-between gap-2">
                    <div className="min-w-0 truncate text-xs font-semibold text-amber-900 dark:text-amber-100">
                      ⚠ {t('workbench.approvalOps')}
                    </div>
                    {itemTime ? (
                      <div className="shrink-0 text-[10px] tabular-nums text-muted-foreground/80">
                        {itemTime}
                      </div>
                    ) : null}
                  </div>
                  <HitlApprovalCard
                    className="mt-0"
                    hitl={item.approval}
                    onApproved={onHitlApprovedContinue}
                    onRejected={onHitlRejected}
                  />
                </div>
              )
            }

            const item = group.item
            const index = group.index
            const itemTime = formatChatTimestamp(item.timestamp, {
              timeZone,
              locale: i18n.language,
              formatId: dateTimeFormat,
            })

            if (!item.message.content?.trim()) {
              return null
            }

            return (
              <div key={item.key || `${turn.id}-message-${index}`} className="min-w-0 text-sm">
                <div className="mb-1 flex min-w-0 items-center justify-between gap-2">
                  <div className="min-w-0 truncate text-xs text-muted-foreground">
                    {t('workbench.intermediateResponses')}
                  </div>
                  {itemTime ? (
                    <div className="shrink-0 text-[10px] tabular-nums text-muted-foreground/80">
                      {itemTime}
                    </div>
                  ) : null}
                </div>
                <MarkdownDocument content={item.message.content} density="compact" />
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}