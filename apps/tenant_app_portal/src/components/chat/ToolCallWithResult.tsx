import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useState } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    toolCallWithResult: {
      processing: 'Processing...',
      awaitingApproval: 'Awaiting approval',
      failed: 'Failed',
      completed: 'Completed',
      showDetails: 'Show details',
      hideDetails: 'Hide details',
      params: 'Parameters',
      execResult: 'Execution Result',
      showFullResult: 'Show full result',
      hideFullResult: 'Hide full result',
      executingWillShow: 'Result will appear when execution completes',
      loadingToolDetails: 'Loading tool details...',
      noToolDetails: 'No details available',
      showMetrics: 'Show metrics',
      hideMetrics: 'Hide metrics',
      toolName: 'Tool Name',
      toolStatus: 'Status',
      success: 'Success',
      error: 'Error',
      duration: 'Duration',
      inputSize: 'Input Size',
      outputSize: 'Output Size',
      errorInfo: 'Error Info',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    toolCallWithResult: {
      processing: '处理中...',
      awaitingApproval: '等待审批',
      failed: '失败',
      completed: '完成',
      showDetails: '显示详情',
      hideDetails: '隐藏详情',
      params: '参数',
      execResult: '执行结果',
      showFullResult: '显示完整结果',
      hideFullResult: '隐藏完整结果',
      executingWillShow: '执行完成后将显示结果',
      loadingToolDetails: '加载工具详情...',
      noToolDetails: '暂无详情',
      showMetrics: '显示指标',
      hideMetrics: '隐藏指标',
      toolName: '工具名称',
      toolStatus: '状态',
      success: '成功',
      error: '错误',
      duration: '时长',
      inputSize: '输入大小',
      outputSize: '输出大小',
      errorInfo: '错误信息',
    },
  },
}, true, true)
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, BarChart3, CheckCircle2, XCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Message, ToolCallMetrics } from '@/types'
import { preprocessMarkdown } from '@/lib/utils'
import { getToolCallMetrics } from '@/lib/chatApi'
import { useToolCallDetail } from '@/hooks/useChatHistory'
import { ToolCallProgressStatus } from '@/lib/chatTurns'

interface ToolCallWithResultProps {
  toolCall: {
    id: string
    name: string
    args: Record<string, any>
  }
  resultMessage?: Message
  threadId: string
  compact?: boolean
  status?: ToolCallProgressStatus
  variant?: 'card' | 'details-only'
}

const RESULT_PREVIEW_LENGTH_COMPACT = 160
const RESULT_PREVIEW_LENGTH_DEFAULT = 280

function isToolCallMetrics(metrics: any): metrics is ToolCallMetrics {
  return metrics && 'tool_call_id' in metrics
}

export default function ToolCallWithResult({
  toolCall,
  resultMessage,
  threadId,
  compact = false,
  status,
  variant = 'card',
}: ToolCallWithResultProps) {
  const { t } = useTranslation()
  const [showDetails, setShowDetails] = useState(variant === 'details-only' ? true : !compact)
  const [showFullResult, setShowFullResult] = useState(false)
  const [showToolMetrics, setShowToolMetrics] = useState(false)

  const isProvisionalStreamToolCallId = toolCall.id.startsWith('stream-tool-')
  const canFetchToolDetail = showDetails && !resultMessage && !isProvisionalStreamToolCallId

  const { data: lazyDetailMessage, isLoading: loadingToolDetail } = useToolCallDetail(
    threadId,
    toolCall.id,
    resultMessage?.session_id,
    canFetchToolDetail
  )

  const effectiveResultMessage = resultMessage || lazyDetailMessage || undefined

  const hasArgs = Object.keys(toolCall.args).length > 0
  const argsString = JSON.stringify(toolCall.args, null, 2)

  const toolMetrics =
    effectiveResultMessage && isToolCallMetrics(effectiveResultMessage.metrics)
      ? effectiveResultMessage.metrics
      : null

  const sessionIdForMetrics = effectiveResultMessage?.session_id
  const { data: lazyToolMetrics } = useQuery<ToolCallMetrics | null>({
    queryKey: ['toolCallMetricsDetail', toolCall.id, sessionIdForMetrics],
    queryFn: async () => {
      if (!sessionIdForMetrics) return null
      try {
        return await getToolCallMetrics(toolCall.id, sessionIdForMetrics)
      } catch {
        return null
      }
    },
    enabled: showDetails && !toolMetrics && !!sessionIdForMetrics && !isProvisionalStreamToolCallId,
    staleTime: 5 * 60 * 1000,
  })

  const effectiveToolMetrics = toolMetrics || lazyToolMetrics || null

  const resultContent = effectiveResultMessage?.content || ''
  const previewLength = compact ? RESULT_PREVIEW_LENGTH_COMPACT : RESULT_PREVIEW_LENGTH_DEFAULT
  const shouldCollapseResult = resultContent.length > previewLength
  const displayContent = effectiveResultMessage
    ? preprocessMarkdown(
        shouldCollapseResult && !showFullResult
          ? `${resultContent.slice(0, previewLength).trimEnd()}...`
          : resultContent
      )
    : null

  const effectiveStatus: ToolCallProgressStatus | 'error' | 'completed' =
    status || (effectiveToolMetrics?.status === 'error' ? 'error' : 'completed')

  const statusIcon =
    effectiveStatus === 'running' ? (
      <span className="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
    ) : effectiveStatus === 'hitl_pending' ? (
      <span className="inline-block h-2 w-2 rounded-full bg-amber-600" />
    ) : effectiveStatus === 'error' ? (
      <XCircle className="w-3 h-3 text-red-600 dark:text-red-400" />
    ) : (
      <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-400" />
    )

  const statusText =
    effectiveStatus === 'running'
      ? t('components.toolCallWithResult.processing')
      : effectiveStatus === 'hitl_pending'
        ? t('components.toolCallWithResult.awaitingApproval')
        : effectiveStatus === 'error'
          ? t('components.toolCallWithResult.failed')
          : t('components.toolCallWithResult.completed')

  const detailsContent = showDetails ? (
    <>
      {hasArgs && (
        <div className="px-3 py-2 border-b border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/50">
          <div className="text-xs text-foreground font-medium mb-1">{t('components.toolCallWithResult.params')}</div>
          <pre className="text-xs bg-muted/80 rounded p-2 overflow-x-auto">{argsString}</pre>
        </div>
      )}

      {displayContent && (
        <div className="px-3 py-2">
          <div className="text-xs text-foreground font-medium mb-2">
            {t('components.toolCallWithResult.execResult')}
          </div>
          <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-pre:my-1">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
          </div>
          {shouldCollapseResult && (
            <button
              onClick={() => setShowFullResult((prev) => !prev)}
              className="mt-1 text-xs text-foreground hover:underline"
            >
              {showFullResult ? t('components.toolCallWithResult.hideFullResult') : t('components.toolCallWithResult.showFullResult')}
            </button>
          )}
        </div>
      )}

      {showDetails && !displayContent && (
        <div className="px-3 py-2 text-xs text-muted-foreground">
          {isProvisionalStreamToolCallId
            ? t('components.toolCallWithResult.executingWillShow')
            : loadingToolDetail
              ? t('components.toolCallWithResult.loadingToolDetails')
              : t('components.toolCallWithResult.noToolDetails')}
        </div>
      )}

      {effectiveToolMetrics && (
        <div className="px-3 py-2 border-t border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/50">
          <button
            onClick={() => setShowToolMetrics(!showToolMetrics)}
            className="flex items-center gap-2 text-xs text-foreground hover:underline"
          >
            <BarChart3 className="w-3 h-3" />
            {showToolMetrics ? t('components.toolCallWithResult.hideMetrics') : t('components.toolCallWithResult.showMetrics')}
          </button>
          {showToolMetrics && (
            <div className="mt-2 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('components.toolCallWithResult.toolName')}</span>
                <span className="font-medium">{effectiveToolMetrics.tool_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('components.toolCallWithResult.toolStatus')}</span>
                <span
                  className={`font-medium ${effectiveToolMetrics.status === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
                >
                  {effectiveToolMetrics.status === 'success' ? `✅ ${t('components.toolCallWithResult.success')}` : `❌ ${t('components.toolCallWithResult.error')}`}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('components.toolCallWithResult.duration')}</span>
                <span className="font-medium">
                  {effectiveToolMetrics.duration_ms
                    ? `${effectiveToolMetrics.duration_ms.toFixed(2)}ms`
                    : 'N/A'}
                </span>
              </div>
              {effectiveToolMetrics.input_size !== undefined && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('components.toolCallWithResult.inputSize')}</span>
                  <span className="font-medium">{effectiveToolMetrics.input_size} bytes</span>
                </div>
              )}
              {effectiveToolMetrics.output_size !== undefined && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('components.toolCallWithResult.outputSize')}</span>
                  <span className="font-medium">{effectiveToolMetrics.output_size} bytes</span>
                </div>
              )}
              {effectiveToolMetrics.error_message && (
                <div className="flex flex-col gap-1">
                  <span className="text-muted-foreground">{t('components.toolCallWithResult.errorInfo')}</span>
                  <span className="font-medium text-red-600 dark:text-red-400">
                    {effectiveToolMetrics.error_message}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  ) : null

  if (variant === 'details-only') {
    return (
      <div className="rounded-md border border-border bg-secondary/20 overflow-hidden text-left">
        {detailsContent}
      </div>
    )
  }

  return (
    <div
      className={`border rounded-lg overflow-hidden ${
        effectiveStatus === 'hitl_pending'
          ? 'border-amber-300 dark:border-amber-700 bg-amber-50/40 dark:bg-amber-950/30'
          : 'border-border bg-secondary/30'
      }`}
    >
      {/* Tool Call Header */}
      <div
        className={`px-3 py-2 border-b ${
          effectiveStatus === 'hitl_pending'
            ? 'bg-amber-100 dark:bg-amber-900 border-amber-200 dark:border-amber-800'
            : 'bg-secondary border-border'
        }`}
      >
        <button
          onClick={() => setShowDetails((prev) => !prev)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <span className="text-xs">🔧</span>
            <span
              className={`text-xs font-medium ${
                effectiveStatus === 'hitl_pending'
                  ? 'text-amber-900 dark:text-amber-100'
                  : 'text-foreground'
              }`}
            >
              {toolCall.name}
            </span>
            {statusIcon}
            <span className="text-[10px] text-muted-foreground">{statusText}</span>
            {effectiveToolMetrics && (
              <span className="text-xs text-muted-foreground">
                {effectiveToolMetrics.duration_ms.toFixed(2)}ms
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            <span>{showDetails ? t('components.toolCallWithResult.hideDetails') : t('components.toolCallWithResult.showDetails')}</span>
          </div>
        </button>
      </div>

      {detailsContent}
    </div>
  )
}
