import type { Message, MessageFeedback, SessionMetrics } from '@/types'

export interface ThreadHistoryPage {
  messages: Message[]
  nextBeforeSessionId?: string
  hasMore: boolean
}

export const emptyHistoryPage: ThreadHistoryPage = {
  messages: [],
  hasMore: false,
}

export type HistoryAction =
  | { type: 'reset' }
  | { type: 'set_initial'; page: ThreadHistoryPage }
  | { type: 'prepend'; page: ThreadHistoryPage }
  | { type: 'refresh_tail'; messages: Message[] }
  | { type: 'patch_metrics'; sessionId: string; metrics: SessionMetrics }
  | { type: 'patch_feedback'; feedbackByMessageId: Record<string, MessageFeedback> }

function isSessionMetrics(metrics: Message['metrics']): metrics is SessionMetrics {
  return (
    typeof metrics === 'object' &&
    metrics !== null &&
    'session_id' in metrics &&
    'total_tokens' in metrics
  )
}

export function collectMetricsBySession(messages: Message[]): Map<string, SessionMetrics> {
  const metricsBySession = new Map<string, SessionMetrics>()
  for (const msg of messages) {
    if (msg.role === 'ai' && msg.session_id && isSessionMetrics(msg.metrics)) {
      metricsBySession.set(msg.session_id, msg.metrics)
    }
  }
  return metricsBySession
}

export function mergePreservedSessionMetrics(
  messages: Message[],
  metricsBySession: Map<string, SessionMetrics>
): Message[] {
  if (metricsBySession.size === 0) {
    return messages
  }

  return messages.map((msg) => {
    if (msg.role !== 'ai' || msg.metrics || !msg.session_id) {
      return msg
    }
    const preserved = metricsBySession.get(msg.session_id)
    return preserved ? { ...msg, metrics: preserved } : msg
  })
}

export function applyFeedbackToHistory(
  messages: Message[],
  feedbackByMessageId: Record<string, MessageFeedback>
): Message[] {
  if (Object.keys(feedbackByMessageId).length === 0) {
    return messages
  }
  return messages.map((msg) => {
    if (!msg.message_id) {
      return msg
    }
    const feedback = feedbackByMessageId[msg.message_id]
    return feedback ? { ...msg, feedback } : msg
  })
}

export function applySessionMetricsToHistory(
  messages: Message[],
  sessionId: string,
  metrics: Message['metrics']
): Message[] {
  return messages.map((msg) =>
    msg.role === 'ai' && msg.session_id === sessionId && !msg.metrics
      ? { ...msg, metrics }
      : msg
  )
}

export function findOldestSessionId(messages: Message[]): string | undefined {
  for (const message of messages) {
    if (message.session_id) {
      return message.session_id
    }
  }
  return undefined
}

export function mergeLatestPageIntoCachedHistory(
  cachedMessages: Message[],
  latestPageMessages: Message[]
): Message[] {
  if (cachedMessages.length === 0) {
    return latestPageMessages
  }
  if (latestPageMessages.length === 0) {
    return cachedMessages
  }

  const latestPageOldestSessionId = findOldestSessionId(latestPageMessages)
  if (!latestPageOldestSessionId) {
    return latestPageMessages
  }

  const overlapIndex = cachedMessages.findIndex(
    (message) => message.session_id === latestPageOldestSessionId
  )

  if (overlapIndex === -1) {
    return [...cachedMessages, ...latestPageMessages]
  }

  return [...cachedMessages.slice(0, overlapIndex), ...latestPageMessages]
}

export function collectPendingSessionIds(messages: Message[]): string[] {
  const pending = new Set<string>()
  for (const msg of messages) {
    if (msg.role === 'ai' && msg.session_id && !msg.metrics) {
      pending.add(msg.session_id)
    }
  }
  return [...pending]
}

export function reduceHistory(
  state: ThreadHistoryPage,
  action: HistoryAction
): ThreadHistoryPage {
  switch (action.type) {
    case 'reset':
      return emptyHistoryPage
    case 'set_initial':
      return {
        messages: mergePreservedSessionMetrics(
          action.page.messages,
          collectMetricsBySession(state.messages)
        ),
        nextBeforeSessionId: action.page.nextBeforeSessionId,
        hasMore: action.page.hasMore,
      }
    case 'prepend':
      return {
        messages: [
          ...mergePreservedSessionMetrics(
            action.page.messages,
            collectMetricsBySession(state.messages)
          ),
          ...state.messages,
        ],
        nextBeforeSessionId: action.page.nextBeforeSessionId,
        hasMore: action.page.hasMore,
      }
    case 'refresh_tail':
      return {
        ...state,
        messages: mergePreservedSessionMetrics(
          mergeLatestPageIntoCachedHistory(state.messages, action.messages),
          collectMetricsBySession(state.messages)
        ),
      }
    case 'patch_metrics':
      return {
        ...state,
        messages: applySessionMetricsToHistory(state.messages, action.sessionId, action.metrics),
      }
    case 'patch_feedback':
      return {
        ...state,
        messages: applyFeedbackToHistory(state.messages, action.feedbackByMessageId),
      }
    default:
      return state
  }
}
