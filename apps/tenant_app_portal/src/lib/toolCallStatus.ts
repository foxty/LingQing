import type { Message, ToolCallMetrics } from '@/types'

/** Matches {@link import('@/lib/chatTurns').ToolCallProgressStatus} without a circular import. */
export type ToolCallProgressStatus = 'running' | 'completed' | 'hitl_pending'

export type ToolCallDisplayStatus = ToolCallProgressStatus | 'error' | 'skipped'

/** Mirrors backend ``additional_kwargs.tool_result_status``. */
export type PersistedToolResultStatus = 'success' | 'error' | 'skipped' | 'partial'

export function isToolCallMetrics(metrics: unknown): metrics is ToolCallMetrics {
  return typeof metrics === 'object' && metrics !== null && 'tool_call_id' in metrics
}

export function readPersistedToolResultStatus(
  resultMessage?: Message | null
): PersistedToolResultStatus | undefined {
  const raw = resultMessage?.additional_kwargs?.tool_result_status
  if (raw === 'success' || raw === 'error' || raw === 'skipped' || raw === 'partial') {
    return raw
  }
  return undefined
}

/** Persisted tool outcome; missing or ``partial`` → treat as success for UI. */
export function resolvePersistedToolOutcome(
  resultMessage?: Message | null
): 'success' | 'error' | 'skipped' {
  const persisted = readPersistedToolResultStatus(resultMessage)
  if (persisted === 'error') {
    return 'error'
  }
  if (persisted === 'skipped') {
    return 'skipped'
  }
  return 'success'
}

export function isToolResultSkipped(resultMessage?: Message | null): boolean {
  return resolvePersistedToolOutcome(resultMessage) === 'skipped'
}

export function isToolResultFailed(resultMessage?: Message | null): boolean {
  return resolvePersistedToolOutcome(resultMessage) === 'error'
}

export function getToolCallDisplayStatus(options: {
  status?: ToolCallProgressStatus
  resultMessage?: Message
}): ToolCallDisplayStatus {
  const { status, resultMessage } = options
  if (status === 'running' || status === 'hitl_pending') {
    return status
  }
  if (resultMessage) {
    const outcome = resolvePersistedToolOutcome(resultMessage)
    if (outcome === 'skipped') {
      return 'skipped'
    }
    if (outcome === 'error') {
      return 'error'
    }
    return 'completed'
  }
  if (status === 'completed') {
    return 'completed'
  }
  return status ?? 'completed'
}
