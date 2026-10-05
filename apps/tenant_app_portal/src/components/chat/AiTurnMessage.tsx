import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { SessionMetrics } from '@/types'

i18n.addResourceBundle('en', 'translation', {
  workbench: {
    toolCalls: 'Tool calls:',
    toolApprovals: 'Approvals:',
    toolInterimResponses: 'Interim responses:',
    executionDetails: 'Execution Details',
    finalResponse: 'Final Response',
    copyFailed: 'Failed to copy',
    copyReply: 'Copy reply',
    copied: 'Copied',
    approvalOps: 'Approval Required',
    intermediateResponses: 'Intermediate Responses',
    hideMetrics: 'Hide metrics',
    viewMetrics: 'View metrics',
    modelUsed: 'Model Used',
    inputTokens: 'Input Tokens',
    outputTokens: 'Output Tokens',
    totalTokens: 'Total Tokens',
    llmCallCount: 'LLM Calls:',
    toolCallCount: 'Tool Calls',
    duration: 'Duration',
    working: 'Working on your request',
    generatingResponse: 'Generating response',
    thinking: 'Thinking...',
    noResponseGenerated: 'No response was generated.',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  workbench: {
    toolCalls: '工具调用:',
    toolApprovals: '审批:',
    toolInterimResponses: '中间响应:',
    executionDetails: '执行详情',
    finalResponse: '最终响应',
    copyFailed: '复制失败',
    copyReply: '复制回复',
    copied: '已复制',
    approvalOps: '需要审批',
    intermediateResponses: '中间响应',
    hideMetrics: '隐藏指标',
    viewMetrics: '查看指标',
    modelUsed: '使用的模型',
    inputTokens: '输入 Token',
    outputTokens: '输出 Token',
    totalTokens: '总 Token',
    llmCallCount: 'LLM 调用:',
    toolCallCount: '工具调用',
    duration: '时长',
    working: '正在处理您的请求',
    generatingResponse: '正在生成回复',
    thinking: '思考中...',
    noResponseGenerated: '未生成回复内容。',
  },
}, true, true)
import { AlertCircle, Bot, Check, ChevronDown, ChevronUp, Copy, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { copyToClipboard, preprocessMarkdown } from '@/lib/utils'
import { AiTurn, TurnProcessItem } from '@/lib/chatTurns'
import ToolCallTimeline from './ToolCallTimeline'
import HitlApprovalCard from './HitlApprovalCard'
import MessageFeedbackButtons from './MessageFeedbackButtons'
import { AuthDocumentImage } from './AuthDocumentImage'
import type { MessageFeedback } from '@/types'

const markdownComponents = { img: AuthDocumentImage }

type ToolProcessItem = Extract<TurnProcessItem, { type: 'tool' }>
type ApprovalProcessItem = Extract<TurnProcessItem, { type: 'approval' }>
type MessageProcessItem = Extract<TurnProcessItem, { type: 'message' }>

type ProcessRenderGroup =
  | { type: 'tools'; items: ToolProcessItem[]; keys: string[] }
  | { type: 'approval'; item: ApprovalProcessItem; index: number }
  | { type: 'message'; item: MessageProcessItem; index: number }

function groupProcessItems(processItems: TurnProcessItem[]): ProcessRenderGroup[] {
  const groups: ProcessRenderGroup[] = []
  let toolBuffer: { items: ToolProcessItem[]; keys: string[] } | null = null

  const flushTools = () => {
    if (toolBuffer && toolBuffer.items.length > 0) {
      groups.push({ type: 'tools', items: toolBuffer.items, keys: toolBuffer.keys })
      toolBuffer = null
    }
  }

  processItems.forEach((item, index) => {
    if (item.type === 'tool') {
      if (item.toolItem.hitl?.proposal_id) {
        return
      }
      if (!toolBuffer) {
        toolBuffer = { items: [], keys: [] }
      }
      toolBuffer.items.push(item)
      toolBuffer.keys.push(item.key || `tool-${index}`)
      return
    }

    flushTools()
    if (item.type === 'approval') {
      groups.push({ type: 'approval', item, index })
    } else if (item.type === 'message') {
      groups.push({ type: 'message', item, index })
    }
  })

  flushTools()
  return groups
}

interface AiTurnMessageProps {
  turn: AiTurn
  threadId?: string
  defaultProcessOpen?: boolean
  isStreaming?: boolean
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
}

function isSessionMetrics(metrics: unknown): metrics is SessionMetrics {
  return (
    typeof metrics === 'object' &&
    metrics !== null &&
    'session_id' in metrics &&
    'total_tokens' in metrics
  )
}

function getProcessBadges(turn: AiTurn, t: (key: string) => string): string[] {
  const badges: string[] = []

  if (turn.approvals.length > 0) {
    badges.push(`${t('workbench.toolApprovals')} ${turn.approvals.length}`)
  }
  if (turn.processMessages.length > 0) {
    badges.push(`${t('workbench.toolInterimResponses')} ${turn.processMessages.length}`)
  }

  return badges
}

function formatProcessItemTime(timestamp?: string): string {
  if (!timestamp) {
    return ''
  }

  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  return date.toLocaleTimeString(undefined, {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
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
  const [showProcessDetails, setShowProcessDetails] = useState(defaultProcessOpen)
  const [showSessionMetrics, setShowSessionMetrics] = useState(false)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'error'>('idle')
  const [localFeedback, setLocalFeedback] = useState<MessageFeedback | undefined>(
    turn.finalMessage.feedback
  )

  useEffect(() => {
    setLocalFeedback(turn.finalMessage.feedback)
  }, [turn.finalMessage.feedback, turn.finalMessage.message_id])

  useEffect(() => {
    setShowProcessDetails(defaultProcessOpen)
  }, [defaultProcessOpen, turn.id])

  useEffect(() => {
    setCopyStatus('idle')
  }, [turn.id])

  const handleCopyFinalMessage = async () => {
    const text = turn.finalMessage.content?.trim()
    if (!text) {
      setCopyStatus('error')
      return
    }

    const success = await copyToClipboard(text)
    setCopyStatus(success ? 'copied' : 'error')
  }

  const isError = turn.finalMessage.content.startsWith('❌')
  const sessionMetrics = isSessionMetrics(turn.metrics)
    ? turn.metrics
    : isSessionMetrics(turn.finalMessage.metrics)
      ? turn.finalMessage.metrics
      : null
  const usedModels = useMemo(() => {
    if (!sessionMetrics?.model_usage) {
      return []
    }

    return Object.entries(sessionMetrics.model_usage)
      .filter(([modelKey]) => Boolean(modelKey))
      .map(([modelKey, usage]) => `${modelKey} (${usage.calls} ${t('workbench.llmCallCount').replace(':', '')})`)
  }, [sessionMetrics])
  const processBadges = useMemo(() => getProcessBadges(turn, t), [turn, t])
  const processGroups = useMemo(() => groupProcessItems(turn.processItems), [turn.processItems])

  const hasProcessArea =
    turn.toolItems.length > 0 || turn.approvals.length > 0 || turn.processMessages.length > 0

  const thinkingPlaceholder = t('workbench.thinking')
  const hasRunningTool = turn.toolItems.some((item) => item.status === 'running')
  const finalContent = turn.finalMessage.content?.trim() || ''
  const hasRealFinalContent =
    finalContent.length > 0 && finalContent !== thinkingPlaceholder
  const showInitialWorkingState = isStreaming && !hasProcessArea && !hasRealFinalContent

  return (
    <div className="flex items-start space-x-3">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isError ? 'bg-destructive/10 text-destructive' : 'bg-muted'
        } ${isStreaming ? 'ring-2 ring-primary/30' : ''}`}
      >
        {isError ? (
          <AlertCircle className="h-4 w-4" />
        ) : isStreaming ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className="flex-1 space-y-1 items-start">
        {showInitialWorkingState ? (
          <div className="rounded-lg px-4 py-3 max-w-[80%] bg-muted border border-primary/20">
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
          className={`relative rounded-lg px-4 py-3 max-w-[80%] ${
            isError ? 'bg-destructive/5 border border-destructive/20' : 'bg-muted'
          } ${isStreaming ? 'border border-primary/20' : ''}`}
        >
          {hasProcessArea && (
            <div className="mb-3 border-l-2 border-border pl-3">
              <button
                onClick={() => setShowProcessDetails((prev) => !prev)}
                className="flex w-full items-center justify-between text-left"
              >
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-foreground">
                    {t('workbench.executionDetails')}
                  </div>
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
                {showProcessDetails ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </button>

              {showProcessDetails && (
                <div className="mt-2 space-y-2">
                  {processGroups.map((group) => {
                    if (group.type === 'tools') {
                      return (
                        <ToolCallTimeline
                          key={group.keys.join('-')}
                          items={group.items.map((item) => item.toolItem)}
                          itemKeys={group.keys}
                          threadId={threadId || ''}
                          isStreaming={isStreaming}
                        />
                      )
                    }

                    if (group.type === 'approval') {
                      const item = group.item
                      const index = group.index
                      const itemTime = formatProcessItemTime(item.timestamp)
                      return (
                        <div key={item.key || `${turn.id}-approval-${index}`}>
                          <div className="mb-1 flex items-center justify-between gap-2">
                            <div className="text-xs font-semibold text-amber-900 dark:text-amber-100">
                              ⚠ {t('workbench.approvalOps')}
                            </div>
                            {itemTime && (
                              <div className="text-[10px] text-muted-foreground/80">{itemTime}</div>
                            )}
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
                    const itemTime = formatProcessItemTime(item.timestamp)

                    if (!item.message.content?.trim()) {
                      return null
                    }

                    return (
                      <div key={item.key || `${turn.id}-message-${index}`} className="text-sm">
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <div className="text-xs text-muted-foreground">
                            {t('workbench.intermediateResponses')}
                          </div>
                          {itemTime && (
                            <div className="text-[10px] text-muted-foreground/80">{itemTime}</div>
                          )}
                        </div>
                        <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-pre:my-1">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                            {preprocessMarkdown(item.message.content)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          <div className="mb-1 flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-muted-foreground">{t('workbench.finalResponse')}</div>
            {!isStreaming && (
            <div className="inline-flex items-center gap-1">
              <MessageFeedbackButtons
                threadId={threadId}
                messageId={turn.finalMessage.message_id}
                feedback={localFeedback}
                onFeedbackChange={setLocalFeedback}
              />
              <button
                onClick={handleCopyFinalMessage}
                className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                title={copyStatus === 'copied' ? t('workbench.copied') : t('workbench.copyReply')}
                aria-label={copyStatus === 'copied' ? t('workbench.copied') : t('workbench.copyReply')}
              >
                {copyStatus === 'copied' ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
            )}
          </div>
          {hasRealFinalContent ? (
          <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:my-2 prose-pre:my-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {preprocessMarkdown(turn.finalMessage.content)}
            </ReactMarkdown>
            {isStreaming ? (
              <span className="inline-block w-1 h-4 bg-primary ml-1 animate-pulse" />
            ) : null}
          </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>{hasRunningTool ? t('workbench.working') : t('workbench.generatingResponse')}</span>
            </div>
          ) : (
          <div className="text-sm text-muted-foreground">
            {t('workbench.noResponseGenerated')}
          </div>
          )}

          {!isStreaming && copyStatus === 'error' && (
            <div className="mt-1 text-[11px] text-destructive">{t('workbench.copyFailed')}</div>
          )}

          {!isStreaming && (
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground/80">
            <span>{turn.timestamp && new Date(turn.timestamp).toLocaleTimeString()}</span>
            {sessionMetrics && (
              <button
                onClick={() => setShowSessionMetrics((prev) => !prev)}
                className="text-foreground hover:underline"
              >
                {sessionMetrics.total_tokens.total_tokens} tokens ·{' '}
                {((sessionMetrics.duration_ms ?? 0) / 1000).toFixed(1)}s ·{' '}
                {showSessionMetrics ? t('workbench.hideMetrics') : t('workbench.viewMetrics')}
              </button>
            )}
          </div>
          )}

          {!isStreaming && sessionMetrics && showSessionMetrics && (
            <div className="mt-2 rounded-md border border-border bg-secondary/60 p-2 text-xs">
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Session ID:</span>
                <span className="font-medium text-right break-all">
                  {sessionMetrics.session_id}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">{t('workbench.modelUsed')}</span>
                <span className="font-medium text-right">
                  {usedModels.length > 0 ? usedModels.join(', ') : '-'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.inputTokens')}</span>
                <span className="font-medium">{sessionMetrics.total_tokens.input_tokens}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.outputTokens')}</span>
                <span className="font-medium">{sessionMetrics.total_tokens.output_tokens}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.totalTokens')}</span>
                <span className="font-medium">{sessionMetrics.total_tokens.total_tokens}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.llmCallCount')}</span>
                <span className="font-medium">{sessionMetrics.llm_call_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.toolCallCount')}</span>
                <span className="font-medium">{sessionMetrics.tool_call_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('workbench.duration')}</span>
                <span className="font-medium">{(sessionMetrics.duration_ms ?? 0).toFixed(2)}ms</span>
              </div>
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  )
}
