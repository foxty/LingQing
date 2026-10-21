/**
 * Chat Area Component
 * Handles chat UI, message display, and user input
 * Pure presentation component with local UI state management
 */

import './workbenchChatI18n'
import ChatComposer from './ChatComposer'
import ChatThreadEmptyState from './ChatThreadEmptyState'
import MessageList from './MessageList'
import { useTranslation } from 'react-i18next'
import type { ThinkingEffortOption } from '@/lib/chatApi'
import { shouldShowStreamingTurn } from '@/lib/chatStream'
import { buildStreamingTurn, StreamingToolCallState } from '@/lib/chatTurns'
import type { ThreadLoadError } from '@/hooks/useChatHistory'
import { useChatScroll } from '@/hooks/useChatScroll'
import type { ArtifactsAutoOpenPreference, ThinkingEffort } from '@/lib/userPreferencesTypes'
import type { ComposeMentionPayload } from '@/lib/participantMention'
import type { AttachedArtifact, Message } from '@/types'
import { useMemo } from 'react'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  isBusy?: boolean
  streamingContent: string
  streamingToolCalls?: StreamingToolCallState[]
  streamingAgentId?: number | null
  sendKeyPreference: 'enter' | 'ctrl-enter'
  artifactsAutoOpen: ArtifactsAutoOpenPreference
  thinkingEffort: ThinkingEffort
  thinkingEffortOptions?: ThinkingEffortOption[]
  thinkingEffortControlEnabled?: boolean
  agentModelId?: string
  agentProfileName?: string
  threadId?: string
  isLoadingHistory?: boolean
  threadLoadError?: ThreadLoadError | null
  agentAccessRevoked?: boolean
  exampleQuestions?: string[]

  hasMore?: boolean
  isLoadingMore?: boolean
  onLoadMore?: () => Promise<void>

  onSendMessage: (
    message: string,
    resources: AttachedArtifact[],
    mentions?: ComposeMentionPayload[]
  ) => void
  onSendKeyPreferenceChange: (value: 'enter' | 'ctrl-enter') => void
  onArtifactsAutoOpenChange: (value: ArtifactsAutoOpenPreference) => void
  onThinkingEffortChange: (value: ThinkingEffort) => void
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
  isSharedThread?: boolean
  rosterAgentOptions?: { id: number; label: string }[]
  memberUserIds?: number[]
  memberUserLabels?: { id: number; label: string }[]
  currentUserId?: number
  userNameById?: Map<number, string>
  agentNameById?: Map<number, string>
  fallbackAgentId?: number
}

export default function ChatArea({
  messages,
  isStreaming,
  isBusy = false,
  streamingContent,
  streamingToolCalls = [],
  streamingAgentId = null,
  sendKeyPreference,
  artifactsAutoOpen,
  thinkingEffort,
  thinkingEffortOptions = [],
  thinkingEffortControlEnabled = true,
  agentModelId = '',
  agentProfileName = '',
  threadId,
  isLoadingHistory = false,
  threadLoadError = null,
  agentAccessRevoked = false,
  exampleQuestions = [],
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
  onSendMessage,
  onSendKeyPreferenceChange,
  onArtifactsAutoOpenChange,
  onThinkingEffortChange,
  onHitlApprovedContinue,
  onHitlRejected,
  isSharedThread = false,
  rosterAgentOptions = [],
  memberUserIds = [],
  memberUserLabels = [],
  currentUserId,
  userNameById,
  agentNameById,
  fallbackAgentId,
}: ChatAreaProps) {
  const { t } = useTranslation()

  const { containerRef, onScroll, pinToBottom } = useChatScroll({
    threadId,
    messages,
    followContent: streamingContent,
    hasMore,
    isLoadingMore,
    onLoadMore,
  })

  const streamingTurn = shouldShowStreamingTurn(isStreaming, isBusy)
    ? buildStreamingTurn({
        content: streamingContent,
        toolCalls: streamingToolCalls,
      })
    : null

  const inputDisabled = useMemo(
    () =>
      isBusy ||
      Boolean(threadLoadError) ||
      agentAccessRevoked ||
      (isLoadingHistory && Boolean(threadId)),
    [agentAccessRevoked, isBusy, isLoadingHistory, threadId, threadLoadError]
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={containerRef}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6"
        onScroll={onScroll}
      >
        {hasMore ? (
          <div className="flex justify-center py-1 text-xs text-muted-foreground">
            {isLoadingMore ? t('common.loading') : null}
          </div>
        ) : null}

        {messages.length === 0 && !isStreaming ? (
          <ChatThreadEmptyState
            threadId={threadId}
            isLoadingHistory={isLoadingHistory}
            threadLoadError={threadLoadError}
            agentAccessRevoked={agentAccessRevoked}
            exampleQuestions={exampleQuestions}
            inputDisabled={inputDisabled}
            onSendExample={(question) => onSendMessage(question, [])}
          />
        ) : null}

        <MessageList
          messages={messages}
          threadId={threadId}
          streamingTurn={streamingTurn}
          currentUserId={currentUserId}
          userNameById={userNameById}
          agentNameById={agentNameById}
          streamingAgentId={streamingAgentId}
          fallbackAgentId={fallbackAgentId}
          onHitlApprovedContinue={onHitlApprovedContinue}
          onHitlRejected={onHitlRejected}
        />
      </div>

      <ChatComposer
        isBusy={isBusy}
        threadId={threadId}
        isLoadingHistory={isLoadingHistory}
        threadLoadError={threadLoadError}
        agentAccessRevoked={agentAccessRevoked}
        showAgentAccessRevokedNotice={agentAccessRevoked && messages.length > 0}
        sendKeyPreference={sendKeyPreference}
        artifactsAutoOpen={artifactsAutoOpen}
        thinkingEffort={thinkingEffort}
        thinkingEffortOptions={thinkingEffortOptions}
        thinkingEffortControlEnabled={thinkingEffortControlEnabled}
        agentModelId={agentModelId}
        agentProfileName={agentProfileName}
        onSendMessage={onSendMessage}
        onSendKeyPreferenceChange={onSendKeyPreferenceChange}
        onArtifactsAutoOpenChange={onArtifactsAutoOpenChange}
        onThinkingEffortChange={onThinkingEffortChange}
        onBeforeSend={pinToBottom}
        isSharedThread={isSharedThread}
        rosterAgentOptions={rosterAgentOptions}
        memberUserIds={memberUserIds}
        memberUserLabels={memberUserLabels}
      />
    </div>
  )
}
