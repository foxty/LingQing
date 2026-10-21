import '@/components/chat/workbenchChatI18n'
import ThreadSelector from '@/components/workbench/ThreadSelector'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ChatThread } from '@/types'
import { PanelRight, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface AgentOption {
  id: number
  name: string
}

interface WorkbenchThreadChromeProps {
  sharedUiEnabled: boolean
  selectedAgentId: number
  agentOptions: AgentOption[]
  onAgentChange: (agentId: number) => void
  threads: ChatThread[]
  currentThreadId: string | null
  threadsLoading: boolean
  isSharedThread: boolean
  showMembersButton: boolean
  participantCount?: number
  onSelectThread: (threadId: string) => void
  onCreateConversation: () => void
  onDeleteThread: (threadId: string) => Promise<void>
  onOpenMembers: () => void
  membersPanelOpen: boolean
  artifactsCount: number
  artifactsPanelVisible: boolean
  onOpenArtifactsPanel: () => void
  onCloseArtifactsPanel: () => void
}

export default function WorkbenchThreadChrome({
  sharedUiEnabled,
  selectedAgentId,
  agentOptions,
  onAgentChange,
  threads,
  currentThreadId,
  threadsLoading,
  isSharedThread,
  showMembersButton,
  participantCount,
  onSelectThread,
  onCreateConversation,
  onDeleteThread,
  onOpenMembers,
  membersPanelOpen,
  artifactsCount,
  artifactsPanelVisible,
  onOpenArtifactsPanel,
  onCloseArtifactsPanel,
}: WorkbenchThreadChromeProps) {
  const { t } = useTranslation()

  const handleArtifactsClick = () => {
    if (artifactsPanelVisible) {
      onCloseArtifactsPanel()
      return
    }
    onOpenArtifactsPanel()
  }

  return (
    <div className="shrink-0 border-b bg-background">
      {isSharedThread ? (
        <div className="flex items-center gap-2 border-b border-accent/20 bg-accent/5 px-3 py-1.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{t('workbench.sharedRoomBanner')}</span>
          <span>{t('workbench.sharedRoomBannerHint')}</span>
        </div>
      ) : null}

      <div className="flex min-h-11 flex-wrap items-center gap-2 px-3 py-1.5">
        {sharedUiEnabled ? (
          <Select value={String(selectedAgentId)} onValueChange={(v) => onAgentChange(Number(v))}>
            <SelectTrigger className="h-9 w-44 shrink-0" aria-label={t('workbench.filterByAgent')}>
              <SelectValue placeholder={t('workbench.filterByAgent')} />
            </SelectTrigger>
            <SelectContent>
              {agentOptions.map((agent) => (
                <SelectItem key={agent.id} value={String(agent.id)}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Select value={String(selectedAgentId)} onValueChange={(v) => onAgentChange(Number(v))}>
            <SelectTrigger className="h-9 w-44 shrink-0" aria-label={t('workbench.selectAgent')}>
              <SelectValue placeholder={t('workbench.selectAgent')} />
            </SelectTrigger>
            <SelectContent>
              {agentOptions.map((agent) => (
                <SelectItem key={agent.id} value={String(agent.id)}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <ThreadSelector
          threads={threads}
          currentThreadId={currentThreadId}
          isLoading={threadsLoading}
          onSelectThread={onSelectThread}
          onCreateThread={onCreateConversation}
          onDeleteThread={onDeleteThread}
          createLabel={t('components.threadSelector.newThread')}
          emptyHint={t('workbench.conversationsEmptyHint')}
        />

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {showMembersButton && currentThreadId ? (
            <Button
              variant={membersPanelOpen ? 'secondary' : 'outline'}
              size="sm"
              className="h-9 gap-1.5"
              onClick={onOpenMembers}
            >
              <Users className="h-4 w-4" />
              {t('workbench.conversationParticipantsShort')}
              {participantCount != null && participantCount > 0 ? (
                <span className="tabular-nums text-muted-foreground">({participantCount})</span>
              ) : null}
            </Button>
          ) : null}

          {currentThreadId ? (
            <Button
              variant={artifactsPanelVisible ? 'secondary' : 'ghost'}
              size="sm"
              className="h-9 px-2"
              disabled={artifactsCount === 0}
              onClick={handleArtifactsClick}
              title={
                artifactsCount === 0
                  ? t('workbench.noArtifactsYet')
                  : artifactsPanelVisible
                    ? t('workbench.closeArtifacts')
                    : t('workbench.openArtifacts')
              }
              aria-label={t('workbench.openArtifacts')}
            >
              <PanelRight className="h-4 w-4" />
              {artifactsCount > 0 ? (
                <span className="ml-1.5 tabular-nums text-xs text-muted-foreground">{artifactsCount}</span>
              ) : null}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
