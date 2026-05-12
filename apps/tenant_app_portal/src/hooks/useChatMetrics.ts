/**
 * useChatMetrics Hook
 * React hook for loading and managing chat metrics
 */

import { useCallback, useState } from 'react'
import {
  getSessionMetrics,
  getSessionToolCalls,
  getToolCallMetrics,
  type SessionMetrics,
  type SessionToolCallsResponse,
  type ToolCallMetrics,
} from '@/lib/chatApi'
import { useNotification } from './useNotification'

export function useChatMetrics() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { showNotification } = useNotification()

  const fetchSessionMetrics = useCallback(
    async (sessionId: string): Promise<SessionMetrics | null> => {
      setLoading(true)
      setError(null)
      try {
        const metrics = await getSessionMetrics(sessionId)
        return metrics
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to load session metrics'
        setError(errorMsg)
        console.error('Failed to load session metrics:', err)
        // Don't show notification for metrics failures (non-critical)
        return null
      } finally {
        setLoading(false)
      }
    },
    [showNotification]
  )

  const fetchSessionToolCalls = useCallback(
    async (sessionId: string): Promise<SessionToolCallsResponse | null> => {
      setLoading(true)
      setError(null)
      try {
        const toolCalls = await getSessionToolCalls(sessionId)
        return toolCalls
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to load tool calls'
        setError(errorMsg)
        console.error('Failed to load tool calls:', err)
        return null
      } finally {
        setLoading(false)
      }
    },
    [showNotification]
  )

  const fetchToolCallMetrics = useCallback(
    async (toolCallId: string, sessionId: string): Promise<ToolCallMetrics | null> => {
      setLoading(true)
      setError(null)
      try {
        const metrics = await getToolCallMetrics(toolCallId, sessionId)
        return metrics
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to load tool metrics'
        setError(errorMsg)
        console.error('Failed to load tool metrics:', err)
        return null
      } finally {
        setLoading(false)
      }
    },
    [showNotification]
  )

  return {
    loading,
    error,
    fetchSessionMetrics,
    fetchSessionToolCalls,
    fetchToolCallMetrics,
  }
}
