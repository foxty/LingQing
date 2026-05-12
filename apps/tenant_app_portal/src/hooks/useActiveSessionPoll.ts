import { useCallback, useEffect, useRef, useState } from 'react'
import { getSessionStatus, SESSION_STATUS, type SessionStatus } from '@/lib/chatApi'

const INITIAL_POLL_MS = 2000
const MAX_POLL_MS = 8000

interface UseActiveSessionPollOptions {
  threadId: string | undefined
  enabled?: boolean
  onHistoryRefresh?: () => void | Promise<void>
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
}

export function useActiveSessionPoll({
  threadId,
  enabled = true,
  onHistoryRefresh,
  onHitlApprovedContinue,
}: UseActiveSessionPollOptions) {
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>(SESSION_STATUS.COMPLETED)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isAgentWorking, setIsAgentWorking] = useState(false)
  const pollTimeoutRef = useRef<number | null>(null)
  const pollDelayRef = useRef(INITIAL_POLL_MS)
  const autoContinueRef = useRef<string | null>(null)
  const lastStatusRef = useRef<SessionStatus | null>(null)
  const onHistoryRefreshRef = useRef(onHistoryRefresh)
  const onHitlApprovedContinueRef = useRef(onHitlApprovedContinue)

  onHistoryRefreshRef.current = onHistoryRefresh
  onHitlApprovedContinueRef.current = onHitlApprovedContinue

  const clearPollTimeout = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      window.clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    if (!threadId || !enabled) {
      setSessionStatus(SESSION_STATUS.COMPLETED)
      setActiveSessionId(null)
      setIsAgentWorking(false)
      lastStatusRef.current = SESSION_STATUS.COMPLETED
      return null
    }

    try {
      const status = await getSessionStatus(threadId)
      const previousStatus = lastStatusRef.current
      lastStatusRef.current = status.status
      setSessionStatus(status.status)
      setActiveSessionId(status.session_id ?? null)

      const statusChanged = previousStatus !== status.status

      if (status.status === SESSION_STATUS.RUNNING) {
        setIsAgentWorking(true)
        if (statusChanged) {
          await onHistoryRefreshRef.current?.()
        }
        return status
      }

      if (status.status === SESSION_STATUS.AWAITING_HITL) {
        setIsAgentWorking(false)
        if (statusChanged) {
          await onHistoryRefreshRef.current?.()
        }
        return status
      }

      if (status.status === SESSION_STATUS.HITL_APPROVED_PENDING_CONTINUE && status.approved_hitl) {
        setIsAgentWorking(false)
        const proposalId = status.approved_hitl.proposal_id
        if (autoContinueRef.current !== proposalId) {
          autoContinueRef.current = proposalId
          await onHitlApprovedContinueRef.current?.(proposalId)
        }
        return status
      }

      if (status.status === SESSION_STATUS.COMPLETED) {
        setIsAgentWorking(false)
        if (statusChanged && previousStatus === SESSION_STATUS.RUNNING) {
          await onHistoryRefreshRef.current?.()
        }
      }

      return status
    } catch (error) {
      console.error('Failed to refresh session status:', error)
      setSessionStatus(SESSION_STATUS.COMPLETED)
      setActiveSessionId(null)
      setIsAgentWorking(false)
      return null
    }
  }, [enabled, threadId])

  useEffect(() => {
    clearPollTimeout()
    pollDelayRef.current = INITIAL_POLL_MS
    autoContinueRef.current = null
    lastStatusRef.current = null

    if (!threadId || !enabled) {
      setSessionStatus(SESSION_STATUS.COMPLETED)
      setActiveSessionId(null)
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
      const status = await refreshStatus()
      if (cancelled || !status) return

      if (status.status === SESSION_STATUS.RUNNING) {
        pollDelayRef.current = Math.min(pollDelayRef.current + 1000, MAX_POLL_MS)
        schedulePoll(pollDelayRef.current)
      }
    }

    void poll()

    return () => {
      cancelled = true
      clearPollTimeout()
    }
  }, [clearPollTimeout, enabled, refreshStatus, threadId])

  const notifyStreamStarted = useCallback(() => {
    setIsAgentWorking(true)
    setSessionStatus(SESSION_STATUS.RUNNING)
    lastStatusRef.current = SESSION_STATUS.RUNNING
  }, [])

  const notifyStreamFinished = useCallback(() => {
    setIsAgentWorking(false)
    setSessionStatus(SESSION_STATUS.COMPLETED)
    lastStatusRef.current = SESSION_STATUS.COMPLETED
  }, [])

  return {
    sessionStatus,
    activeSessionId,
    isAgentWorking,
    refreshStatus,
    notifyStreamStarted,
    notifyStreamFinished,
  }
}
