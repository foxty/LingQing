import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { SessionMetrics } from '@/types'

interface AiTurnSessionMetricsPanelProps {
  sessionMetrics: SessionMetrics
  thinkingContent: string
}

export default function AiTurnSessionMetricsPanel({
  sessionMetrics,
  thinkingContent,
}: AiTurnSessionMetricsPanelProps) {
  const { t } = useTranslation()

  const reasoningEvidenceLabel = (evidence?: string) => {
    if (evidence === 'usage') return t('workbench.reasoningEvidenceUsage')
    if (evidence === 'content_blocks') return t('workbench.reasoningEvidenceBlocks')
    return t('workbench.reasoningEvidenceNone')
  }

  const usedModels = useMemo(() => {
    if (!sessionMetrics.model_usage) {
      return []
    }

    return Object.entries(sessionMetrics.model_usage)
      .filter(([modelKey]) => Boolean(modelKey))
      .map(
        ([modelKey, usage]) =>
          `${modelKey} (${usage.calls} ${t('workbench.llmCallCount').replace(':', '')})`
      )
  }, [sessionMetrics, t])

  return (
    <div className="mt-2 rounded-md border border-border bg-secondary/60 p-2 text-xs">
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Session ID:</span>
        <span className="break-all text-right font-medium">{sessionMetrics.session_id}</span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">{t('workbench.modelUsed')}</span>
        <span className="text-right font-medium">{usedModels.length > 0 ? usedModels.join(', ') : '-'}</span>
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
      {sessionMetrics.thinking ? (
        <>
          <div className="mt-2 border-t border-border pt-2 font-medium text-foreground">
            {t('workbench.reasoningTitle')}
          </div>
          {'thinking_effort_requested' in sessionMetrics.thinking ? (
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">{t('workbench.reasoningEffortRequested')}</span>
              <span className="font-medium">
                {sessionMetrics.thinking.thinking_effort_requested ?? 'none'}
              </span>
            </div>
          ) : null}
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">{t('workbench.reasoningEffort')}</span>
            <span className="font-medium">{sessionMetrics.thinking.thinking_effort ?? 'none'}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">{t('workbench.reasoningApiRequest')}</span>
            <span className="break-all text-right font-medium">
              {sessionMetrics.thinking.thinking_request
                ? JSON.stringify(sessionMetrics.thinking.thinking_request)
                : t('workbench.reasoningEvidenceNone')}
            </span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">{t('workbench.reasoningSupported')}</span>
            <span className="font-medium">
              {sessionMetrics.thinking.supports_thinking ? 'yes' : 'no'}
            </span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">{t('workbench.reasoningEvidence')}</span>
            <span className="text-right font-medium">
              {reasoningEvidenceLabel(sessionMetrics.thinking.thinking_evidence)}
            </span>
          </div>
          {typeof sessionMetrics.thinking.reasoning_tokens === 'number' ? (
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">{t('workbench.reasoningTokens')}</span>
              <span className="font-medium">{sessionMetrics.thinking.reasoning_tokens}</span>
            </div>
          ) : null}
          {(sessionMetrics.thinking.reasoning_tokens ?? 0) > 0 &&
          (sessionMetrics.thinking.thinking_effort ?? 'none') === 'none' ? (
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
              {sessionMetrics.thinking.thinking_effort_none_disables === false
                ? t('workbench.reasoningNoneDoesNotDisable')
                : sessionMetrics.thinking.thinking_request &&
                    typeof sessionMetrics.thinking.thinking_request === 'object' &&
                    sessionMetrics.thinking.thinking_request.reasoning_effort === 'none'
                  ? t('workbench.reasoningGatewayMismatch')
                  : t('workbench.reasoningTokensHint')}
            </p>
          ) : null}
          {thinkingContent ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                {t('workbench.showReasoning')}
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-background/80 p-2 text-[11px] text-muted-foreground">
                {thinkingContent}
              </pre>
            </details>
          ) : null}
        </>
      ) : null}
    </div>
  )
}