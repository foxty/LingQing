/**
 * Chat Area Component
 * Handles chat UI, message display, and user input
 * Pure presentation component with local UI state management
 */

import MessageList from './MessageList'
import ContextChipsBar from './ContextChipsBar'
import ResourcePickerPopover, {
  type ResourcePickerPopoverHandle,
} from './ResourcePickerPopover'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  workbench: {
    startChat: 'Start a conversation',
    startChatDesc: 'Ask a question or describe a task to get started',
    threadNotAccessible: 'Conversation not accessible',
    threadNotAccessibleDesc: 'This conversation belongs to another user. Select one of your conversations or start a new one.',
    threadNotFound: 'Conversation not found',
    threadNotFoundDesc: 'This conversation may have been deleted or is no longer available.',
    threadLoadFailed: 'Failed to load conversation',
    threadLoadFailedDesc: 'Something went wrong while loading this conversation. Try again or start a new one.',
    agentAccessRevoked: 'You no longer have access to this agent',
    agentAccessRevokedDesc: 'This conversation is no longer listed. Start a new one with an agent you can use.',
    messagePlaceholderEnter: 'Type a message... (Enter to send, @ to attach artifacts)',
    messagePlaceholderCtrlEnter: 'Type a message... (Ctrl+Enter to send, @ to attach artifacts)',
    enterToSend: 'Enter to send',
    ctrlEnterToSend: 'Ctrl+Enter to send',
    artifactsAutoOpen: 'Artifacts panel',
    artifactsAutoOpenNever: 'Stay closed (badge + toast)',
    artifactsAutoOpenOnNew: 'Open for new artifacts',
    artifactsAutoOpenAlways: 'Always open for new artifacts',
    send: 'Send',
    thinkingEffort: 'Reasoning effort',
    thinkingNone: 'Off (default)',
    thinkingLow: 'Low',
    thinkingMedium: 'Medium',
    thinkingHigh: 'High',
    thinkingEffortUnavailable:
      'Not available for this agent’s model (catalog has no reasoning control for the resolved profile).',
    boundModel: 'Model',
    boundProfile: 'Profile',
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  workbench: {
    startChat: '开始对话',
    startChatDesc: '提出问题或描述任务以开始',
    threadNotAccessible: '无法访问此对话',
    threadNotAccessibleDesc: '此对话属于其他用户。请选择您自己的对话或开始新对话。',
    threadNotFound: '未找到对话',
    threadNotFoundDesc: '此对话可能已被删除或不再可用。',
    threadLoadFailed: '加载对话失败',
    threadLoadFailedDesc: '加载此对话时出错。请重试或开始新对话。',
    agentAccessRevoked: '你已没有此智能体的访问权限',
    agentAccessRevokedDesc: '此对话已不再列出。请改用你仍可访问的智能体开始新对话。',
    messagePlaceholderEnter: '输入消息...（Enter 发送，@附加产物）',
    messagePlaceholderCtrlEnter: '输入消息...（Ctrl+Enter 发送，@附加产物）',
    enterToSend: 'Enter 发送',
    ctrlEnterToSend: 'Ctrl+Enter 发送',
    artifactsAutoOpen: '产物面板',
    artifactsAutoOpenNever: '保持关闭（角标与提示）',
    artifactsAutoOpenOnNew: '有新产物时打开',
    artifactsAutoOpenAlways: '有新产物时始终打开',
    send: '发送',
    thinkingEffort: '推理深度',
    thinkingNone: '关闭（默认）',
    thinkingLow: '低',
    thinkingMedium: '中',
    thinkingHigh: '高',
    thinkingEffortUnavailable: '当前智能体绑定的模型不支持工作台推理深度控制。',
    boundModel: '模型',
    boundProfile: '配置',
  },
}, true, true)
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { ThinkingEffortOption } from '@/lib/chatApi'
import type { ArtifactsAutoOpenPreference, ThinkingEffort } from '@/lib/userPreferencesTypes'
import { Textarea } from '@/components/ui/textarea'
import { Message, ContextResource } from '@/types'
import { Bot, Loader2, LockKeyhole, Send, Settings } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useChatScroll } from '@/hooks/useChatScroll'
import { shouldShowStreamingTurn } from '@/lib/chatStream'
import { buildStreamingTurn, StreamingToolCallState } from '@/lib/chatTurns'
import type { ThreadLoadError } from '@/hooks/useChatHistory'

interface ChatAreaProps {
  // Display state
  messages: Message[]
  isStreaming: boolean
  isBusy?: boolean
  streamingContent: string
  streamingToolCalls?: StreamingToolCallState[]
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

  // Pagination
  hasMore?: boolean
  isLoadingMore?: boolean
  onLoadMore?: () => Promise<void>

  // Callbacks
  onSendMessage: (message: string, resources: ContextResource[]) => void
  onSendKeyPreferenceChange: (value: 'enter' | 'ctrl-enter') => void
  onArtifactsAutoOpenChange: (value: ArtifactsAutoOpenPreference) => void
  onThinkingEffortChange: (value: ThinkingEffort) => void
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
}

export default function ChatArea({
  messages,
  isStreaming,
  isBusy = false,
  streamingContent,
  streamingToolCalls = [],
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
}: ChatAreaProps) {
  const { t } = useTranslation()
  const modelChipTitle = useMemo(() => {
    if (!agentModelId) {
      return ''
    }
    if (agentProfileName && agentProfileName !== agentModelId) {
      return `${agentProfileName}\n${agentModelId}`
    }
    return agentModelId
  }, [agentModelId, agentProfileName])

  const showRuntimeBar =
    Boolean(agentModelId) || (thinkingEffortControlEnabled && thinkingEffortOptions.length > 0)

  const [input, setInput] = useState('')
  const [selectedResources, setSelectedResources] = useState<ContextResource[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const resourcePickerRef = useRef<ResourcePickerPopoverHandle>(null)
  const { containerRef, onScroll, pinToBottom } = useChatScroll({
    threadId,
    messages,
    followContent: streamingContent,
    hasMore,
    isLoadingMore,
    onLoadMore,
  })

  // Detect @ trigger in input
  useEffect(() => {
    const match = input.match(/@([^\s]*)$/)
    setPickerOpen(!!match && !isBusy)
  }, [input, isBusy])

  const handleResourceSelect = useCallback((resource: ContextResource) => {
    setSelectedResources((prev) => [...prev, resource])
    setInput((prev) => prev.replace(/@[^\s]*$/, ''))
  }, [])

  const handleRemoveResource = useCallback((resource: ContextResource) => {
    setSelectedResources((prev) =>
      prev.filter((r) => r.artifact_id !== resource.artifact_id)
    )
  }, [])

  const selectedIds = new Set(
    selectedResources.map((r) => `artifact-${r.artifact_id}`)
  )

  const handleSend = useCallback(() => {
    pinToBottom()
    onSendMessage(input, selectedResources)
    setInput('')
    setSelectedResources([])
  }, [input, onSendMessage, pinToBottom, selectedResources])

  const handleKeyPress = useCallback(
    (e: React.KeyboardEvent) => {
      if (pickerOpen && resourcePickerRef.current?.handleKeyDown(e)) {
        return
      }

      const shouldSend =
        sendKeyPreference === 'enter'
          ? e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey
          : e.key === 'Enter' && (e.ctrlKey || e.metaKey)

      if (shouldSend) {
        e.preventDefault()
        handleSend()
      }
    },
    [sendKeyPreference, handleSend, pickerOpen]
  )

  const streamingTurn = shouldShowStreamingTurn(isStreaming, isBusy)
    ? buildStreamingTurn({
        content: streamingContent,
        toolCalls: streamingToolCalls,
      })
    : null

  const emptyStateContent = (() => {
    if (isLoadingHistory && threadId) {
      return {
        icon: <Loader2 className="w-16 h-16 text-muted-foreground mb-4 animate-spin" />,
        title: t('common.loading'),
        description: null,
      }
    }

    if (threadLoadError === 'forbidden') {
      return {
        icon: <LockKeyhole className="w-16 h-16 text-muted-foreground mb-4" />,
        title: t('workbench.threadNotAccessible'),
        description: t('workbench.threadNotAccessibleDesc'),
      }
    }

    if (threadLoadError === 'not_found') {
      return {
        icon: <LockKeyhole className="w-16 h-16 text-muted-foreground mb-4" />,
        title: t('workbench.threadNotFound'),
        description: t('workbench.threadNotFoundDesc'),
      }
    }

    if (threadLoadError === 'unknown') {
      return {
        icon: <Bot className="w-16 h-16 text-muted-foreground mb-4" />,
        title: t('workbench.threadLoadFailed'),
        description: t('workbench.threadLoadFailedDesc'),
      }
    }

    if (agentAccessRevoked) {
      return {
        icon: <LockKeyhole className="w-16 h-16 text-muted-foreground mb-4" />,
        title: t('workbench.agentAccessRevoked'),
        description: t('workbench.agentAccessRevokedDesc'),
      }
    }

    return {
      icon: <Bot className="w-16 h-16 text-muted-foreground mb-4" />,
      title: t('workbench.startChat'),
      description: t('workbench.startChatDesc'),
    }
  })()

  const inputDisabled =
    isBusy || Boolean(threadLoadError) || agentAccessRevoked || (isLoadingHistory && Boolean(threadId))

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto p-6 space-y-4"
        onScroll={onScroll}
      >
        {hasMore ? (
          <div className="flex justify-center py-1 text-xs text-muted-foreground">
            {isLoadingMore ? t('common.loading') : null}
          </div>
        ) : null}

        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            {emptyStateContent.icon}
            <h2 className="text-xl font-semibold mb-2">{emptyStateContent.title}</h2>
            {emptyStateContent.description ? (
              <p className="text-muted-foreground max-w-md">{emptyStateContent.description}</p>
            ) : null}
            {!threadLoadError && !agentAccessRevoked && exampleQuestions.length > 0 ? (
              <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                {exampleQuestions.map((question) => (
                  <Button
                    key={question}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-auto whitespace-normal text-left"
                    disabled={inputDisabled}
                    onClick={() => onSendMessage(question, [])}
                  >
                    {question}
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        )}

        <MessageList
          messages={messages}
          threadId={threadId}
          streamingTurn={streamingTurn}
          onHitlApprovedContinue={onHitlApprovedContinue}
          onHitlRejected={onHitlRejected}
        />
      </div>

      <div className="border-t">
        {agentAccessRevoked && messages.length > 0 ? (
          <p className="px-3 pt-2 text-xs text-muted-foreground">{t('workbench.agentAccessRevoked')}</p>
        ) : null}
        <ContextChipsBar
          resources={selectedResources}
          onRemove={handleRemoveResource}
        />

        <div className="p-2 space-y-2">
          {showRuntimeBar ? (
            <div className="flex flex-wrap items-center gap-2 min-h-8">
              {agentModelId ? (
                <Badge
                  variant="secondary"
                  className="max-w-[min(100%,20rem)] font-mono font-normal truncate shrink-0"
                  title={modelChipTitle}
                >
                  {agentModelId}
                </Badge>
              ) : null}
              {thinkingEffortControlEnabled && thinkingEffortOptions.length > 0 ? (
                <Select
                  value={thinkingEffort}
                  onValueChange={(value) => onThinkingEffortChange(value as ThinkingEffort)}
                  disabled={inputDisabled}
                >
                  <SelectTrigger
                    className="h-8 w-auto min-w-[9rem] max-w-[14rem] gap-1.5 px-2.5 text-xs font-normal"
                    aria-label={t('workbench.thinkingEffort')}
                  >
                    <span className="text-muted-foreground shrink-0">{t('workbench.thinkingEffort')}</span>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="start">
                    {thinkingEffortOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value} className="text-xs">
                        {option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          ) : null}

          <div className="flex gap-2 items-center">
          <div className="flex-1 relative">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={
                agentAccessRevoked
                  ? t('workbench.agentAccessRevoked')
                  : sendKeyPreference === 'enter'
                    ? t('workbench.messagePlaceholderEnter')
                    : t('workbench.messagePlaceholderCtrlEnter')
              }
              disabled={inputDisabled}
              className="min-h-16 max-h-40 resize-none pr-8"
              rows={3}
            />

            <ResourcePickerPopover
              ref={resourcePickerRef}
              inputValue={input}
              open={pickerOpen}
              onOpenChange={setPickerOpen}
              onSelect={handleResourceSelect}
              selectedIds={selectedIds}
            />
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" disabled={inputDisabled}>
                <Settings className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuRadioGroup
                value={sendKeyPreference}
                onValueChange={(value) =>
                  onSendKeyPreferenceChange(value as 'enter' | 'ctrl-enter')
                }
              >
                <DropdownMenuRadioItem value="enter">{t('workbench.enterToSend')}</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="ctrl-enter">{t('workbench.ctrlEnterToSend')}</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>{t('workbench.artifactsAutoOpen')}</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={artifactsAutoOpen}
                onValueChange={(value) =>
                  onArtifactsAutoOpenChange(value as ArtifactsAutoOpenPreference)
                }
              >
                <DropdownMenuRadioItem value="never">
                  {t('workbench.artifactsAutoOpenNever')}
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="on-new">
                  {t('workbench.artifactsAutoOpenOnNew')}
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="always">
                  {t('workbench.artifactsAutoOpenAlways')}
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button className="min-h-11 px-4" onClick={handleSend} disabled={inputDisabled || !input.trim()}>
            <Send className="w-4 h-4 mr-2" />
            {t('workbench.send')}
          </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
