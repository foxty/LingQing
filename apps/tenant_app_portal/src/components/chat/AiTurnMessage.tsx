import './aiTurnMessageI18n'
import CollapsibleMessageBody from './CollapsibleMessageBody'
import { AlertCircle, Bot, CircleStop, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AGENT_RUN_STATUS, messageAgentRunStatus } from '@/lib/agentRunStatus'
import { AiTurn } from '@/lib/chatTurns'
import { usePreferredDateTimeFormat, usePreferredTimezone } from '@/hooks/useCurrentUserProfile'
import MarkdownDocument from '@/components/markdown/MarkdownDocument'
import type { MessageFeedback } from '@/types'
import AiTurnExecutionDetails from './AiTurnExecutionDetails'
import AiTurnMessageFooter from './AiTurnMessageFooter'
import AiTurnSessionMetricsPanel from './AiTurnSessionMetricsPanel'
import { useCopyToClipboard } from '@/components/CopyIconButton'
import {
  AI_TURN_BUBBLE_WIDTH,
  getProcessBadges,
  groupProcessItems,
  isSessionMetrics,
} from './aiTurnMessageUtils'

interface AiTurnMessageProps {
  turn: AiTurn
  threadId?: string
  defaultProcessOpen?: boolean
  isStreaming?: boolean
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
}

export default function AiTurnMessage({
  turn,
  threadId,
  defaultProcessOpen = false,
  isStreaming = false,
  onHitlApprovedContinue,
  onHitlRejected,
}: AiTurnMessageProps) {
  const { t } = useTranslation()
  const timeZone = usePreferredTimezone()
  const dateTimeFormat = usePreferredDateTimeFormat()
  const [showProcessDetails, setShowProcessDetails] = useState(defaultProcessOpen)
  const [showSessionMetrics, setShowSessionMetrics] = useState(false)
  const { status: copyStatus, copy: handleCopyFinalMessage } = useCopyToClipboard(
    turn.finalMessage.content ?? '',
    turn.id
  )
  const [localFeedback, setLocalFeedback] = useState<MessageFeedback | undefined>(
    turn.finalMessage.feedback
  )

  useEffect(() => {
    setLocalFeedback(turn.finalMessage.feedback)
  }, [turn.finalMessage.feedback, turn.finalMessage.message_id])

  useEffect(() => {
    setShowProcessDetails(defaultProcessOpen)
  }, [defaultProcessOpen, turn.id])

  const isError = turn.finalMessage.content.startsWith('❌')
  const cancelledNotice = t('workbench.runCancelledInline')
  const sessionMetrics = isSessionMetrics(turn.metrics)
    ? turn.metrics
    : isSessionMetrics(turn.finalMessage.metrics)
      ? turn.finalMessage.metrics
      : null
  const thinkingContent =
    typeof turn.finalMessage.message_metadata?.thinking_content === 'string'
      ? turn.finalMessage.message_metadata.thinking_content.trim()
      : ''

  const processBadges = useMemo(() => getProcessBadges(turn, t), [turn, t])
  const processGroups = useMemo(() => groupProcessItems(turn.processItems), [turn.processItems])

  const hasProcessArea =
    turn.toolItems.length > 0 || turn.approvals.length > 0 || turn.processMessages.length > 0

  const thinkingPlaceholder = t('workbench.thinking')
  const hasRunningTool = turn.toolItems.some((item) => item.status === 'running')
  const finalContent = turn.finalMessage.content?.trim() || ''
  const hasRealFinalContent =
    finalContent.length > 0 && finalContent !== thinkingPlaceholder
  const agentRunStatus = messageAgentRunStatus(turn.finalMessage)
  const isCancelled = agentRunStatus === AGENT_RUN_STATUS.CANCELLED
  const showCancelledNoticeOnly = isCancelled && !hasRealFinalContent
  const showCancelledPartial = isCancelled && hasRealFinalContent
  const showInitialWorkingState = isStreaming && !hasProcessArea && !hasRealFinalContent
  const showFinalMessageActions =
    !showCancelledNoticeOnly && !isStreaming && !isCancelled && hasRealFinalContent

  return (
    <div className="flex items-start space-x-3">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isError ? 'bg-destructive/10 text-destructive' : 'bg-muted'
        } ${isStreaming ? 'ring-2 ring-primary/30' : ''} ${isCancelled ? 'ring-1 ring-border' : ''}`}
      >
        {isError ? (
          <AlertCircle className="h-4 w-4" />
        ) : isCancelled ? (
          <CircleStop className="h-4 w-4 text-muted-foreground" />
        ) : isStreaming ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col items-start space-y-1">
        {showInitialWorkingState ? (
          <div
            className={`${AI_TURN_BUBBLE_WIDTH} rounded-lg border border-primary/20 bg-muted px-4 py-3`}
          >
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>{t('workbench.working')}</span>
              <span className="inline-flex gap-0.5">
                <span className="animate-bounce [animation-delay:0ms]">.</span>
                <span className="animate-bounce [animation-delay:150ms]">.</span>
                <span className="animate-bounce [animation-delay:300ms]">.</span>
              </span>
            </div>
          </div>
        ) : (
          <div
            className={`relative ${AI_TURN_BUBBLE_WIDTH} rounded-lg px-4 py-3 ${
              isError ? 'bg-destructive/5 border border-destructive/20' : 'bg-muted'
            } ${isStreaming ? 'border border-primary/20' : ''} ${
              isCancelled ? 'border border-dashed border-muted-foreground/35' : ''
            }`}
          >
            {showCancelledNoticeOnly ? (
              <p className="text-sm italic text-muted-foreground">{cancelledNotice}</p>
            ) : null}
            {!showCancelledNoticeOnly && hasProcessArea ? (
              <AiTurnExecutionDetails
                turn={turn}
                threadId={threadId}
                isStreaming={isStreaming}
                processBadges={processBadges}
                processGroups={processGroups}
                expanded={showProcessDetails}
                onToggle={() => setShowProcessDetails((prev) => !prev)}
                timeZone={timeZone}
                dateTimeFormat={dateTimeFormat}
                onHitlApprovedContinue={onHitlApprovedContinue}
                onHitlRejected={onHitlRejected}
              />
            ) : null}

            {!showCancelledNoticeOnly ? (
              <div className="mb-1 text-xs font-semibold text-muted-foreground">
                {t('workbench.finalResponse')}
              </div>
            ) : null}
            {!showCancelledNoticeOnly && hasRealFinalContent ? (
              <div className="min-w-0 text-sm">
                <CollapsibleMessageBody
                  contentLength={turn.finalMessage.content.length}
                  isStreaming={isStreaming}
                >
                  <MarkdownDocument content={turn.finalMessage.content} density="default" />
                </CollapsibleMessageBody>
                {showCancelledPartial ? (
                  <p className="mt-2 text-xs italic text-muted-foreground">{cancelledNotice}</p>
                ) : null}
                {isStreaming ? (
                  <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-primary" />
                ) : null}
              </div>
            ) : !showCancelledNoticeOnly && isStreaming ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>
                  {hasRunningTool ? t('workbench.working') : t('workbench.generatingResponse')}
                </span>
              </div>
            ) : !showCancelledNoticeOnly ? (
              <div className="text-sm text-muted-foreground">{t('workbench.noResponseGenerated')}</div>
            ) : null}

            {!showCancelledNoticeOnly && !isStreaming && copyStatus === 'error' ? (
              <div className="mt-1 text-[11px] text-destructive">{t('workbench.copyFailed')}</div>
            ) : null}

            {!showCancelledNoticeOnly && !isStreaming ? (
              <AiTurnMessageFooter
                timestamp={turn.timestamp}
                timeZone={timeZone}
                dateTimeFormat={dateTimeFormat}
                sessionMetrics={sessionMetrics}
                showSessionMetrics={showSessionMetrics}
                onToggleSessionMetrics={() => setShowSessionMetrics((prev) => !prev)}
                showActions={showFinalMessageActions}
                threadId={threadId}
                messageId={turn.finalMessage.message_id}
                feedback={localFeedback}
                onFeedbackChange={setLocalFeedback}
                copyStatus={copyStatus}
                onCopy={() => void handleCopyFinalMessage()}
              />
            ) : null}

            {!isStreaming && sessionMetrics && showSessionMetrics ? (
              <AiTurnSessionMetricsPanel
                sessionMetrics={sessionMetrics}
                thinkingContent={thinkingContent}
              />
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}