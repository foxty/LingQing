/**
 * Chat API Service
 * Handles all chat and metrics-related API calls
 */

import api from './api'
import type { Message } from '@/types'

export interface ChatHistoryResponse {
  thread_id: string
  tenant_id: number
  agent_id: number
  user_id: number
  username: string
  total_rounds: number
  messages: Message[]
  message_count: number
  next_before_created_at?: string | null
  next_before_id?: number | null
  next_before_session_id?: string | null
  has_more?: boolean
}

export interface SessionMetrics {
  session_id: string
  total_tokens: {
    input_tokens: number
    output_tokens: number
    total_tokens: number
  }
  duration_ms: number
  llm_call_count: number
  tool_call_count: number
  start_time: string
  end_time: string
}

export interface ToolCallMetrics {
  tool_call_id: string
  tool_name: string
  status: 'success' | 'error'
  duration_ms: number
  input_size?: number
  output_size?: number
  start_time: string
  end_time: string
}

export interface SessionToolCallsResponse {
  session_id: string
  tool_calls: ToolCallMetrics[]
}

export const SESSION_STATUS = {
  RUNNING: 'running',
  AWAITING_HITL: 'awaiting_hitl',
  HITL_APPROVED_PENDING_CONTINUE: 'hitl_approved_pending_continue',
  COMPLETED: 'completed',
} as const

export type SessionStatus = (typeof SESSION_STATUS)[keyof typeof SESSION_STATUS]

export interface PendingHitlInfo {
  proposal_id: string
  tool_name: string
  session_id?: string | null
}

export interface ApprovedHitlInfo {
  proposal_id: string
  tool_name: string
  session_id?: string | null
}

export interface SessionStatusResponse {
  session_id?: string | null
  status: SessionStatus
  has_ai_response: boolean
  pending_hitl?: PendingHitlInfo | null
  approved_hitl?: ApprovedHitlInfo | null
}

/**
 * Get durable session status for polling in-progress agent turns.
 */
export async function getSessionStatus(threadId: string): Promise<SessionStatusResponse> {
  const response = await api.get<SessionStatusResponse>(`/threads/${threadId}/session-status`)
  return response.data
}

/**
 * Get chat history (messages) for a thread
 */
export async function getThreadHistory(
  threadId: string,
  params: {
    sessionLimit?: number
    beforeSessionId?: string
    includeToolMessages?: boolean
  } = {}
): Promise<ChatHistoryResponse> {
  const response = await api.get<ChatHistoryResponse>(`/threads/${threadId}/messages`, {
    params: {
      session_limit: params.sessionLimit ?? 5,
      before_session_id: params.beforeSessionId,
      include_tool_messages: params.includeToolMessages,
    },
  })
  return response.data
}

/**
 * Get aggregated metrics for a session
 */
export async function getSessionMetrics(sessionId: string): Promise<SessionMetrics> {
  const response = await api.get<SessionMetrics>(`/chat/metrics/session/${sessionId}`)
  return response.data
}

/**
 * Get all tool calls for a session
 */
export async function getSessionToolCalls(sessionId: string): Promise<SessionToolCallsResponse> {
  const response = await api.get<SessionToolCallsResponse>(
    `/chat/metrics/session/${sessionId}/tools`
  )
  return response.data
}

/**
 * Get detailed metrics for a specific tool call
 */
export async function getToolCallMetrics(
  toolCallId: string,
  sessionId: string
): Promise<ToolCallMetrics> {
  const response = await api.get<ToolCallMetrics>(
    `/chat/metrics/tool/${toolCallId}?session_id=${sessionId}`
  )
  return response.data
}

/**
 * Lazy load tool call detail from thread history by tool_call_id.
 *
 * Since history rendering can skip tool messages, this helper searches paginated
 * thread messages only when user requests details.
 */
export async function getToolCallDetail(
  threadId: string,
  toolCallId: string,
  sessionId?: string
): Promise<Message | null> {
  try {
    const response = await api.get<Message>(`/threads/${threadId}/tool-calls/${toolCallId}`, {
      params: {
        session_id: sessionId,
      },
    })
    return response.data
  } catch {
    return null
  }
}
