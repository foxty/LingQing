/**
 * Context Resources API Service
 * Lightweight keyword search for @mention resource picker.
 */

import api from './api'
import type { ContextResource } from '@/types'

export interface ContextResourceSearchResponse {
  items: ContextResource[]
}

/**
 * Search all context-capable resources by keyword.
 *
 * @param query - Search term; empty string lists recent resources for @mention browse
 * @param limit - Max results per resource type (default 10)
 */
export async function searchContextResources(
  query: string,
  limit: number = 10
): Promise<ContextResourceSearchResponse> {
  const response = await api.get<ContextResourceSearchResponse>(
    '/context-resources/search',
    {
      params: { query, limit },
    }
  )
  return response.data
}
