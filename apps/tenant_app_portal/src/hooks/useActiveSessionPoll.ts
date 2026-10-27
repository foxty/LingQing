import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AGENT_RUN_STATUS,
  getActiveRun,
  isActiveRunStatus,
  type ActiveRunResponse,
} from '@/lib/chatApi'

const INITIAL_POLL_MS = 2000
const MAX_POLL_MS = 8000

/** Poll active agent run while a turn may outlive the SSE connection. */
interface UseActiveSessionPollOptions {
  threadId: string | undefined
  enabled?: boolean
  onHistoryRefresh?: () => void | Promise<void>
}

export function useActiveSessionPoll({
  threadId,
  enabled = true,
  onHistoryRefresh,
}: UseActiveSessionPollOptions) {
  const [activeRun, setActiveRun] = useState<ActiveRunResponse | null>(null)
  const [isAgentWorking, setIsAgentWorking] = useState(false)
  const pollTimeoutRef = useRef<number | null>(null)
  const pollDelayRef = useRef(INITIAL_POLL_MS)
  const pollLoopRef = useRef<(() => void) | null>(null)
  const lastActiveRef = useRef<boolean | null>(null)
  const onHistoryRefreshRef = useRef(onHistoryRefresh)

  onHistoryRefreshRef.current = onHistoryRefresh

  const clearPollTimeout = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      window.clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    if (!threadId || !enabled) {
      setActiveRun(null)
      setIsAgentWorking(false)
      lastActiveRef.current = false
      return null
    }

    try {
      const snapshot = await getActiveRun(threadId)
      const wasActive = lastActiveRef.current
      const isActive = isActiveRunStatus(snapshot.run_status ?? null)
      lastActiveRef.current = isActive

      setActiveRun(snapshot)
      setIsAgentWorking(isActive)

      if (isActive && snapshot.run_status === AGENT_RUN_STATUS.RUNNING && wasActive !== isActive) {
        await onHistoryRefreshRef.current?.()
      }

      if (!isActive && wasActive === true) {
        await onHistoryRefreshRef.current?.()
      }

      return snapshot
    } catch (error) {
      console.error('Failed to refresh active run:', error)
      setActiveRun(null)
      setIsAgentWorking(false)
      lastActiveRef.current = false
      return null
    }
  }, [enabled, threadId])

  useEffect(() => {
    clearPollTimeout()
    pollDelayRef.current = INITIAL_POLL_MS
    lastActiveRef.current = null

    if (!threadId || !enabled) {
      setActiveRun(null)
      setIsAgentWorking(false)
      return
    }

    let cancelled = false

    const schedulePoll = (delayMs: number) => {
      pollTimeoutRef.current = window.setTimeout(() => {
        void poll()
      }, delayMs)
    }

    const poll = async () => {
      if (cancelled) return
      const snapshot = await refreshStatus()
      if (cancelled || !snapshot) return

      if (isActiveRunStatus(snapshot.run_status ?? null)) {
        pollDelayRef.current = Math.min(pollDelayRef.current + 1000, MAX_POLL_MS)
        schedulePoll(pollDelayRef.current)
      }
    }

    pollLoopRef.current = () => {
      void poll()
    }
    void poll()

    return () => {
      cancelled = true
      pollLoopRef.current = null
      clearPollTimeout()
    }
  }, [clearPollTimeout, enabled, refreshStatus, threadId])

  const resumeSessionWatch = useCallback(() => {
    pollDelayRef.current = INITIAL_POLL_MS
    pollLoopRef.current?.()
  }, [])

  const notifyStreamStarted = useCallback(() => {
    setIsAgentWorking(true)
    lastActiveRef.current = true
  }, [])

  const notifyStreamFinished = useCallback(() => {
    setIsAgentWorking(false)
    lastActiveRef.current = false
  }, [])

  return {
    activeRun,
    activeSessionId: activeRun?.session_id ?? null,
    isAgentWorking,
    refreshStatus,
    notifyStreamStarted,
    notifyStreamFinished,
    resumeSessionWatch,
  }
}
