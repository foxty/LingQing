import { useTranslation } from 'react-i18next'
import { formatChatTimestamp } from '@/lib/dateTime'
import type { DateTimeFormatId } from '@/lib/datetimeFormats'
import { SessionMetrics } from '@/types'
import MessageFeedbackButtons from './MessageFeedbackButtons'
import type { MessageFeedback } from '@/types'
import CopyIconButton, { type CopyIconStatus } from '@/components/CopyIconButton'

interface AiTurnMessageFooterProps {
  timestamp?: string
  timeZone: string
  dateTimeFormat: DateTimeFormatId
  sessionMetrics: SessionMetrics | null
  showSessionMetrics: boolean
  onToggleSessionMetrics: () => void
  showActions: boolean
  threadId?: string
  messageId?: string
  feedback?: MessageFeedback
  onFeedbackChange: (feedback: MessageFeedback | undefined) => void
  copyStatus: CopyIconStatus
  onCopy: () => void
}

export default function AiTurnMessageFooter({
  timestamp,
  timeZone,
  dateTimeFormat,
  sessionMetrics,
  showSessionMetrics,
  onToggleSessionMetrics,
  showActions,
  threadId,
  messageId,
  feedback,
  onFeedbackChange,
  copyStatus,
  onCopy,
}: AiTurnMessageFooterProps) {
  const { t, i18n } = useTranslation()

  const formattedTimestamp = formatChatTimestamp(timestamp, {
    timeZone,
    locale: i18n.language,
    formatId: dateTimeFormat,
  })

  return (
    <div className="mt-2 flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-muted-foreground/80">
      {formattedTimestamp ? (
        <span className="shrink-0 tabular-nums">{formattedTimestamp}</span>
      ) : (
        <span />
      )}
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
        {sessionMetrics ? (
          <button
            type="button"
            onClick={onToggleSessionMetrics}
            className="text-foreground hover:underline"
          >
            {sessionMetrics.total_tokens.total_tokens} tokens ·{' '}
            {((sessionMetrics.duration_ms ?? 0) / 1000).toFixed(1)}s ·{' '}
            {showSessionMetrics ? t('workbench.hideMetrics') : t('workbench.viewMetrics')}
          </button>
        ) : null}
        {showActions ? (
          <div
            className={`inline-flex items-center gap-0.5 ${
              sessionMetrics ? 'border-l border-border pl-2' : ''
            }`}
          >
            <MessageFeedbackButtons
              threadId={threadId}
              messageId={messageId}
              feedback={feedback}
              onFeedbackChange={onFeedbackChange}
            />
            <CopyIconButton
              status={copyStatus}
              onCopy={onCopy}
              label={t('workbench.copyReply')}
              copiedLabel={t('workbench.copied')}
            />
          </div>
        ) : null}
      </div>
    </div>
  )
}