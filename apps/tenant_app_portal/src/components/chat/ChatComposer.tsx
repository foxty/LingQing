import './workbenchChatI18n'
import ContextChipsBar from './ContextChipsBar'
import ResourcePickerPopover, {
  type ResourcePickerPopoverHandle,
} from './ResourcePickerPopover'
import ChatComposerToolbar from './ChatComposerToolbar'
import { Textarea } from '@/components/ui/textarea'
import type { ThreadLoadError } from '@/hooks/useChatHistory'
import type { ThinkingEffortOption } from '@/lib/chatApi'
import {
  mentionResourceChipId,
  shouldOpenMentionPicker,
  stripTrailingMention,
} from '@/lib/chatMention'
import type { ArtifactsAutoOpenPreference, ThinkingEffort } from '@/lib/userPreferencesTypes'
import type { AttachedArtifact } from '@/types'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface ChatComposerProps {
  isBusy: boolean
  threadId?: string
  isLoadingHistory: boolean
  threadLoadError: ThreadLoadError | null
  agentAccessRevoked: boolean
  showAgentAccessRevokedNotice: boolean
  sendKeyPreference: 'enter' | 'ctrl-enter'
  artifactsAutoOpen: ArtifactsAutoOpenPreference
  thinkingEffort: ThinkingEffort
  thinkingEffortOptions: ThinkingEffortOption[]
  thinkingEffortControlEnabled: boolean
  agentModelId: string
  agentProfileName: string
  onSendMessage: (message: string, resources: AttachedArtifact[]) => void
  onSendKeyPreferenceChange: (value: 'enter' | 'ctrl-enter') => void
  onArtifactsAutoOpenChange: (value: ArtifactsAutoOpenPreference) => void
  onThinkingEffortChange: (value: ThinkingEffort) => void
  onBeforeSend?: () => void
}

export default function ChatComposer({
  isBusy,
  threadId,
  isLoadingHistory,
  threadLoadError,
  agentAccessRevoked,
  showAgentAccessRevokedNotice,
  sendKeyPreference,
  artifactsAutoOpen,
  thinkingEffort,
  thinkingEffortOptions,
  thinkingEffortControlEnabled,
  agentModelId,
  agentProfileName,
  onSendMessage,
  onSendKeyPreferenceChange,
  onArtifactsAutoOpenChange,
  onThinkingEffortChange,
  onBeforeSend,
}: ChatComposerProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [selectedResources, setSelectedResources] = useState<AttachedArtifact[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const resourcePickerRef = useRef<ResourcePickerPopoverHandle>(null)

  const modelChipTitle = useMemo(() => {
    if (!agentModelId) {
      return agentProfileName || ''
    }
    if (agentProfileName && agentProfileName !== agentModelId) {
      return `${agentProfileName}\n${agentModelId}`
    }
    return agentModelId
  }, [agentModelId, agentProfileName])

  const modelDisplayLabel = useMemo(() => {
    if (agentProfileName && agentProfileName !== agentModelId) {
      return agentProfileName
    }
    return agentModelId
  }, [agentModelId, agentProfileName])

  const showRuntimeControls =
    Boolean(modelDisplayLabel) || (thinkingEffortControlEnabled && thinkingEffortOptions.length > 0)

  const sendKeyHint =
    sendKeyPreference === 'enter'
      ? t('workbench.composerSendHintEnter')
      : t('workbench.composerSendHintCtrlEnter')

  const inputDisabled =
    isBusy || Boolean(threadLoadError) || agentAccessRevoked || (isLoadingHistory && Boolean(threadId))

  const selectedIds = useMemo(
    () => new Set(selectedResources.map((r) => mentionResourceChipId(r.artifact_id))),
    [selectedResources]
  )

  useEffect(() => {
    setPickerOpen(shouldOpenMentionPicker(input, isBusy))
  }, [input, isBusy])

  const handleResourceSelect = useCallback((resource: AttachedArtifact) => {
    setSelectedResources((prev) => [...prev, resource])
    setInput((prev) => stripTrailingMention(prev))
  }, [])

  const handleRemoveResource = useCallback((resource: AttachedArtifact) => {
    setSelectedResources((prev) => prev.filter((r) => r.artifact_id !== resource.artifact_id))
  }, [])

  const handleSend = useCallback(() => {
    onBeforeSend?.()
    onSendMessage(input, selectedResources)
    setInput('')
    setSelectedResources([])
  }, [input, onBeforeSend, onSendMessage, selectedResources])

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

  return (
    <div className="flex shrink-0 flex-col gap-2 bg-background px-3 pb-3 pt-3">
      {showAgentAccessRevokedNotice ? (
        <p className="mb-2 text-xs text-muted-foreground">{t('workbench.agentAccessRevoked')}</p>
      ) : null}
      <ContextChipsBar resources={selectedResources} onRemove={handleRemoveResource} />

      <div className="rounded-[var(--radius-pane)] border border-border bg-card">
        <div className="relative z-10">
          <ResourcePickerPopover
            ref={resourcePickerRef}
            inputValue={input}
            open={pickerOpen}
            onOpenChange={setPickerOpen}
            onSelect={handleResourceSelect}
            selectedIds={selectedIds}
          />
          <div className="[&>div]:mb-0">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder={
                agentAccessRevoked ? t('workbench.agentAccessRevoked') : t('workbench.messagePlaceholder')
              }
              disabled={inputDisabled}
              className="min-h-[4.5rem] max-h-40 resize-none rounded-none border-0 bg-transparent px-3 py-3 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
              rows={3}
            />
          </div>
        </div>

        <ChatComposerToolbar
          inputDisabled={inputDisabled}
          canSend={Boolean(input.trim())}
          sendKeyHint={sendKeyHint}
          showRuntimeControls={showRuntimeControls}
          modelDisplayLabel={modelDisplayLabel}
          modelChipTitle={modelChipTitle}
          agentModelId={agentModelId}
          thinkingEffortControlEnabled={thinkingEffortControlEnabled}
          thinkingEffortOptions={thinkingEffortOptions}
          thinkingEffort={thinkingEffort}
          onThinkingEffortChange={onThinkingEffortChange}
          sendKeyPreference={sendKeyPreference}
          onSendKeyPreferenceChange={onSendKeyPreferenceChange}
          artifactsAutoOpen={artifactsAutoOpen}
          onArtifactsAutoOpenChange={onArtifactsAutoOpenChange}
          onSend={handleSend}
        />
      </div>
      {showRuntimeControls ? (
        <p className="mt-1.5 px-0.5 text-[11px] text-muted-foreground">{t('workbench.composerAttachHint')}</p>
      ) : null}
    </div>
  )
}
