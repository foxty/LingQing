/**
 * Thread API client
 */

import api from './api'
import type { ApiChatThread, Artifact } from '@/types'

/**
 * Create a new thread
 */
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

/**
 * List all threads for current user
 */
export async function listThreads(agentId?: number): Promise<ApiChatThread[]> {
  const params = agentId !== undefined ? { agent_id: agentId } : undefined
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
