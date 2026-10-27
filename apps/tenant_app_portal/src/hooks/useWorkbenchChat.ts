import { useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { useActiveSessionPoll } from '@/hooks/useActiveSessionPoll'
import { useNotification } from '@/hooks/useNotification'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useChatStream } from '@/hooks/useChatStream'
import { shouldNavigateAfterStreamStart } from '@/lib/chatStream'
import { isActiveRunStatus } from '@/lib/chatApi'
import { isStreamTransportError } from '@/lib/streamErrors'
import type { ArtifactsAutoOpenPreference, ThinkingEffort } from '@/lib/userPreferencesTypes'
import {
  getLatestMessageTimestamp,
  getLatestSessionWindow,
  shouldAutoOpenArtifactsPanel,
  toTimestampMs,
} from '@/lib/workbenchChatUtils'
import type { SSEMessage } from '@/lib/sse'
import type { Artifact, AttachedArtifact, Message } from '@/types'

interface UseWorkbenchChatOptions {
  agentId: number
  threadId: string | null
  createThread: (params: { agentId: number }) => Promise<{ id: string }>
  navigate: (path: string, options?: { replace?: boolean }) => void
  updateThreadTitle: (params: { threadId: string; title: string }) => void
  reloadArtifacts: () => Promise<Artifact[]>
  selectArtifact: (artifact: Artifact) => void
  setArtifactsPanelVisible: (visible: boolean) => void
  artifactsAutoOpen: ArtifactsAutoOpenPreference
  thinkingEffort: ThinkingEffort
  isArtifactsPanelDismissedForThread: () => boolean
  isArtifactsPanelVisible: () => boolean
  onNewArtifactsWhilePanelClosed: (artifacts: Artifact[]) => void
}

function withOptimisticMessage(history: Message[], optimistic: Message | null): Message[] {
  if (!optimistic) return history
  if (optimistic.role === 'human') {
    const latestHuman = [...history].reverse().find((msg) => msg.role === 'human')
    if (latestHuman?.content === optimistic.content) {
      return history
    }
  }
  return [...history, optimistic]
}

export function useWorkbenchChat({
  agentId,
  threadId,
  createThread,
  navigate,
  updateThreadTitle,
  reloadArtifacts,
  selectArtifact,
  setArtifactsPanelVisible,
  artifactsAutoOpen,
  thinkingEffort,
  isArtifactsPanelDismissedForThread,
  isArtifactsPanelVisible,
  onNewArtifactsWhilePanelClosed,
}: UseWorkbenchChatOptions) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { showError } = useNotification()
  const latestMessageTimestampBeforeSendRef = useRef(0)
  const hitlContinueProposalRef = useRef<string | null>(null)
  const handleStreamEventRef = useRef<(data: SSEMessage, activeThreadId: string) => Promise<void>>(
    async () => {}
  )

  const {
    historyMessages,
    isLoading: historyLoading,
    hasMore,
    isLoadingMore,
    loadError: threadLoadError,
    loadMore,
    refreshTail,
  } = useChatHistory(agentId, threadId || undefined, !!threadId)

  const {
    optimisticMessage,
    isStreaming,
    streamingContent,
    streamingToolCalls,
    beginStream,
    runStream,
    runHitlResumeStream,
    resetStreamState,
    failStream,
  } = useChatStream({
    threadId,
    onEvent: (data, activeThreadId) => handleStreamEventRef.current(data, activeThreadId),
  })

  const {
    isAgentWorking,
    notifyStreamStarted,
    notifyStreamFinished,
    refreshStatus,
    resumeSessionWatch,
  } = useActiveSessionPoll({
    threadId: threadId || undefined,
    enabled: !!threadId,
    onHistoryRefresh: async () => {
      await refreshTail()
    },
  })

  const recoverFromStreamTransportLoss = useCallback(async () => {
    resetStreamState()
    const status = await refreshStatus()
    if (isActiveRunStatus(status?.run_status ?? null)) {
      resumeSessionWatch()
      return
    }
    notifyStreamFinished()
    failStream(t('workbench.streamDisconnected'))
    void refreshTail()
  }, [
    failStream,
    notifyStreamFinished,
    refreshStatus,
    refreshTail,
    resetStreamState,
    resumeSessionWatch,
    t,
  ])

  handleStreamEventRef.current = async (data, activeThreadId) => {
    switch (data.type) {
      case 'session_started': {
        await refreshTail()
        return
      }
      case 'update_thread_title': {
        if (data.title) {
          updateThreadTitle({ threadId: activeThreadId, title: data.title })
        }
        return
      }
      case 'done': {
        notifyStreamFinished()
        try {
          const [reloadedArtifacts, latestMessages] = await Promise.all([
            reloadArtifacts(),
            refreshTail(),
          ])
          const latestSessionWindow = getLatestSessionWindow(latestMessages)
          if (
            latestSessionWindow &&
            latestSessionWindow.endMs > latestMessageTimestampBeforeSendRef.current
          ) {
            const artifactsInLatestSession = reloadedArtifacts.filter((artifact) => {
              const createdMs = toTimestampMs(artifact.created_at)
              if (!createdMs) return false
              return (
                createdMs >= latestSessionWindow.startMs && createdMs <= latestSessionWindow.endMs
              )
            })
            if (artifactsInLatestSession.length > 0) {
              const primary = artifactsInLatestSession[0]
              const shouldOpen = shouldAutoOpenArtifactsPanel(
                artifactsAutoOpen,
                isArtifactsPanelDismissedForThread()
              )
              if (shouldOpen) {
                setArtifactsPanelVisible(true)
                selectArtifact(primary)
              } else if (isArtifactsPanelVisible()) {
                selectArtifact(primary)
              } else {
                onNewArtifactsWhilePanelClosed(artifactsInLatestSession)
              }
            }
          }
        } finally {
          resetStreamState()
        }
        return
      }
      case 'error': {
        console.error('Stream error:', data.message)
        if (isStreamTransportError(data.message ?? '')) {
          await recoverFromStreamTransportLoss()
          return
        }
        if (data.error_code === 'THREAD_BUSY') {
          notifyStreamFinished()
          resetStreamState()
          showError(data.message?.trim() || t('workbench.threadBusy'))
          await refreshStatus()
          void refreshTail()
          return
        }
        notifyStreamFinished()
        failStream(data.message?.trim() || t('workbench.streamFailed'))
        void refreshTail()
        return
      }
      default:
        return
    }
  }

  const displayMessages = useMemo(
    () => withOptimisticMessage(historyMessages, optimisticMessage),
    [historyMessages, optimisticMessage]
  )

  const showWorkingIndicator = isStreaming || isAgentWorking

  const handleSendMessage = useCallback(
    async (
      messageText: string,
      selectedResources: AttachedArtifact[],
      options?: {
        hidden?: boolean
      }
    ) => {
      if ((!options?.hidden && !messageText.trim()) || showWorkingIndicator || !user) return

      let activeThreadId = threadId
      let createdThreadId: string | null = null
      if (!activeThreadId) {
        try {
          const newThread = await createThread({ agentId })
          activeThreadId = newThread.id
          createdThreadId = newThread.id
        } catch (error) {
          console.error('Failed to create thread:', error)
          failStream(t('workbench.createThreadFailed'))
          return
        }
      }

      const token = localStorage.getItem('token')
      if (!token) {
        failStream(t('workbench.authRequired'))
        return
      }

      latestMessageTimestampBeforeSendRef.current = getLatestMessageTimestamp(historyMessages)
      notifyStreamStarted()
      const userInput = options?.hidden ? messageText : messageText.trim()
      const abortController = beginStream(
        options?.hidden
          ? undefined
          : {
              role: 'human',
              content: userInput,
              timestamp: new Date().toISOString(),
              message_metadata: {
                attached_artifacts: selectedResources,
              },
            },
        activeThreadId
      )

      if (shouldNavigateAfterStreamStart(createdThreadId)) {
        navigate(`/workbench/${createdThreadId}`, { replace: true })
      }

      try {
        await runStream(
          {
            token,
            body: {
              tenant_id: user.tenantId,
              agent_id: agentId,
              message: {
                role: 'human',
                content: userInput,
              },
              thread_id: activeThreadId,
              selected_artifact_ids: selectedResources.map((r) => r.artifact_id),
              thinking_effort: thinkingEffort || null,
            },
          },
          activeThreadId,
          abortController
        )
      } catch (error) {
        console.error('Error sending message:', error)
        const message = error instanceof Error ? error.message : String(error)
        if (isStreamTransportError(message)) {
          await recoverFromStreamTransportLoss()
          return
        }
        notifyStreamFinished()
        failStream(message.trim() || t('workbench.streamFailed'))
      }
    },
    [
      agentId,
      beginStream,
      createThread,
      failStream,
      historyMessages,
      navigate,
      notifyStreamFinished,
      notifyStreamStarted,
      recoverFromStreamTransportLoss,
      resetStreamState,
      runStream,
      runHitlResumeStream,
      showWorkingIndicator,
      thinkingEffort,
      t,
      threadId,
      user,
    ]
  )

  const handleHitlApprovedContinue = useCallback(
    async (proposalId: string) => {
      if (hitlContinueProposalRef.current === proposalId || !threadId || !user) {
        return
      }
      hitlContinueProposalRef.current = proposalId
      const token = localStorage.getItem('token')
      if (!token) {
        failStream(t('workbench.authRequired'))
        hitlContinueProposalRef.current = null
        return
      }
      notifyStreamStarted()
      const abortController = beginStream(undefined, threadId)
      try {
        await runHitlResumeStream(proposalId, threadId, token, abortController)
      } catch (error) {
        console.error('HITL resume stream failed:', error)
        const message = error instanceof Error ? error.message : String(error)
        if (isStreamTransportError(message)) {
          await recoverFromStreamTransportLoss()
          return
        }
        notifyStreamFinished()
        resetStreamState()
      } finally {
        notifyStreamFinished()
        await refreshTail()
        if (hitlContinueProposalRef.current === proposalId) {
          hitlContinueProposalRef.current = null
        }
      }
    },
    [
      beginStream,
      failStream,
      notifyStreamFinished,
      recoverFromStreamTransportLoss,
      refreshTail,
      resetStreamState,
      runHitlResumeStream,
      t,
      threadId,
      user,
    ]
  )

  const handleHitlRejected = useCallback(async () => {
    notifyStreamFinished()
    await refreshTail()
  }, [notifyStreamFinished, refreshTail])

  return {
    displayMessages,
    historyLoading,
    threadLoadError,
    hasMore,
    isLoadingMore,
    handleLoadMore: async () => {
      await loadMore()
    },
    showWorkingIndicator,
    isStreaming,
    streamingContent,
    streamingToolCalls,
    handleSendMessage,
    handleHitlApprovedContinue,
    handleHitlRejected,
  }
}
