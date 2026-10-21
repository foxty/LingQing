/**
 * Thread API client
 */

import api from './api'
import type { ApiChatThread, Artifact } from '@/types'

export type ThreadListScope = 'personal' | 'shared' | 'all'

export interface ThreadAgentRosterEntry {
  agent_id: number
  display_alias: string | null
}

/**
 * Create a new thread
 */
export interface ConversationCreatePayload {
  agent_ids: number[]
  member_user_ids?: number[]
  title?: string | null
  first_message?: string | null
}

export async function createThread(
  agentId: number,
  title?: string,
  firstMessage?: string
): Promise<ApiChatThread> {
  const response = await api.post<ApiChatThread>('/threads', {
    agent_id: agentId,
    title: title || null,
    first_message: firstMessage || null,
  })
  return response.data
}

export async function createConversation(payload: ConversationCreatePayload): Promise<ApiChatThread> {
  const response = await api.post<ApiChatThread>('/threads', {
    agent_ids: payload.agent_ids,
    member_user_ids: payload.member_user_ids,
    title: payload.title ?? null,
    first_message: payload.first_message ?? null,
  })
  return response.data
}

/**
 * List all threads for current user
 */
export async function listThreads(
  agentId?: number,
  scope: ThreadListScope = 'personal'
): Promise<ApiChatThread[]> {
  const params: Record<string, string | number> = { scope }
  if (agentId !== undefined) {
    params.agent_id = agentId
  }
  const response = await api.get<ApiChatThread[]>('/threads', { params })
  return response.data
}

/**
 * Get a specific thread
 */
export async function getThread(threadId: string): Promise<ApiChatThread> {
  const response = await api.get<ApiChatThread>(`/threads/${threadId}`)
  return response.data
}

/**
 * Update thread title
 */
export async function updateThreadTitle(threadId: string, title: string): Promise<ApiChatThread> {
  const response = await api.patch<ApiChatThread>(`/threads/${threadId}`, { title })
  return response.data
}

/**
 * Delete a thread
 */
export async function deleteThread(threadId: string): Promise<void> {
  await api.delete(`/threads/${threadId}`)
}

export interface ComposeMention {
  type: 'user' | 'agent'
  id: number
  label?: string | null
}

export interface ComposeThreadMessageResponse {
  message_id: string
  thread_id: string
  content: string
  author_user_id: number
  created_at: string
  invoke_agent_ids: number[]
}

export async function composeThreadMessage(
  threadId: string,
  payload: {
    content: string
    mentions?: ComposeMention[]
    attached_artifact_ids?: number[]
  }
): Promise<ComposeThreadMessageResponse> {
  const response = await api.post<ComposeThreadMessageResponse>(
    `/threads/${threadId}/messages/compose`,
    payload
  )
  return response.data
}

export async function listThreadAgentRoster(threadId: string): Promise<ThreadAgentRosterEntry[]> {
  const response = await api.get<ThreadAgentRosterEntry[]>(`/threads/${threadId}/agents`)
  return response.data
}

export interface ThreadMemberEntry {
  user_id: number
  role: string
  username?: string | null
}

export async function listThreadMembers(threadId: string): Promise<ThreadMemberEntry[]> {
  const response = await api.get<ThreadMemberEntry[]>(`/threads/${threadId}/members`)
  return response.data
}

export async function addThreadMember(threadId: string, userId: number): Promise<ThreadMemberEntry> {
  const response = await api.post<ThreadMemberEntry>(`/threads/${threadId}/members`, { user_id: userId })
  return response.data
}

export async function removeThreadMember(threadId: string, userId: number): Promise<void> {
  await api.delete(`/threads/${threadId}/members/${userId}`)
}

export type ThreadUserMemberRole = 'owner' | 'member' | 'viewer'

export async function updateThreadMemberRole(
  threadId: string,
  userId: number,
  role: ThreadUserMemberRole
): Promise<ThreadMemberEntry> {
  const response = await api.patch<ThreadMemberEntry>(`/threads/${threadId}/members/${userId}`, {
    role,
  })
  return response.data
}

export async function removeThreadAgent(threadId: string, agentId: number): Promise<void> {
  await api.delete(`/threads/${threadId}/agents/${agentId}`)
}

export async function setThreadPrimaryAgent(threadId: string, agentId: number): Promise<ThreadAgentRosterEntry> {
  const response = await api.patch<ThreadAgentRosterEntry>(`/threads/${threadId}/agents/${agentId}`, {
    is_primary: true,
  })
  return response.data
}

export async function addThreadAgent(
  threadId: string,
  agentId: number
): Promise<ThreadAgentRosterEntry> {
  const response = await api.post<ThreadAgentRosterEntry>(`/threads/${threadId}/agents`, {
    agent_id: agentId,
  })
  return response.data
}

/**
 * List all artifacts for a thread
 */
export async function listThreadArtifacts(
  threadId: string,
  artifactType?: string
): Promise<Artifact[]> {
  const params = artifactType ? { artifact_type: artifactType } : undefined
  const response = await api.get<Artifact[]>(`/threads/${threadId}/artifacts`, { params })
  return response.data
}

/**
 * Unlink an artifact from a thread
 */
export async function unlinkThreadArtifact(threadId: string, artifactId: string): Promise<void> {
  await api.delete(`/threads/${threadId}/artifacts/${artifactId}`)
}
