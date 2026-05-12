/**
 * SSE (Server-Sent Events) utilities
 * Provides a clean interface for handling streaming responses
 */

import config from './config'
import type { Artifact, HitlPayload, Message } from '@/types'
import i18n from '@/i18n/config'

interface SSEBaseMessage {
  type:
    | 'session_started'
    | 'update_thread_title'
    | 'token'
    | 'tool_start'
    | 'tool_end'
    | 'hitl_request'
    | 'hitl_resolved'
    | 'error'
    | 'done'
}

export interface SSESessionStartedMessage extends SSEBaseMessage {
  type: 'session_started'
  session_id: string
}

export interface SSEUpdateThreadTitleMessage extends SSEBaseMessage {
  type: 'update_thread_title'
  title: string
}

export interface SSETokenMessage extends SSEBaseMessage {
  type: 'token'
  content: string
}

export interface SSEToolStartMessage extends SSEBaseMessage {
  type: 'tool_start'
  tool_name: string
  message: string
}

export interface SSEToolEndMessage extends SSEBaseMessage {
  type: 'tool_end'
  tool_name: string
  message: string
  artifact?: Artifact
}

export interface SSEHitlMessage extends SSEBaseMessage {
  type: 'hitl_request' | 'hitl_resolved'
  proposal_id: string
  thread_id?: string
  tool_name?: string
  message?: string
  hitl: HitlPayload
  ai_message?: Message
}

export interface SSEErrorMessage extends SSEBaseMessage {
  type: 'error'
  message: string
  error_code?: string
}

export interface SSEDoneMessage extends SSEBaseMessage {
  type: 'done'
  session_id?: string
}

export type SSEMessage =
  | SSESessionStartedMessage
  | SSEUpdateThreadTitleMessage
  | SSETokenMessage
  | SSEToolStartMessage
  | SSEToolEndMessage
  | SSEHitlMessage
  | SSEErrorMessage
  | SSEDoneMessage

export interface SSEStreamOptions {
  url: string
  body: any
  token: string
  baseUrl?: string // Optional baseUrl, defaults to config.backendUrl
  signal?: AbortSignal
  onMessage: (message: SSEMessage) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}

/**
 * Handle SSE streaming with proper error handling
 * Follows Single Responsibility Principle
 */
export async function handleSSEStream(options: SSEStreamOptions): Promise<void> {
  const { url, body, token, baseUrl, signal, onMessage, onError, onComplete } = options

  try {
    // Build full URL - handle both relative paths and absolute URLs
    let fullUrl = url
    if (url.startsWith('/')) {
      // Relative path - use baseUrl (defaults to backendUrl)
      const targetBaseUrl = baseUrl || config.backendUrl
      fullUrl = `${targetBaseUrl}${url}`
    }
    // If url already starts with http/https, use it as-is

    const response = await fetch(fullUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      signal,
    })

    if (!response.ok) {
      const errorMessage = await getErrorMessage(response)
      throw new Error(errorMessage)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error(i18n.t('common.failedToLoad'))
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')

      // Keep the last incomplete line in the buffer
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6)) as SSEMessage
            onMessage(data)

            // Stop reading if we receive 'done' or 'error'
            if (data.type === 'done' || data.type === 'error') {
              reader.cancel()
              return
            }
          } catch (e) {
            console.error('Failed to parse SSE message:', e, 'Line:', line)
          }
        }
      }
    }

    onComplete?.()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    console.error('SSE stream error:', error)
    onError?.(error instanceof Error ? error : new Error(String(error)))
  }
}

/**
 * Extract error message from HTTP response
 */
async function getErrorMessage(response: Response): Promise<string> {
  try {
    const errorData = await response.json()
    return errorData.message || errorData.detail || getStatusErrorMessage(response.status)
  } catch {
    return getStatusErrorMessage(response.status)
  }
}

/**
 * Get user-friendly error message based on HTTP status code
 */
function getStatusErrorMessage(status: number): string {
  const statusMessages: Record<number, string> = {
    401: i18n.t('common.failedToLoad'),
    403: i18n.t('common.failedToLoad'),
    404: i18n.t('common.failedToLoad'),
    429: i18n.t('common.failedToLoad'),
    500: i18n.t('common.failedToLoad'),
    503: i18n.t('common.failedToLoad'),
  }

  return statusMessages[status] || `${i18n.t('common.failedToLoad')} (${status})`
}
