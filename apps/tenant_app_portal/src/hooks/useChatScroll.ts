import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import { captureScrollAnchor, restoreScrollAnchor, type ScrollAnchor } from '@/lib/chatScroll'

interface UseChatScrollOptions {
  threadId?: string
  messages: unknown
  followContent?: unknown
  hasMore: boolean
  isLoadingMore: boolean
  onLoadMore?: () => Promise<void>
}

export function useChatScroll({
  threadId,
  messages,
  followContent,
  hasMore,
  isLoadingMore,
  onLoadMore,
}: UseChatScrollOptions) {
  const containerRef = useRef<HTMLDivElement>(null)
  const shouldFollowOutputRef = useRef(true)
  const pendingScrollAnchorRef = useRef<ScrollAnchor | null>(null)
  const isRestoringScrollRef = useRef(false)

  const scrollToBottom = useCallback(() => {
    const container = containerRef.current
    if (!container) {
      return
    }
    container.scrollTop = container.scrollHeight
  }, [])

  const pinToBottom = useCallback(() => {
    shouldFollowOutputRef.current = true
  }, [])

  useEffect(() => {
    shouldFollowOutputRef.current = true
    pendingScrollAnchorRef.current = null
    isRestoringScrollRef.current = false
  }, [threadId])

  useLayoutEffect(() => {
    const container = containerRef.current
    const anchor = pendingScrollAnchorRef.current
    if (!container || !anchor) {
      return
    }

    isRestoringScrollRef.current = true
    restoreScrollAnchor(container, anchor)
    pendingScrollAnchorRef.current = null
    shouldFollowOutputRef.current = false
    requestAnimationFrame(() => {
      isRestoringScrollRef.current = false
    })
  }, [messages])

  useEffect(() => {
    if (isRestoringScrollRef.current || isLoadingMore || !shouldFollowOutputRef.current) {
      return
    }
    scrollToBottom()
  }, [messages, followContent, isLoadingMore, scrollToBottom])

  const loadOlder = useCallback(async () => {
    if (!onLoadMore || !containerRef.current || !hasMore || isLoadingMore) return

    shouldFollowOutputRef.current = false
    pendingScrollAnchorRef.current = captureScrollAnchor(containerRef.current)
    await onLoadMore()
  }, [hasMore, isLoadingMore, onLoadMore])

  const onScroll = useCallback(() => {
    const container = containerRef.current
    if (!container || isRestoringScrollRef.current) return

    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <= 24
    shouldFollowOutputRef.current = isAtBottom

    if (isLoadingMore || !hasMore || container.scrollTop > 0) {
      return
    }

    void loadOlder()
  }, [hasMore, isLoadingMore, loadOlder])

  return {
    containerRef,
    onScroll,
    pinToBottom,
  }
}
