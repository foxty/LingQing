/**
 * Artifact search for chat @mention (user-accessible artifacts, any thread).
 */

import api from './api'
import type { Artifact } from '@/types'

export async function searchArtifactsForMention(
  query: string,
  limit: number = 20
): Promise<Artifact[]> {
  const response = await api.get<Artifact[]>('/artifacts/context-picker', {
    params: { query, limit },
  })
  return response.data
}
