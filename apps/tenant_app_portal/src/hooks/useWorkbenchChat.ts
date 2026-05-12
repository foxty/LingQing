import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { useActiveSessionPoll } from '@/hooks/useActiveSessionPoll'
import { useChatHistory } from '@/hooks/useChatHistory'
import { useChatStream } from '@/hooks/useChatStream'
import { shouldNavigateAfterStreamStart } from '@/lib/chatStream'
import {
  getLatestMessageTimestamp,
  getLatestSessionWindow,
  toTimestampMs,
} from '@/lib/workbenchChatUtils'
import type { SSEMessage } from '@/lib/sse'
import type { Artifact, ContextResource, Message } from '@/types'

interface UseWorkbenchChatOptions {
  agentId: number
  threadId: string | null
  createThread: (params: { agentId: number }) => Promise<{ id: string }>
  navigate: (path: string, options?: { replace?: boolean }) => void
  updateThreadTitle: (params: { threadId: string; title: string }) => void
  reloadArtifacts: () => Promise<Artifact[]>
  selectArtifact: (artifact: Artifact) => void
  setArtifactsPanelVisible: (visible: boolean) => void
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
}: UseWorkbenchChatOptions) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const latestMessageTimestampBeforeSendRef = useRef(0)
  const handleHitlApprovedContinueRef = useRef<(proposalId: string) => Promise<void>>(async () => {})
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
    resetStreamState,
    failStream,
  } = useChatStream({
    threadId,
    onEvent: (data, activeThreadId) => handleStreamEventRef.current(data, activeThreadId),
  })

  const { isAgentWorking, notifyStreamStarted, notifyStreamFinished } = useActiveSessionPoll({
    threadId: threadId || undefined,
    enabled: !!threadId,
    onHistoryRefresh: async () => {
      await refreshTail()
    },
    onHitlApprovedContinue: (proposalId) => handleHitlApprovedContinueRef.current(proposalId),
  })

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
              setArtifactsPanelVisible(true)
              selectArtifact(artifactsInLatestSession[0])
            }
          }
        } finally {
          resetStreamState()
        }
        return
      }
      case 'error': {
        console.error('Stream error:', data.message)
        notifyStreamFinished()
        failStream(t('workbench.createThreadFailed'))
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
      selectedResources: ContextResource[],
      options?: {
        hidden?: boolean
        hitlProposalId?: string
        hitlAction?: 'approved'
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
        failStream(t('workbench.createThreadFailed'))
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
                context_resources: selectedResources,
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
              selected_resource_ids: selectedResources.map((r) => ({
                resource_type: r.resource_type,
                resource_id: r.resource_id,
              })),
              hitl_proposal_id: options?.hitlProposalId || null,
              hitl_action: options?.hitlAction || null,
            },
          },
          activeThreadId,
          abortController
        )
      } catch (error) {
        console.error('Error sending message:', error)
        notifyStreamFinished()
        resetStreamState()
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
      resetStreamState,
      runStream,
      showWorkingIndicator,
      t,
      threadId,
      user,
    ]
  )

  const handleHitlApprovedContinue = useCallback(
    async (proposalId: string) => {
      await handleSendMessage('continue hitl workflow', [], {
        hidden: true,
        hitlProposalId: proposalId,
        hitlAction: 'approved',
      })
    },
    [handleSendMessage]
  )

  const handleHitlRejected = useCallback(async () => {
    notifyStreamFinished()
    await refreshTail()
  }, [notifyStreamFinished, refreshTail])

  useEffect(() => {
    handleHitlApprovedContinueRef.current = handleHitlApprovedContinue
  }, [handleHitlApprovedContinue])

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
