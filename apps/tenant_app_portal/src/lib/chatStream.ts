import type { StreamingToolCallState } from '@/lib/chatTurns'

/** Reset stream state when the active thread changes, except first-message route catch-up. */
export function shouldResetStreamOnThreadChange(
  nextThreadId: string | null,
  streamThreadId: string | null,
  isStreaming: boolean
): boolean {
  if (isStreaming && streamThreadId && nextThreadId === streamThreadId) {
    return false
  }
  return true
}

/** Show the in-progress AI turn while SSE is active or session poll reports running. */
export function shouldShowStreamingTurn(isStreaming: boolean, isBusy: boolean): boolean {
  return isStreaming || isBusy
}

/** First-message sends must navigate only after stream start is registered. */
export function shouldNavigateAfterStreamStart(createdThreadId: string | null): boolean {
  return createdThreadId !== null
}

export function applyToolStart(
  tools: StreamingToolCallState[],
  nextId: string,
  toolName: string
): StreamingToolCallState[] {
  return [
    ...tools,
    {
      id: nextId,
      name: toolName,
      args: {},
      status: 'running',
      startedAt: new Date().toISOString(),
    },
  ]
}

export function applyToolEnd(
  tools: StreamingToolCallState[],
  toolName: string,
  fallbackId: string
): StreamingToolCallState[] {
  const endedAt = new Date().toISOString()
  const reverseIndex = [...tools]
    .reverse()
    .findIndex((item) => item.name === toolName && item.status === 'running')

  if (reverseIndex === -1) {
    return [
      ...tools,
      {
        id: fallbackId,
        name: toolName,
        args: {},
        status: 'completed',
        endedAt,
      },
    ]
  }

  const index = tools.length - 1 - reverseIndex
  return tools.map((item, itemIndex) =>
    itemIndex === index ? { ...item, status: 'completed', endedAt } : item
  )
}
