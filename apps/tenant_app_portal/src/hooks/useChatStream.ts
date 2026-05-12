import { useCallback, useEffect, useRef, useState } from 'react'
import { handleSSEStream, type SSEMessage } from '@/lib/sse'
import { applyToolEnd, applyToolStart, shouldResetStreamOnThreadChange } from '@/lib/chatStream'
import type { StreamingToolCallState } from '@/lib/chatTurns'
import type { Message } from '@/types'

interface StreamRequest {
  token: string
  body: Record<string, unknown>
}

interface UseChatStreamOptions {
  threadId: string | null
  onEvent?: (data: SSEMessage, threadId: string) => void | Promise<void>
}

export function useChatStream({ threadId, onEvent }: UseChatStreamOptions) {
  const [optimisticMessage, setOptimisticMessage] = useState<Message | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingToolCalls, setStreamingToolCalls] = useState<StreamingToolCallState[]>([])
  const streamingToolCallsRef = useRef<StreamingToolCallState[]>([])
  const streamingToolCallSeqRef = useRef(0)
  const streamAbortRef = useRef<AbortController | null>(null)
  const streamThreadIdRef = useRef<string | null>(null)
  const isStreamingRef = useRef(false)
  const onEventRef = useRef(onEvent)

  onEventRef.current = onEvent

  const resetStreamState = useCallback(() => {
    streamThreadIdRef.current = null
    isStreamingRef.current = false
    setIsStreaming(false)
    setStreamingContent('')
    setStreamingToolCalls([])
    streamingToolCallsRef.current = []
    setOptimisticMessage(null)
  }, [])

  const failStream = useCallback(
    (content: string) => {
      streamThreadIdRef.current = null
      isStreamingRef.current = false
      setOptimisticMessage({
        role: 'ai',
        content,
        timestamp: new Date().toISOString(),
      })
      setIsStreaming(false)
      setStreamingContent('')
      setStreamingToolCalls([])
      streamingToolCallsRef.current = []
    },
    []
  )

  const beginStream = useCallback(
    (optimisticHuman?: Message, activeThreadId?: string | null) => {
      streamThreadIdRef.current = activeThreadId ?? threadId
      isStreamingRef.current = true
      setIsStreaming(true)
      setOptimisticMessage(optimisticHuman ?? null)
      setStreamingContent('')
      setStreamingToolCalls([])
      streamingToolCallsRef.current = []
      streamingToolCallSeqRef.current = 0
      streamAbortRef.current?.abort()
      const abortController = new AbortController()
      streamAbortRef.current = abortController
      return abortController
    },
    [threadId]
  )

  const runStream = useCallback(
    async (request: StreamRequest, activeThreadId: string, abortController: AbortController) => {
      let accumulatedContent = ''

      await handleSSEStream({
        url: '/chat/stream',
        signal: abortController.signal,
        body: request.body,
        token: request.token,
        onMessage: (data: SSEMessage) => {
          switch (data.type) {
            case 'token': {
              if (data.content) {
                accumulatedContent += data.content
                setStreamingContent(accumulatedContent)
              }
              break
            }
            case 'tool_start': {
              setStreamingToolCalls((prev) => {
                const next = applyToolStart(
                  prev,
                  `stream-tool-${streamingToolCallSeqRef.current++}`,
                  data.tool_name || 'tool'
                )
                streamingToolCallsRef.current = next
                return next
              })
              break
            }
            case 'tool_end': {
              setStreamingToolCalls((prev) => {
                const next = applyToolEnd(
                  prev,
                  data.tool_name || 'tool',
                  `stream-tool-${streamingToolCallSeqRef.current++}`
                )
                streamingToolCallsRef.current = next
                return next
              })
              break
            }
            default:
              break
          }

          void onEventRef.current?.(data, activeThreadId)
        },
        onError: (error: Error) => {
          console.error('Streaming error:', error)
          void onEventRef.current?.(
            { type: 'error', message: error.message },
            activeThreadId
          )
        },
      })
    },
    []
  )

  useEffect(() => {
    if (
      !shouldResetStreamOnThreadChange(
        threadId,
        streamThreadIdRef.current,
        isStreamingRef.current
      )
    ) {
      return
    }
    streamAbortRef.current?.abort()
    streamAbortRef.current = null
    resetStreamState()
  }, [threadId, resetStreamState])

  return {
    optimisticMessage,
    isStreaming,
    streamingContent,
    streamingToolCalls,
    beginStream,
    runStream,
    resetStreamState,
    failStream,
  }
}
