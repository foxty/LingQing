import api from './api'
import type { MessageFeedback } from '@/types'

export interface FeedbackStats {
  positive_count: number
  negative_count: number
  total_count: number
  positive_rate: number
  by_agent: Array<{
    agent_id: number
    positive_count: number
    negative_count: number
    total_count: number
  }>
}

export interface FeedbackListItem {
  id: number
  thread_id: string
  session_id?: string | null
  message_id: string
  agent_id: number
  user_id: number
  username?: string | null
  rating: 'positive' | 'negative'
  comment?: string | null
  source: 'portal' | 'slack'
  human_message_preview?: string | null
  ai_message_preview?: string | null
  created_at: string
}

export interface FeedbackListResponse {
  items: FeedbackListItem[]
  next_cursor?: number | null
  has_more: boolean
}

export interface ThreadFeedbackMapResponse {
  thread_id: string
  feedback: Record<string, MessageFeedback>
}

export async function submitMessageFeedback(
  threadId: string,
  messageId: string,
  payload: { rating: 'positive' | 'negative'; comment?: string }
): Promise<MessageFeedback> {
  const { data } = await api.put<MessageFeedback>(
    `/threads/${threadId}/messages/${messageId}/feedback`,
    payload
  )
  return data
}

export async function clearMessageFeedback(threadId: string, messageId: string): Promise<void> {
  await api.delete(`/threads/${threadId}/messages/${messageId}/feedback`)
}

export async function getThreadFeedback(threadId: string): Promise<ThreadFeedbackMapResponse> {
  const { data } = await api.get<ThreadFeedbackMapResponse>(`/threads/${threadId}/feedback`)
  return data
}

export async function getFeedbackStats(params?: {
  agent_id?: number
  source?: string
  from?: string
  to?: string
}): Promise<FeedbackStats> {
  const { data } = await api.get<FeedbackStats>('/feedback/stats', { params })
  return data
}

export async function listFeedback(params?: {
  agent_id?: number
  rating?: string
  source?: string
  from?: string
  to?: string
  cursor?: number
  limit?: number
}): Promise<FeedbackListResponse> {
  const { data } = await api.get<FeedbackListResponse>('/feedback', { params })
  return data
}

export async function exportFeedbackCsv(params?: {
  agent_id?: number
  rating?: string
  source?: string
  from?: string
  to?: string
}): Promise<Blob> {
  const response = await api.get('/feedback/export', {
    params,
    responseType: 'blob',
  })
  return response.data
}
