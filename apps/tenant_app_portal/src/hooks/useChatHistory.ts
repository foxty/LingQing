import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { useAuth } from './useAuth'
import type { Message, SessionMetrics } from '@/types'
import {
  collectPendingSessionIds,
  emptyHistoryPage,
  reduceHistory,
  type ThreadHistoryPage,
} from '@/lib/chatHistoryMerge'
import { getSessionMetrics, getThreadHistory, getToolCallDetail } from '@/lib/chatApi'

export type ThreadLoadError = 'forbidden' | 'not_found' | 'unknown'

function resolveThreadLoadError(error: unknown): ThreadLoadError {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  return 'unknown'
}

function toHistoryPage(response: {
  messages?: Message[]
  next_before_session_id?: string | null
  has_more?: boolean
}): ThreadHistoryPage {
  return {
    messages: response.messages || [],
    nextBeforeSessionId: response.next_before_session_id || undefined,
    hasMore: Boolean(response.has_more),
  }
}

/**
 * Single history store for a thread.
 * Initial page, prepend, and tail refresh all go through reduceHistory.
 */
export function useChatHistory(
  agentId: number | undefined,
  threadId: string | undefined,
  enabled: boolean = true
) {
  const { user } = useAuth()
  const [history, dispatch] = useReducer(reduceHistory, emptyHistoryPage)
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState<ThreadLoadError | null>(null)
  const historyRef = useRef(history)
  const metricsInFlightRef = useRef<Set<string>>(new Set())

  historyRef.current = history

  const canFetch = enabled && !!user && !!agentId && !!threadId

  const loadSessionMetrics = useCallback(async (sessionId: string) => {
    if (metricsInFlightRef.current.has(sessionId)) {
      return
    }
    metricsInFlightRef.current.add(sessionId)
    try {
      const metrics = await getSessionMetrics(sessionId)
      if (metrics) {
        dispatch({ type: 'patch_metrics', sessionId, metrics })
      }
    } catch (metricsError) {
      console.error('Failed to load session metrics:', metricsError)
    } finally {
      metricsInFlightRef.current.delete(sessionId)
    }
  }, [])

  const loadMissingMetrics = useCallback(
    (messages: Message[]) => {
      collectPendingSessionIds(messages).forEach((sessionId) => {
        void loadSessionMetrics(sessionId)
      })
    },
    [loadSessionMetrics]
  )

  const loadInitial = useCallback(async () => {
    if (!threadId || !canFetch) {
      dispatch({ type: 'reset' })
      setLoadError(null)
      setIsLoading(false)
      return
    }

    dispatch({ type: 'reset' })
    setIsLoading(true)
    setLoadError(null)
    try {
      const page = toHistoryPage(
        await getThreadHistory(threadId, {
          sessionLimit: 5,
          includeToolMessages: true,
        })
      )
      dispatch({ type: 'set_initial', page })
      loadMissingMetrics(page.messages)
    } catch (error) {
      setLoadError(resolveThreadLoadError(error))
    } finally {
      setIsLoading(false)
    }
  }, [canFetch, loadMissingMetrics, threadId])

  useEffect(() => {
    setIsLoadingMore(false)
    metricsInFlightRef.current.clear()
    void loadInitial()
  }, [loadInitial])

  const loadMore = useCallback(async () => {
    if (!threadId || !canFetch) return []
    const current = historyRef.current
    if (!current.hasMore || !current.nextBeforeSessionId || isLoadingMore) return []

    setIsLoadingMore(true)
    try {
      const page = toHistoryPage(
        await getThreadHistory(threadId, {
          sessionLimit: 5,
          beforeSessionId: current.nextBeforeSessionId,
          includeToolMessages: true,
        })
      )
      dispatch({ type: 'prepend', page })
      loadMissingMetrics(page.messages)
      return page.messages
    } catch (loadMoreError) {
      console.error('Failed to load more chat history from server:', loadMoreError)
      return []
    } finally {
      setIsLoadingMore(false)
    }
  }, [canFetch, isLoadingMore, loadMissingMetrics, threadId])

  const refreshTail = useCallback(async () => {
    if (!threadId || !canFetch) return []
    const page = toHistoryPage(
      await getThreadHistory(threadId, {
        sessionLimit: 5,
        includeToolMessages: true,
      })
    )
    dispatch({ type: 'refresh_tail', messages: page.messages })
    loadMissingMetrics(page.messages)
    return page.messages
  }, [canFetch, loadMissingMetrics, threadId])

  const updateMessageMetrics = useCallback((sessionId: string, metrics: SessionMetrics) => {
    dispatch({ type: 'patch_metrics', sessionId, metrics })
  }, [])

  return {
    historyMessages: history.messages,
    isLoading,
    isLoadingMore,
    hasMore: history.hasMore,
    loadError,
    loadMore,
    refreshTail,
    refetch: loadInitial,
    updateMessageMetrics,
  }
}

export function useToolCallDetail(
  threadId: string | undefined,
  toolCallId: string,
  sessionId: string | undefined,
  enabled: boolean = false
) {
  return useQuery<Message | null>({
    queryKey: ['toolCallDetail', threadId, toolCallId, sessionId],
    queryFn: async () => {
      if (!threadId || !toolCallId) return null

      try {
        return await getToolCallDetail(threadId, toolCallId, sessionId)
      } catch (error) {
        console.error(`Failed to load tool detail for ${toolCallId}:`, error)
        return null
      }
    },
    enabled: enabled && !!threadId && !!toolCallId,
    staleTime: 5 * 60 * 1000,
  })
}
